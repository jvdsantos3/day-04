"""Unit tests for typed streaming/SSE contracts (AHR-SSE-01/AHR-SSE-04)."""

import pytest
from pydantic import ValidationError

from financial_assistant.contracts.agent_response import AgentResponse
from financial_assistant.contracts.streaming import (
    SseEventFrame,
    StreamEvent,
    format_sse_event,
)

pytestmark = pytest.mark.unit


def test_stream_event_accepts_only_spec_allowed_event_names():
    allowed = {"message_delta", "tool_call", "tool_result", "final", "done", "error"}

    events = [StreamEvent(event=name, data={}) for name in allowed]

    assert {event.event for event in events} == allowed
    with pytest.raises(ValidationError):
        StreamEvent(event="progress", data={})


def test_final_stream_event_carries_serialized_agent_response():
    response = AgentResponse(text="Resposta final", action="none", metadata={"source": "test"})

    event = StreamEvent(event="final", data=response.model_dump(mode="json"))

    assert event.event == "final"
    assert event.data["text"] == "Resposta final"
    assert event.data["action"] == "none"
    assert event.data["metadata"] == {"source": "test"}


def test_format_sse_event_supports_named_multiline_string_data():
    frame = format_sse_event("tool_result", "linha 1\nlinha 2")

    assert frame == "event: tool_result\ndata: linha 1\ndata: linha 2\n\n"


def test_sse_event_frame_from_stream_event_json_encodes_payload():
    event = StreamEvent(
        event="tool_result",
        data={"agent": "transacoes", "tool": "create_transaction", "status": "ok"},
        sequence=3,
    )

    frame = SseEventFrame.from_stream_event(event)

    assert frame == (
        'event: tool_result\n'
        'data: {"event":"tool_result","data":{"agent":"transacoes",'
        '"tool":"create_transaction","status":"ok"},"sequence":3}\n\n'
    )
