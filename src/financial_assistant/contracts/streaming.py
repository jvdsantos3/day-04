"""Typed streaming contracts for internal events and SSE frames."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

StreamEventType = Literal[
    "message_delta",
    "tool_call",
    "tool_result",
    "final",
    "done",
    "error",
]


class StreamEvent(BaseModel):
    """Internal event shape that maps directly to a named SSE event."""

    event: StreamEventType
    data: dict
    sequence: int | None = None


def format_sse_event(event_name: str, payload: dict | str) -> str:
    """Frame ``payload`` as one named SSE event, splitting multi-line data."""
    if isinstance(payload, dict):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        data = payload

    lines = [f"data: {line}" for line in data.splitlines()] or ["data: "]
    return "\n".join([f"event: {event_name}", *lines]) + "\n\n"


class SseEventFrame:
    """Factory for SSE frames produced from typed stream events."""

    @staticmethod
    def from_stream_event(event: StreamEvent) -> str:
        return format_sse_event(event.event, event.model_dump(mode="json"))
