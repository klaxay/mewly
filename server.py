"""Serve the capture page and run one meeting loop per WebSocket."""

from contextlib import AsyncExitStack, asynccontextmanager
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from openai import APIError, AsyncOpenAI

from assist import DummyAssistant, OpenAIAssistant
from assist.window import TranscriptWindow
from transcribe import CHUNK_BYTES, DummyTranscriber, OpenAIWhisperTranscriber

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def mode(name: str) -> str:
    value = os.getenv(name, "dummy")
    if value not in {"dummy", "openai"}:
        raise ValueError(f"{name} must be dummy or openai")
    return value


def api_key(name: str) -> str:
    key = os.getenv(name) or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError(f"Set {name} or OPENAI_API_KEY for the selected adapter")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env")
    app.state.transcriber = None
    app.state.assistant = DummyAssistant()
    app.state.meeting_context = os.getenv("MEETING_CONTEXT", "")

    # Reuse HTTP connections across chunks and close them on server shutdown.
    async with AsyncExitStack() as stack:
        if mode("TRANSCRIBER") == "openai":
            client = await stack.enter_async_context(AsyncOpenAI(
                api_key=api_key("OPENAI_API_KEY"), timeout=8, max_retries=0,
            ))
            app.state.transcriber = OpenAIWhisperTranscriber(
                client, os.getenv("WHISPER_MODEL", "whisper-1")
            )
        if mode("ASSISTANT") == "openai":
            client = await stack.enter_async_context(AsyncOpenAI(
                api_key=api_key("ASSISTANT_API_KEY"),
                base_url=os.getenv("ASSISTANT_BASE_URL") or None,
                timeout=8,
                max_retries=0,
            ))
            app.state.assistant = OpenAIAssistant(
                client, os.getenv("ASSISTANT_MODEL", "gpt-4o-mini")
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
    transcriber = state.transcriber or DummyTranscriber()
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
