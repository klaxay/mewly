import asyncio
import json

import httpx
from openai import AsyncOpenAI
import pytest

from assist import OpenAIAssistant
from assist.window import TranscriptWindow


@pytest.mark.parametrize(
    ("choices", "expected"),
    [
        ([{"content": "  Ask who owns the release.  "}], "Ask who owns the release."),
        ([{"content": " PASS\n"}], ""),
        ([{"content": None}], ""),
        ([], ""),
    ],
)
def test_assistant_sends_rolling_prompt_and_parses_response(choices, expected):
    window = TranscriptWindow(max_segments=2)
    for segment in ("Old topic", "Can we ship Friday?", "We need an owner."):
        window.add(segment)

    def respond(request):
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "custom-chat-model"
        assert payload["stream"] is False
        system, user = payload["messages"]
        assert system["role"] == "system"
        assert "25 words" in system["content"]
        assert "Meeting context:\nRelease planning" in system["content"]
        assert user == {
            "role": "user",
            "content": "Recent transcript:\nCan we ship Friday?\nWe need an owner.",
        }
        return httpx.Response(200, json={
            "id": "test-completion",
            "object": "chat.completion",
            "created": 0,
            "model": payload["model"],
            "choices": [
                {
                    "message": {"role": "assistant", **message},
                    "index": index,
                    "finish_reason": "stop",
                }
                for index, message in enumerate(choices)
            ],
        })

    async def run():
        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async with AsyncOpenAI(
            api_key="test", base_url="https://example.test/v1", http_client=http
        ) as client:
            assistant = OpenAIAssistant(client, "custom-chat-model")
            assert await assistant.suggest(" ") == ""
            assert await assistant.suggest(window.text(), "Release planning") == expected

    asyncio.run(run())
