"""Serve the capture page and run one meeting loop per WebSocket."""

from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from openai import APIError, AsyncOpenAI

from assist import DEFAULT_MODEL as DEFAULT_ASSISTANT_MODEL
from assist import DummyAssistant, OpenAIAssistant
from assist.window import TranscriptWindow
from transcribe import DEFAULT_MODEL as DEFAULT_WHISPER_MODEL
from transcribe import (
    CHUNK_BYTES,
    DEFAULT_WINDOW_SECONDS,
    DummyTranscriber,
    OpenAIWhisperTranscriber,
)

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def mode(name: str, provider: str) -> str:
    value = os.getenv(name, "dummy")
    if value not in {"dummy", provider}:
        raise ValueError(f"{name} must be dummy or {provider}")
    return value


def api_key(override: str | None = None) -> str:
    key = (os.getenv(override) if override else None) or os.getenv("OPENAI_API_KEY")
    if not key:
        names = f"{override} or OPENAI_API_KEY" if override else "OPENAI_API_KEY"
        raise ValueError(f"Set {names} for the selected adapter")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env")
    app.state.make_transcriber = DummyTranscriber
    app.state.assistant = DummyAssistant()
    app.state.meeting_context = os.getenv("MEETING_CONTEXT", "")

    # Reuse HTTP connections across chunks and close them on server shutdown.
    async with AsyncExitStack() as stack:
        if mode("MEWLY_TRANSCRIBER", "whisper") == "whisper":
            window_seconds = int(os.getenv(
                "WHISPER_WINDOW_SECONDS", str(DEFAULT_WINDOW_SECONDS)
            ))
            if window_seconds < 1:
                raise ValueError("WHISPER_WINDOW_SECONDS must be positive")
            client = await stack.enter_async_context(AsyncOpenAI(
                api_key=api_key(), timeout=8, max_retries=0,
            ))
            app.state.make_transcriber = partial(
                OpenAIWhisperTranscriber,
                client,
                os.getenv("WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
                window_seconds,
            )
        if mode("MEWLY_ASSISTANT", "openai") == "openai":
            client = await stack.enter_async_context(AsyncOpenAI(
                api_key=api_key("ASSISTANT_API_KEY"),
                base_url=os.getenv("ASSISTANT_BASE_URL") or None,
                timeout=8,
                max_retries=0,
            ))
            app.state.assistant = OpenAIAssistant(
                client, os.getenv("ASSISTANT_MODEL", DEFAULT_ASSISTANT_MODEL)
            )
        yield


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def meeting(socket: WebSocket) -> None:
    # Browsers send Origin even for WebSocket handshakes. Keep other sites
    # from opening a session against the user's localhost server.
    origin = socket.headers.get("origin")
    scheme = "https" if socket.url.scheme == "wss" else "http"
    if origin is not None and origin != f"{scheme}://{socket.headers.get('host')}":
        await socket.close(code=1008)
        return
    await socket.accept()
    window = TranscriptWindow()
    state = socket.app.state
    transcriber = state.make_transcriber()
    try:
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                return
            pcm = message.get("bytes")
            if pcm is None or len(pcm) != CHUNK_BYTES:
                await socket.close(code=1003, reason="Expected one 3-second PCM chunk")
                return

            stage = "Transcription"
            try:
                text = (await transcriber.transcribe(pcm)).strip()
                if text:
                    window.add(text)
                    await socket.send_json({"type": "transcript", "text": text})
                    stage = "Suggestion"
                    suggestion = await state.assistant.suggest(
                        window.text(), state.meeting_context
                    )
                    await socket.send_json({"type": "suggestion", "text": suggestion})
            except APIError as error:
                logger.warning("%s failed (%s)", stage, type(error).__name__)
                await socket.send_json({"type": "error", "text": f"{stage} failed."})

            # Acknowledge even silence or a provider failure so capture can resume.
            await socket.send_json({"type": "ready"})
    except WebSocketDisconnect:
        pass


# Register the catch-all static mount after the WebSocket route.
app.mount("/", StaticFiles(directory=ROOT / "capture", html=True), name="capture")
