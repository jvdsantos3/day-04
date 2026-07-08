"""Unit tests for the Transações specialist (T22) — wiring determinístico.

Testes que dependem da qualidade da extração/categorização via LLM ficam em
``tests/integration/test_transacoes_llm.py`` (``pytest -m llm``), usando a
DeepSeek real. Aqui só validamos caminhos que não dependem do modelo:
Chroma como fonte primária de categoria e persistência condicionada ao intent.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from financial_assistant.agents.specialists.transacoes import categorize, transacoes_node
from financial_assistant.contracts.agent_response import Intent
from financial_assistant.domain.models import BudgetCategory

pytestmark = pytest.mark.unit


def _state(message: str, intent: str) -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "user_id": "u1",
        "session_id": "s1",
        "intent": intent,
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": [],
        "last_tool_results": None,
        "validation_attempts": 0,
        "final_response": None,
    }


def _find_similar_prazeres(**kwargs):
    return [{"metadata": {"category": "prazeres"}, "score": 0.91, "source": "category_example"}]


def _recording_create():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return dict(kwargs)

    return create, calls


def test_categorize_delivery_is_prazeres_via_chroma():
    category = categorize("pedido de delivery", user_id="u1", find_similar=_find_similar_prazeres)

    assert category == BudgetCategory.PLEASURES


def test_delivery_question_offers_register_without_persisting():
    create, calls = _recording_create()
    state = _state(
        "Gastei 20 reais num pedido de delivery, em qual categoria essa despesa se encaixa?",
        intent=Intent.CATEGORIZE.value,
    )

    result = transacoes_node(state, find_similar=_find_similar_prazeres, create=create)

    response = result["final_response"]
    assert response.suggested_category == BudgetCategory.PLEASURES
    assert response.action == "offer_register"
    assert calls == []
