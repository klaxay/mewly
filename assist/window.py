"""Keep the newest transcript segments in arrival order."""

from collections import deque


class TranscriptWindow:
    def __init__(self, max_segments: int = 12) -> None:
        if max_segments < 1:
            raise ValueError("max_segments must be positive")
        self._segments: deque[str] = deque(maxlen=max_segments)

    def add(self, text: str) -> None:
        if segment := text.strip():
            self._segments.append(segment)

    def text(self) -> str:
        return "\n".join(self._segments)
