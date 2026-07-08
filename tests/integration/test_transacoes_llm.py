"""Integration tests for the Transações specialist with real DeepSeek LLM.

These tests exercise ``extract_transaction``, ``categorize`` (LLM fallback) and
``transacoes_node`` against the live model — the only way to validate natural-
language parsing and categorization reliably.

Opt-in only: ``pytest -m llm`` (requires ``DEEPSEEK_API_KEY`` in the environment).
They are intentionally **not** marked ``integration`` so the default gate
(``-m "unit or integration"``) does not hit the API on every run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage

from financial_assistant.agents.orchestrator import get_orchestrator_llm
from financial_assistant.agents.specialists.transacoes import (
    categorize,
    extract_transaction,
    transacoes_node,
)
from financial_assistant.config import get_settings
from financial_assistant.contracts.agent_response import Intent
from financial_assistant.domain.models import BudgetCategory, TransactionType


@pytest.fixture
def llm():
    if not get_settings().deepseek_api_key:
        pytest.skip("DEEPSEEK_API_KEY not set")
    return get_orchestrator_llm()


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


def _find_similar_empty(**kwargs):
    return []


def _recording_create():
    calls: list[dict] = []

    def create(**kwargs):
        calls.append(kwargs)
        return dict(kwargs)

    return create, calls


@pytest.mark.llm
def test_extract_adicione_receita_3000(llm):
    parsed = extract_transaction("Adicione uma receita de 3000 esse mes", llm)

    assert parsed is not None
    assert parsed.type == TransactionType.INCOME
    assert parsed.amount == Decimal("3000")
    assert parsed.description


@pytest.mark.llm
def test_extract_recebi_salario_5000(llm):
    parsed = extract_transaction("recebi 5000 de salário", llm)

    assert parsed is not None
    assert parsed.type == TransactionType.INCOME
    assert parsed.amount == Decimal("5000")
    assert "salár" in parsed.description.lower()


@pytest.mark.llm
def test_extract_gastei_42_almoco(llm):
    parsed = extract_transaction("gastei 42 no almoço", llm)

    assert parsed is not None
    assert parsed.type == TransactionType.EXPENSE
    assert parsed.amount == Decimal("42")
    assert "almo" in parsed.description.lower()


@pytest.mark.llm
def test_extract_gastei_sem_valor_retorna_none(llm):
    parsed = extract_transaction("Gastei um dinheiro no mercado", llm)

    assert parsed is None


@pytest.mark.llm
def test_categorize_almoco_via_llm_sem_chroma(llm):
    category = categorize("almoço", user_id="u1", find_similar=_find_similar_empty, llm=llm)

    assert category == BudgetCategory.PLEASURES


@pytest.mark.llm
def test_registre_receita_3000_sem_categoria(llm):
    create, calls = _recording_create()

    def _find_similar_must_not_be_called(**kwargs):
        raise AssertionError("categorização não deve ser chamada para receitas")

    state = _state("Adicione uma receita de 3000 esse mes", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(
        state, find_similar=_find_similar_must_not_be_called, create=create, llm=llm
    )

    response = result["final_response"]
    assert response.action == "registered"
    assert response.suggested_category is None
    assert len(calls) == 1
    assert calls[0]["type"] == TransactionType.INCOME.value
    assert calls[0]["amount"] == "3000"
    assert calls[0]["category"] is None


@pytest.mark.llm
def test_gastei_almoco_cria_despesa_prazeres(llm):
    create, calls = _recording_create()
    state = _state("gastei 42 no almoço", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(state, find_similar=_find_similar_prazeres, create=create, llm=llm)

    response = result["final_response"]
    assert response.action == "registered"
    assert response.suggested_category == BudgetCategory.PLEASURES
    assert len(calls) == 1
    assert calls[0]["type"] == TransactionType.EXPENSE.value
    assert calls[0]["amount"] == "42"
    assert "almo" in calls[0]["description"].lower()
    assert calls[0]["category"] == BudgetCategory.PLEASURES.value


@pytest.mark.llm
def test_recebi_salario_cria_receita(llm):
    create, calls = _recording_create()

    def _find_similar_must_not_be_called(**kwargs):
        raise AssertionError("categorização não deve ser chamada para receitas")

    state = _state("Recebi R$ 5000 de salário", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(
        state, find_similar=_find_similar_must_not_be_called, create=create, llm=llm
    )

    response = result["final_response"]
    assert response.action == "registered"
    assert len(calls) == 1
    assert calls[0]["type"] == TransactionType.INCOME.value
    assert calls[0]["amount"] == "5000"
    assert calls[0]["category"] is None


@pytest.mark.llm
def test_clarification_when_amount_cannot_be_inferred(llm):
    create, calls = _recording_create()
    state = _state("Gastei um dinheiro no mercado", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(state, create=create, llm=llm)

    response = result["final_response"]
    assert response.action == "none"
    assert calls == []
