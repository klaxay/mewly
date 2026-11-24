import asyncio
from email import policy
from email.parser import BytesParser
from io import BytesIO
import wave

import httpx
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

import server
from transcribe import CHUNK_BYTES, OpenAIWhisperTranscriber


def test_whisper_batches_pcm_into_wav():
    first = b"\x01\x00" * (CHUNK_BYTES // 2)
    second = b"\x02\x00" * (CHUNK_BYTES // 2)
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.path == "/v1/audio/transcriptions"
        header = f"Content-Type: {request.headers['content-type']}\r\n\r\n"
        multipart = BytesParser(policy=policy.default).parsebytes(
            header.encode() + request.content
        )
        model, audio = multipart.iter_parts()
        assert model.get_payload(decode=True) == b"gpt-4o-transcribe"
        assert audio.get_content_type() == "audio/wav"
        with wave.open(BytesIO(audio.get_payload(decode=True)), "rb") as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (
                1, 2, 16000
            )
            assert wav.readframes(wav.getnframes()) == first + second
        return httpx.Response(200, json={"text": "  Confirm the date.  "})

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async with AsyncOpenAI(
            api_key="test", base_url="https://example.test/v1", http_client=http
        ) as client:
            transcriber = OpenAIWhisperTranscriber(client)
            assert await transcriber.transcribe(first) == ""
            assert await transcriber.transcribe(b"") == ""
            assert requests == []
            assert await transcriber.transcribe(second) == "Confirm the date."
            assert await transcriber.transcribe(bytes(CHUNK_BYTES)) == ""
            assert await transcriber.transcribe(bytes(CHUNK_BYTES)) == ""
            assert len(requests) == 1

    asyncio.run(run())


def test_websocket_recovers_from_transcription_failure(monkeypatch):
    monkeypatch.setenv("MEWLY_TRANSCRIBER", "whisper")
    monkeypatch.setenv("MEWLY_ASSISTANT", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("WHISPER_WINDOW_SECONDS", "3")
    monkeypatch.setenv("WHISPER_MODEL", "custom-transcriber")
    requests = []

    def respond(request):
        requests.append(request)
        assert b"custom-transcriber" in request.content
        assert request.headers["authorization"] == "Bearer test"
        if len(requests) == 1:
            return httpx.Response(500, json={"error": {"message": "Unavailable"}})
        if len(requests) == 2:
            return httpx.Response(200, json={"text": " "})
        return httpx.Response(200, json={"text": "Speech recovered"})

    def mock_client(**kwargs):
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        return AsyncOpenAI(http_client=http, **kwargs)

    monkeypatch.setattr(server, "AsyncOpenAI", mock_client)
    pcm = b"\x01\x00" * (CHUNK_BYTES // 2)
    with TestClient(server.app) as client, client.websocket_connect("/ws") as socket:
        socket.send_bytes(pcm)
        assert socket.receive_json() == {"type": "error", "text": "Transcription failed."}
        assert socket.receive_json() == {"type": "ready"}

        socket.send_bytes(pcm)
        assert socket.receive_json() == {"type": "ready"}

        socket.send_bytes(pcm)
        assert socket.receive_json() == {"type": "transcript", "text": "Speech recovered"}
        assert socket.receive_json()["text"].startswith("[Demo]")
        assert socket.receive_json() == {"type": "ready"}
    assert len(requests) == 3
