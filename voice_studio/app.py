"""Run with: python -m uvicorn voice_studio.app:app --host 0.0.0.0 --port 8090."""
import asyncio
import hmac
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import wave
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent
MAX_CHARS = 6000


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    voice: Literal["F2", "M2"] = "M2"
    speed: float = Field(default=1.0, ge=0.75, le=1.25)

    @field_validator("text")
    @classmethod
    def readable_english(cls, value):
        value = value.strip()
        if not re.search(r"[A-Za-z0-9]", value):
            raise ValueError("Add an English script containing words or numbers.")
        for char in value:
            if unicodedata.category(char) == "Cc" and char not in "\n\r\t":
                raise ValueError("The script contains unsupported control characters.")
            if char.isalpha() and "LATIN" not in unicodedata.name(char, ""):
                raise ValueError("Tiny-voca supports English only. Translate your script into English first.")
        return value


class SpeechError(Exception):
    pass


class CLIEngine:
    """Isolate each inference in a killable process; never retain scripts or audio."""

    def __init__(self):
        self.checkpoint = Path(os.environ.get("TINY_VOCA_CHECKPOINT", str(ROOT / "weights/tiny-voca.pt")))
        self.phonemizer = Path(os.environ.get("DIZIONE_DATA", str(ROOT / "weights/phonemizer")))

    def ready(self):
        return (
            self.checkpoint.is_file()
            and all((self.phonemizer / name).is_file() for name in
                    ("lexicon.tsv", "align.json", "g2p.json", "g2p.npz", "homographs.json"))
            and all(importlib.util.find_spec(name) is not None for name in
                    ("tiny_voca", "torch", "soundfile", "dizione"))
        )

    async def generate(self, speech):
        with tempfile.TemporaryDirectory(prefix="tiny-voca-") as temporary:
            directory = Path(temporary)
            script, output = directory / "script.txt", directory / "speech.wav"
            script.write_text(speech.text, encoding="utf-8")
            environment = dict(os.environ, DIZIONE_DATA=str(self.phonemizer),
                               TINY_VOCA_FRONTEND="own", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "tiny_voca.infer", "--checkpoint", str(self.checkpoint),
                "--voice", speech.voice, "--speed", str(speech.speed), "--text-file", str(script),
                "--output", str(output), "--device", "cpu",
                env=environment, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=240)
            except (TimeoutError, asyncio.CancelledError):
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            if process.returncode != 0 or not output.is_file():
                raise SpeechError("This script could not be spoken. Try shorter sentences and English words.")
            # The CLI produces float WAV. Re-encode as PCM-16 for broad player/editor support.
            import soundfile as sf
            samples, sample_rate = sf.read(output, dtype="float32")
            if len(samples) == 0:
                raise SpeechError("No speech was generated. Try an English sentence.")
            import io
            buffer = io.BytesIO()
            sf.write(buffer, samples, sample_rate, format="WAV", subtype="PCM_16")
            return buffer.getvalue()


def create_app(engine=None, api_key=None):
    engine = engine if engine is not None else CLIEngine()
    access_key = os.environ.get("TINY_VOCA_API_KEY", "") if api_key is None else api_key
    application = FastAPI(title="Tiny Voca Studio", docs_url=None, redoc_url=None)
    gate = asyncio.Lock()

    @application.middleware("http")
    async def privacy_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "media-src 'self' blob:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    @application.get("/", include_in_schema=False)
    async def home():
        return FileResponse(Path(__file__).parent / "static/index.html")

    @application.get("/healthz", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @application.get("/api/config")
    async def config():
        return {"engine": "tiny-voca", "language": "en-US", "voices": ["M2", "F2"],
                "max_characters": MAX_CHARS, "requires_key": bool(access_key),
                "ready": engine.ready()}

    @application.post("/api/speech", response_class=Response,
                      responses={200: {"content": {"audio/wav": {}}}})
    async def speech(request: Request, authorization: str = Header(default="")):
        if access_key and not hmac.compare_digest(authorization.encode(),
                                                 ("Bearer " + access_key).encode()):
            raise HTTPException(401, "Enter the correct studio access key.",
                                headers={"WWW-Authenticate": "Bearer"})
        # Bound the body before JSON decoding or model validation, including chunked uploads.
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 40000:
                raise HTTPException(413, "Script upload is too large. Use at most 6,000 characters.")
        try:
            payload = SpeechRequest.model_validate_json(bytes(data))
        except ValueError:
            # Do not echo validation input: scripts should not appear in error responses/logs.
            raise HTTPException(422, "Use an English script of 1–6,000 characters, voice M2 or F2, and speed 0.75–1.25.")
        if not engine.ready():
            raise HTTPException(503, "The speech model is not installed. Complete the server model setup first.")
        if gate.locked():
            raise HTTPException(429, "Another script is being generated. Please try again shortly.",
                                headers={"Retry-After": "5"})
        async with gate:
            try:
                audio = await engine.generate(payload)
                import io
                with wave.open(io.BytesIO(audio)) as wav:
                    duration = wav.getnframes() / wav.getframerate()
                    if not wav.getnframes():
                        raise SpeechError("No speech was generated.")
            except TimeoutError:
                raise HTTPException(504, "Generation took too long. Split the script into smaller parts.")
            except SpeechError as error:
                raise HTTPException(422, str(error))
            except Exception:
                raise HTTPException(500, "Speech generation failed. Try again or check the model installation.")
        return Response(audio, media_type="audio/wav", headers={
            "Content-Disposition": 'attachment; filename="tiny-voca-narration.wav"',
            "X-Audio-Duration": f"{duration:.3f}",
        })

    application.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return application


app = create_app()
