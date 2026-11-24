"""Suggestion adapters consume the same rolling transcript snapshot."""

from typing import Protocol

from openai import AsyncOpenAI

from .prompt import build_prompt

DEFAULT_MODEL = "gpt-4o-mini"


class Assistant(Protocol):
    async def suggest(self, transcript: str, meeting_context: str = "") -> str:
        """Return one brief suggestion or an empty string."""


class DummyAssistant:
    async def suggest(self, transcript: str, meeting_context: str = "") -> str:
        return "[Demo] Ask who owns the next milestone and when it is due."


class OpenAIAssistant:
    def __init__(self, client: AsyncOpenAI, model: str = DEFAULT_MODEL) -> None:
        self.client = client
        self.model = model

    async def suggest(self, transcript: str, meeting_context: str = "") -> str:
        if not transcript.strip():
            return ""
        result = await self.client.chat.completions.create(
            model=self.model,
            messages=build_prompt(transcript, meeting_context),
            stream=False,
        )
        if not result.choices:
            return ""
        suggestion = (result.choices[0].message.content or "").strip()
        return "" if suggestion == "PASS" else suggestion
