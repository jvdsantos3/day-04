"""Integration tests for the chat SSE endpoint (T29, CHAT-01).

``agents.graph.run`` is monkeypatched — no real LLM/DB graph execution here,
that's already covered by ``tests/integration/test_graph_smoke.py`` (T25).
This file proves the HTTP surface of ``POST /api/chat``: auth guarding
(401, AUTH-06) and that a successful turn comes back as a well-formed SSE
event carrying the ``AgentResponse``.

The old ``GET /chat`` Jinja2 HTML page and its two tests
(``test_chat_page_requires_auth``, ``test_chat_page_renders_for_authenticated_user``)
were removed in T18 along with the route itself — the React SPA now owns
that surface (Vitest coverage lives in ``frontend/src``).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.auth.dependencies import SESSION_COOKIE_NAME
from financial_assistant.auth.service import create_access_token
from financial_assistant.chat import router as chat_router
from financial_assistant.contracts.agent_response import AgentResponse
from financial_assistant.db.session import Base, get_db
from financial_assistant.domain.models import User
from financial_assistant.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client(monkeypatch):
    """``TestClient`` wired to an isolated in-memory SQLite DB, with one seeded user."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestingSession() as db:
        user = User(name="Ana", email="ana@example.com", password_hash="x")
        db.add(user)
        db.commit()
        user_id = str(user.id)

    with TestClient(app) as test_client:
        yield test_client, user_id


def _login_as(test_client: TestClient, user_id: str) -> None:
    test_client.cookies.set(SESSION_COOKIE_NAME, create_access_token(user_id))


def test_chat_endpoint_requires_auth(client):
    """T29's stated Verify: an unauthenticated POST gets 401, not a redirect (AUTH-06)."""
    test_client, _ = client

    response = test_client.post("/api/chat", json={"message": "oi", "session_id": "s1"})

    assert response.status_code == 401


def test_chat_endpoint_streams_the_graph_response_as_sse(client, monkeypatch):
    """CHAT-01: an authenticated turn runs the graph and streams back an SSE event."""
    test_client, user_id = client
    _login_as(test_client, user_id)
    captured = {}

    def fake_run(user_id: str, session_id: str, message: str) -> AgentResponse:
        captured["args"] = (user_id, session_id, message)
        return AgentResponse(text="Olá! Como posso ajudar?")

    monkeypatch.setattr(chat_router.agent_graph, "run", fake_run)

    response = test_client.post(
        "/api/chat", json={"message": "Quero montar um plano de gastos", "session_id": "sess-1"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert captured["args"] == (user_id, "sess-1", "Quero montar um plano de gastos")

    events = [chunk for chunk in response.text.split("\n\n") if chunk]
    data_lines = [line for line in events[0].splitlines() if line.startswith("data: ")]
    payload = json.loads(data_lines[0][len("data: ") :])
    assert payload["text"] == "Olá! Como posso ajudar?"
    assert "event: done" in events[1]
