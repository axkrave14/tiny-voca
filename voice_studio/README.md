# Tiny Voca Studio

Paste an English script or import a UTF-8 `.txt` file, choose the male (M2) or female (F2) voice, adjust the speed, and select **Generate voiceover**. Play the result, download a PCM-16 WAV, or share it on supported mobile browsers. A single script can contain up to 6,000 characters. The text remains in the current browser page; it is not saved across reloads.

This is text-to-speech, not language translation. Tiny-voca currently speaks American English only. Foreign names may need phonetic spelling. No paid speech provider or voice cloning is used. WAV output is 24 kHz with the released model.

## Local setup

Use Python 3.12. From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install . -r voice_studio/requirements.txt \
  'dizione @ git+https://github.com/n4ze3m/dizione@8cd889e4de7be6bd1dd2e6891344a0729fa14dd4'
python -m voice_studio.fetch_model
python -m uvicorn voice_studio.app:app --host 127.0.0.1 --port 8090 --no-access-log
```

Open `http://127.0.0.1:8090`. Model files are downloaded once, then generation runs locally without a speech API. The setup needs internet access to GitHub, PyPI, PyTorch, Hugging Face, and Hugging Face's model-download hosts. The downloaded model revision and phonemizer code are pinned. Model and phonemizer license notices remain with the downloaded assets.

## Google Cloud Run

The included Dockerfile downloads the model at build time so requests do not need to fetch it. The container runs as a non-root user and respects Cloud Run's `PORT`. Use a Google Cloud project with billing and Cloud Run, Cloud Build, and Artifact Registry enabled, and the deployment/build permissions required by Google Cloud's source deployment workflow.

From an authenticated Google Cloud CLI or Cloud Shell, clone this fork and check out the branch containing these files. Then run:

```bash
bash voice_studio/deploy-cloudrun.sh YOUR_PROJECT_ID
```

The default region is Singapore (`asia-southeast1`). Pass a second argument to choose another region. This command creates billable resources: build, image storage, runtime, and network usage may incur charges. Zero minimum instances and one maximum instance bound runtime scaling but are not a hard spending cap.

The script deploys a **private** service. It does not grant public access. For personal browser use, run the authenticated proxy command printed by the script and open `http://127.0.0.1:8090`. In Cloud Shell, use Web Preview on port 8090. A private endpoint cannot be opened directly on a phone without an appropriate sign-in/access layer; do not remove Cloud Run authentication just to bypass this step.

If a directly accessible mobile URL is wanted, configure an appropriate login layer separately. The app also supports a shared `TINY_VOCA_API_KEY` for deployment behind an approved public gateway: provide it via Secret Manager or a protected environment variable, never in source or a URL. The UI displays an access-key field when configured and holds the value only in the page. This is an optional extra, not a replacement for Cloud IAM on a private service.

Cloud Run instructions: https://docs.cloud.google.com/run/docs/deploying-source-code

## API for video workflows

`POST /api/speech` accepts JSON and returns WAV bytes. On a private Cloud Run service, send a valid Cloud Run identity token as required by Google IAM; on the authenticated proxy, IAM is handled by the proxy. If an application access key is also configured, send that key in the `Authorization: Bearer ...` header through the proxy. Direct calls using both layers can use Google's `X-Serverless-Authorization` for the IAM identity token and `Authorization` for the app key.

```bash
curl --fail-with-body http://127.0.0.1:8090/api/speech \
  -H 'Content-Type: application/json' \
  --data '{"text":"Every story begins with a voice.","voice":"M2","speed":1.0}' \
  --output narration.wav
```

`GET /api/config` reports whether dependencies/model files are present, supported voices, and the character limit. It is a setup check, not proof that synthesis has succeeded. `GET /healthz` is a liveness check. Errors use HTTP 401, 413, 422, 429, 503, 504, or 500 as appropriate; unsuccessful responses must not be treated as WAV files.

Only one generation runs per app process. Busy requests receive 429 instead of creating an unbounded queue. Inference runs in a subprocess with a 240-second timeout. Its temporary script and output are removed after completion or failure. Each request loads a fresh model, so short clips have a startup cost. Requests and generated audio are not stored in a database or logged by the application. As with any web service, the hosting provider may retain normal request metadata.

## Verification

Install `httpx` and run:

```bash
python -m unittest discover -s voice_studio/tests -v
```

These API tests use a clearly isolated test engine and do not prove model quality. A real model smoke test must generate an actual WAV through `/api/speech` and check playback before calling the deployed service verified. Never substitute a browser's built-in voice for tiny-voca silently.
