import asyncio
import io
import unittest
import wave

import httpx
from fastapi.testclient import TestClient
from voice_studio.app import create_app, SpeechError


def test_wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\0\0" * 2400)
    return buffer.getvalue()


class TestEngine:
    """Deliberate test double; never used by the runnable app."""
    def __init__(self, available=True, failure=None):
        self.available, self.failure, self.calls = available, failure, []

    def ready(self):
        return self.available

    async def generate(self, speech):
        self.calls.append(speech)
        if self.failure:
            raise self.failure
        return test_wav()


class APIContracts(unittest.TestCase):
    def setUp(self):
        self.engine = TestEngine()
        self.client = TestClient(create_app(self.engine, api_key=""))

    def test_wav_response_is_downloadable_pcm_with_duration(self):
        response = self.client.post('/api/speech', json={"text": "Hello, world.", "voice": "F2", "speed": 0.9})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'audio/wav')
        self.assertIn('attachment', response.headers['content-disposition'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertAlmostEqual(float(response.headers['x-audio-duration']), 0.1)
        with wave.open(io.BytesIO(response.content)) as audio:
            self.assertEqual((audio.getframerate(), audio.getsampwidth(), audio.getnchannels()), (24000, 2, 1))
        self.assertEqual(self.engine.calls[0].voice, 'F2')
        self.assertEqual(self.engine.calls[0].speed, 0.9)

    def test_bad_scripts_and_parameters_never_reach_engine(self):
        invalid = [
            {"text": "  "}, {"text": "..."}, {"text": "hello 你好"},
            {"text": "x" * 6001}, {"text": "hello\u0000world"},
            {"text": "hello", "speed": 0}, {"text": "hello", "speed": 1.3},
            {"text": "hello", "voice": "M2\n"}, {"text": "hello", "voice": "unknown"},
            {"text": "hello", "checkpoint": "/etc/passwd"},
        ]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:40]):
                self.assertEqual(self.client.post('/api/speech', json=payload).status_code, 422)
        self.assertEqual(self.engine.calls, [])

    def test_malformed_json_and_oversized_body(self):
        self.assertEqual(self.client.post('/api/speech', content='{not json').status_code, 422)
        self.assertEqual(self.client.post('/api/speech', content=b'x' * 40001).status_code, 413)

    def test_model_missing_is_honest_and_non_audio(self):
        client = TestClient(create_app(TestEngine(available=False), api_key=""))
        self.assertFalse(client.get('/api/config').json()['ready'])
        response = client.post('/api/speech', json={"text": "Hello."})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('audio/wav', response.headers['content-type'])

    def test_access_key_checked_before_generation(self):
        client = TestClient(create_app(self.engine, api_key="test-key"))
        for header in ['', 'Bearer wrong', 'Bearer test-key-too-long']:
            response = client.post('/api/speech', json={"text": "Hello."}, headers={'Authorization': header})
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.engine.calls, [])
        self.assertTrue(client.get('/api/config').json()['requires_key'])
        response = client.post('/api/speech', json={"text": "Hello."}, headers={'Authorization': 'Bearer test-key'})
        self.assertEqual(response.status_code, 200)

    def test_timeout_and_error_do_not_leak_script_or_traceback(self):
        for error, status in [(TimeoutError(), 504), (SpeechError('No speech was generated.'), 422),
                              (RuntimeError('private script details'), 500)]:
            with self.subTest(status=status):
                client = TestClient(create_app(TestEngine(failure=error), api_key=""))
                response = client.post('/api/speech', json={"text": "Private text."})
                self.assertEqual(response.status_code, status)
                self.assertNotIn('private script details', response.text)
                self.assertNotIn('Private text.', response.text)

    def test_page_and_assets_exist_with_external_scripts(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Tiny Voca Studio', response.text)
        self.assertIn("script-src 'self'", response.headers['content-security-policy'])
        for path in ['/static/studio.js', '/static/studio.css']:
            self.assertEqual(self.client.get(path).status_code, 200)


class ConcurrentGeneration(unittest.IsolatedAsyncioTestCase):
    async def test_busy_requests_are_rejected_and_gate_reopens_after_failure(self):
        started, finish = asyncio.Event(), asyncio.Event()

        class SlowEngine(TestEngine):
            async def generate(self, speech):
                started.set()
                await finish.wait()
                return test_wav()

        app = create_app(SlowEngine(), api_key="")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            first = asyncio.create_task(client.post('/api/speech', json={"text": "First."}))
            await asyncio.wait_for(started.wait(), 3)
            second = await client.post('/api/speech', json={"text": "Second."})
            self.assertEqual(second.status_code, 429)
            self.assertEqual(second.headers['retry-after'], '5')
            finish.set()
            self.assertEqual((await first).status_code, 200)
            self.assertEqual((await client.post('/api/speech', json={"text": "Third."})).status_code, 200)


if __name__ == '__main__':
    unittest.main()
