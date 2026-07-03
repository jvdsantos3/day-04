"""Chat router — ``/chat`` page and its SSE endpoint (T29, WEB-05, CHAT-01).

``POST /api/chat`` is the design.md-specified interface (``{message,
session_id}`` -> SSE stream): it runs ``agents.graph.run()`` (T25, which
already persists the turn to ``chat_messages``) and streams the resulting
``AgentResponse`` back as one Server-Sent Event.

Spec-precision gap: design.md's "Reuses" note calls for LangGraph
``astream_events`` for incremental tokens. Every specialist (T21-23) calls
its chat model with a single blocking ``.invoke()``, not a token stream, so
there's nothing incremental to relay yet — that would require reworking
every specialist onto streaming LLM calls, out of scope here. This endpoint
uses genuine SSE framing (``text/event-stream``, one ``data:`` event per
turn) so the wire protocol design.md asks for is in place; upgrading it to
per-token events is a future task once the specialists stream.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from financial_assistant.agents import graph as agent_graph
from financial_assistant.auth.dependencies import get_current_user, get_current_user_api
from financial_assistant.domain.models import User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


class ChatRequest(BaseModel):
    message: str
    session_id: str


def _sse_event(data: str, *, event: str | None = None) -> str:
    """Frame ``data`` as one SSE event, splitting multi-line payloads per spec."""
    lines = [f"data: {line}" for line in data.splitlines()] or ["data: "]
    if event is not None:
        lines.insert(0, f"event: {event}")
    return "\n".join(lines) + "\n\n"


def _stream_turn(user_id: str, session_id: str, message: str) -> Iterator[str]:
    response = agent_graph.run(user_id, session_id, message)
    yield _sse_event(response.model_dump_json())
    yield _sse_event("end", event="done")


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    """Render the chat UI (WEB-05)."""
    return templates.TemplateResponse(request, "chat.html", {"user": user})


@router.post("/api/chat")
def post_chat(
    body: ChatRequest, user: User = Depends(get_current_user_api)
) -> StreamingResponse:
    """Run one turn through the agent graph and stream the reply as SSE (CHAT-01)."""
    return StreamingResponse(
        _stream_turn(str(user.id), body.session_id, body.message),
        media_type="text/event-stream",
    )
