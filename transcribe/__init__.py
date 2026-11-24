"""Speech-to-text adapters share a simple PCM-in, text-out interface."""

from io import BytesIO
from typing import Protocol
import wave

from openai import AsyncOpenAI

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 3
CHUNK_BYTES = SAMPLE_RATE * CHUNK_SECONDS * 2


class Transcriber(Protocol):
    async def transcribe(self, pcm: bytes) -> str:
        """Turn a chunk of signed 16-bit little-endian mono PCM into text."""


class DummyTranscriber:
    def __init__(self) -> None:
        self.chunk_number = 0

    async def transcribe(self, pcm: bytes) -> str:
        self.chunk_number += 1
        return f"[Demo {self.chunk_number}] Let's confirm the next milestone."


class OpenAIWhisperTranscriber:
    def __init__(self, client: AsyncOpenAI, model: str = "whisper-1") -> None:
        self.client = client
        self.model = model

    async def transcribe(self, pcm: bytes) -> str:
        # The file endpoint needs a container that describes the raw samples.
        audio = BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # Bytes per sample
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm)

        result = await self.client.audio.transcriptions.create(
            model=self.model,
            file=("chunk.wav", audio.getvalue(), "audio/wav"),
        )
        return result.text.strip()
