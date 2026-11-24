"""Speech-to-text adapters share a simple PCM-in, text-out interface."""

from io import BytesIO
from typing import Protocol
import wave

from openai import AsyncOpenAI

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 3
CHUNK_BYTES = SAMPLE_RATE * CHUNK_SECONDS * 2
DEFAULT_WINDOW_SECONDS = 6
DEFAULT_MODEL = "gpt-4o-transcribe"


class Transcriber(Protocol):
    async def transcribe(self, pcm: bytes) -> str:
        """Accept signed 16-bit little-endian mono PCM and return available text."""


class DummyTranscriber:
    def __init__(self) -> None:
        self.chunk_number = 0

    async def transcribe(self, pcm: bytes) -> str:
        self.chunk_number += 1
        return f"[Demo {self.chunk_number}] Let's confirm the next milestone."


class OpenAIWhisperTranscriber:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = DEFAULT_MODEL,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        if window_seconds < 1:
            raise ValueError("Transcription window must be positive")
        self.client = client
        self.model = model
        self.window_bytes = SAMPLE_RATE * window_seconds * 2
        self.pending = bytearray()

    async def transcribe(self, pcm: bytes) -> str:
        if not pcm:
            return ""
        self.pending.extend(pcm)
        if len(self.pending) < self.window_bytes:
            return ""

        # Consume the batch before calling the provider so a failure can't replay it.
        batch, self.pending = self.pending, bytearray()
        if not any(batch):
            return ""

        # The file endpoint needs a container that describes the raw samples.
        audio = BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # Bytes per sample
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(batch)

        result = await self.client.audio.transcriptions.create(
            model=self.model,
            file=("chunk.wav", audio.getvalue(), "audio/wav"),
        )
        return result.text.strip()
