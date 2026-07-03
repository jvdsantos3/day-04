"""Integration tests for the spec's 3 literal conversational scenarios (T30-T32).

Each test drives the exact prompt from spec.md's "Cenários conversacionais
reais" through the real, fully-wired graph (``agents.graph.run``, T25) —
orchestrator classification -> specialist -> validator — with only the
outer boundaries mocked (LLM calls, MCP data-fetching functions), same
spirit as ``test_graph_smoke.py`` (T25) and the specialists' own unit tests
(T21-23). Assertions target the exact content spec.md's ACs demand, not
just "some response came back".

``@pytest.mark.llm`` tests hit the real DeepSeek API (opt-in, `-m llm`,
deselected from the default `-m "unit or integration"` gate) — these exist
because the mocked-LLM tests above can't catch a *classification* mistake by
the real model. One is included here on purpose: CONV-02's exact prompt
contains both a ``register_transaction`` marker ("gastei") and a
``categorize`` marker ("qual categoria"/"se encaixa"), and the real DeepSeek
model picked the wrong one before ``orchestrator.SYSTEM_PROMPT`` was fixed
(see `.specs/STATE.md`'s "Validação ao vivo pós-T29" note) — this test locks
that fix in as a regression guard.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.agents import graph as graph_module
from financial_assistant.agents import orchestrator
from financial_assistant.agents import validator as validator_module
from financial_assistant.agents.specialists import atendimento, orcamento, transacoes
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


# --- T31: delivery categorization, no auto-register (CONV-02) ----------------

_DELIVERY_MESSAGE = (
    "Gastei 20 reais num pedido de delivery, em qual categoria essa despesa se encaixa?"
)


@pytest.mark.integration
def test_delivery_categorization_prazeres(graph, monkeypatch):
    user_id = graph
    _mock_classify_intent(monkeypatch, Intent.CATEGORIZE)
    create_calls = []
    monkeypatch.setattr(
        transacoes,
        "_find_similar_transactions",
        lambda **kwargs: [{"metadata": {"category": "prazeres"}, "score": 0.91}],
    )
    monkeypatch.setattr(
        transacoes, "_create_transaction", lambda **kwargs: create_calls.append(kwargs)
    )

    response = graph_module.run(user_id, "sess-delivery", _DELIVERY_MESSAGE)

    assert response.suggested_category == "prazeres"
    assert response.action == "offer_register"
    assert not create_calls  # CONV-02: never persists without confirmation


@pytest.mark.llm
def test_delivery_categorization_prazeres_real_deepseek(graph):
    """Regression guard: the real model must classify this as categorize, not
    register_transaction, despite the message containing both markers ("gastei"
    and "qual categoria"/"se encaixa") — see module docstring."""
    user_id = graph

    response = graph_module.run(user_id, "sess-delivery-llm", _DELIVERY_MESSAGE)

    assert response.suggested_category == "prazeres"
    assert response.action == "offer_register"


# --- T32: "Em quais categorias devo economizar?" (CONV-03) -------------------


def _unbalanced_summary() -> dict:
    return {
        "month": "2026-07",
        "total_income": "5000.00",
        "has_income": True,
        "warning": None,
        "categories": [
            {
                "category": "custos_fixos",
                "spent": "2500.00",
                "pct": 50.0,
                "min_pct": 30.0,
                "max_pct": 40.0,
                "target_pct": 35.0,
                "status": "alerta",
                "remaining_pct": -10.0,
                "over_amount": "500.00",
            },
            {
                "category": "conforto",
                "spent": "500.00",
                "pct": 10.0,
                "min_pct": 15.0,
                "max_pct": 20.0,
                "target_pct": 17.0,
                "status": "ok",
                "remaining_pct": 10.0,
                "over_amount": "0",
            },
        ],
    }


@pytest.mark.integration
def test_economizar_categories_advice(graph, monkeypatch):
    user_id = graph
    _mock_classify_intent(monkeypatch, Intent.BUDGET_ADVICE)
    summary = _unbalanced_summary()
    monkeypatch.setattr(orcamento, "_get_budget_summary", lambda **kwargs: summary)
    monkeypatch.setattr(
        validator_module,
        "_get_balance",
        lambda **kwargs: {"total_income": "5000.00", "total_expense": "3000.00", "balance": "2000.00"},
    )
    monkeypatch.setattr(validator_module, "_get_budget_summary", lambda **kwargs: summary)

    response = graph_module.run(
        user_id, "sess-economizar", "Em quais categorias devo prestar mais atenção ou economizar?"
    )

    assert "custos_fixos" in response.text
    assert "conforto" not in response.text  # within faixa, not flagged
