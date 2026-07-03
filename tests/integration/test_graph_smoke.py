"""Integration smoke tests for the wired agent graph (T25, ORCH-01).

Exercises ``agents.graph.run()`` end-to-end against an isolated in-memory
SQLite DB, with every LLM/MCP boundary mocked (no DeepSeek, no ChromaDB, no
real finance-mcp session) — same spirit as ``tests/integration/test_mcp.py``.
Covers:

- orchestrator -> specialist -> validator -> END on an approved reply;
- validator -> orchestrator retry, bounded to
  ``validator.MAX_VALIDATION_ATTEMPTS`` (2), falling back instead of looping
  forever when the specialist keeps producing an inconsistent reply;
- ``chat_messages`` persistence for both sides of the turn (spec.md "Camada
  2 — SQLite — histórico durável").
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.agents import graph as graph_module
from financial_assistant.agents import orchestrator
from financial_assistant.agents import validator as validator_module
from financial_assistant.agents.specialists import orcamento
from financial_assistant.contracts.agent_response import Intent, IntentClassification
from financial_assistant.db.session import Base
from financial_assistant.domain.models import ChatMessage, User

pytestmark = pytest.mark.integration


def _summary(*, pct: float, max_pct: float, over_amount: str) -> dict:
    return {
        "month": "2026-07",
        "total_income": "5000.00",
        "has_income": True,
        "warning": None,
        "categories": [
            {
                "category": "custos_fixos",
                "spent": "2500.00",
                "pct": pct,
                "min_pct": 30.0,
                "max_pct": max_pct,
                "target_pct": 35.0,
                "status": "alerta",
                "remaining_pct": max_pct - pct,
                "over_amount": over_amount,
            }
        ],
    }


_CONSISTENT_SUMMARY = _summary(pct=50.0, max_pct=40.0, over_amount="500.00")
_BALANCE = {"total_income": "5000.00", "total_expense": "2500.00", "balance": "2500.00"}


@pytest.fixture
def db_session(monkeypatch):
    """Wire ``graph.SessionLocal`` to an isolated in-memory SQLite DB with one seeded user."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(graph_module, "SessionLocal", testing_session)

    with testing_session() as db:
        user = User(name="Ana", email="ana@example.com", password_hash="x")
        db.add(user)
        db.commit()
        user_id = str(user.id)

    return testing_session, user_id


@pytest.fixture
def budget_advice_intent(monkeypatch):
    """Route every turn to the Orçamento specialist (mocked LLM classification)."""
    calls = {"n": 0}

    def fake_classify(message: str) -> IntentClassification:
        calls["n"] += 1
        return IntentClassification(intent=Intent.BUDGET_ADVICE, confidence=0.9)

    monkeypatch.setattr(orchestrator, "classify_intent", fake_classify)
    return calls


def test_graph_approves_a_consistent_specialist_reply(db_session, budget_advice_intent, monkeypatch):
    """orchestrator -> orcamento -> validator -> END when the reply checks out (ORCH-01)."""
    testing_session, user_id = db_session
    monkeypatch.setattr(orcamento, "_get_budget_summary", lambda **kwargs: _CONSISTENT_SUMMARY)
    monkeypatch.setattr(validator_module, "_get_balance", lambda **kwargs: _BALANCE)
    monkeypatch.setattr(validator_module, "_get_budget_summary", lambda **kwargs: _CONSISTENT_SUMMARY)

    response = graph_module.run(user_id, "sess-1", "Em quais categorias devo economizar?")

    assert "custos_fixos" in response.text
    assert budget_advice_intent["n"] == 1  # approved on the first pass, no retry

    with testing_session() as db:
        messages = db.query(ChatMessage).filter_by(session_id="sess-1").order_by(ChatMessage.role).all()
    roles_and_content = {(m.role, m.content) for m in messages}
    assert ("user", "Em quais categorias devo economizar?") in roles_and_content
    assert any(role == "assistant" and content == response.text for role, content in roles_and_content)


def test_graph_retries_then_falls_back_after_max_attempts(db_session, budget_advice_intent, monkeypatch):
    """validator rejects an inconsistent reply, retries <=2x, then returns the fallback (VAL-03)."""
    testing_session, user_id = db_session
    inconsistent_summary = _summary(pct=1.0, max_pct=40.0, over_amount="999.00")
    monkeypatch.setattr(orcamento, "_get_budget_summary", lambda **kwargs: _CONSISTENT_SUMMARY)
    monkeypatch.setattr(validator_module, "_get_balance", lambda **kwargs: _BALANCE)
    # Validator checks against a different (inconsistent) summary -> always rejects.
    monkeypatch.setattr(validator_module, "_get_budget_summary", lambda **kwargs: inconsistent_summary)

    response = graph_module.run(user_id, "sess-2", "Em quais categorias devo economizar?")

    assert response.text == validator_module.FALLBACK_TEXT
    assert budget_advice_intent["n"] == validator_module.MAX_VALIDATION_ATTEMPTS

    with testing_session() as db:
        messages = db.query(ChatMessage).filter_by(session_id="sess-2").all()
    assert len(messages) == 2  # one turn persisted: user message + final (fallback) reply
    assert {m.role for m in messages} == {"user", "assistant"}
