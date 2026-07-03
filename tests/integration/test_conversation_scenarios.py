"""Integration tests for the spec's 3 literal conversational scenarios (T30-T32).

Each test drives the exact prompt from spec.md's "Cenários conversacionais
reais" through the real, fully-wired graph (``agents.graph.run``, T25) —
orchestrator classification -> specialist -> validator — with only the
outer boundaries mocked (LLM calls, MCP data-fetching functions), same
spirit as ``test_graph_smoke.py`` (T25) and the specialists' own unit tests
(T21-23). Assertions target the exact content spec.md's ACs demand, not
just "some response came back".
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.agents import graph as graph_module
from financial_assistant.agents import orchestrator
from financial_assistant.agents.specialists import atendimento
from financial_assistant.contracts.agent_response import Intent, IntentClassification
from financial_assistant.db.session import Base
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import User
from financial_assistant.vector.knowledge_seed import CATEGORY_KNOWLEDGE_DOCS

CATEGORY_NAMES = [
    "Custos Fixos",
    "Conforto",
    "Investimentos",
    "Conhecimento e Metas",
    "Prazeres",
]

_KNOWLEDGE_DOCS = [
    {"doc_id": doc.doc_id, "document": doc.text, "metadata": {}} for doc in CATEGORY_KNOWLEDGE_DOCS
]


class _EchoChatModel:
    """Stands in for the DeepSeek chat model — echoes the grounded prompt back
    (same fake as ``test_atendimento.py``, proves retrieval flows into the reply)."""

    def invoke(self, messages):
        return AIMessage(content=messages[-1].content)


@pytest.fixture
def graph(monkeypatch):
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
        db.flush()
        seed_budget_targets(db, user.id)
        db.commit()
        user_id = str(user.id)

    return user_id


def _mock_classify_intent(monkeypatch, intent: Intent) -> None:
    monkeypatch.setattr(
        orchestrator, "classify_intent", lambda message: IntentClassification(intent=intent, confidence=0.95)
    )


# --- T30: "Quero montar um plano de gastos" (CONV-01) ------------------------


@pytest.mark.integration
def test_plano_de_gastos_explains_five_categories(graph, monkeypatch):
    user_id = graph
    _mock_classify_intent(monkeypatch, Intent.EXPLAIN_BUDGET)
    monkeypatch.setattr(atendimento, "get_atendimento_llm", lambda: _EchoChatModel())
    monkeypatch.setattr(
        "financial_assistant.vector.knowledge_seed.query_knowledge",
        lambda query, n_results=3: _KNOWLEDGE_DOCS,
    )

    response = graph_module.run(user_id, "sess-plano", "Quero montar um plano de gastos")

    for name in CATEGORY_NAMES:
        assert name in response.text
    assert "30-40%" in response.text  # Custos Fixos range — AC1's "faixas percentuais"
