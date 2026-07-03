"""Unit tests for the Transações specialist (T22).

Covers the "Registrar transação via chat" story (CHAT-01/02/03) and the
delivery-categorization real scenario (CONV-02) from spec.md. finance-mcp's
``create_transaction`` and chroma-mcp's ``find_similar_transactions`` are
injected as fakes — no DB, no ChromaDB, no LLM call.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from financial_assistant.agents.specialists.transacoes import (
    categorize,
    parse_transaction_message,
    transacoes_node,
)
from financial_assistant.contracts.agent_response import Intent
from financial_assistant.domain.models import BudgetCategory, TransactionType

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


def _find_similar_empty(**kwargs):
    return []


def _recording_create():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return dict(kwargs)

    return create, calls


def test_categorize_delivery_is_prazeres():
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


def test_gastei_cinema_creates_despesa_prazeres():
    create, calls = _recording_create()
    state = _state("Gastei R$ 150 no cinema", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(state, find_similar=_find_similar_prazeres, create=create)

    response = result["final_response"]
    assert response.action == "registered"
    assert response.suggested_category == BudgetCategory.PLEASURES
    assert len(calls) == 1
    assert calls[0]["type"] == TransactionType.EXPENSE.value
    assert calls[0]["amount"] == "150"
    assert calls[0]["category"] == BudgetCategory.PLEASURES.value


def test_recebi_salario_creates_receita_com_categoria_null():
    create, calls = _recording_create()

    def _find_similar_must_not_be_called(**kwargs):
        raise AssertionError("categorização não deve ser chamada para receitas")

    state = _state("Recebi R$ 5000 de salário", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(state, find_similar=_find_similar_must_not_be_called, create=create)

    response = result["final_response"]
    assert response.action == "registered"
    assert response.suggested_category is None
    assert len(calls) == 1
    assert calls[0]["type"] == TransactionType.INCOME.value
    assert calls[0]["amount"] == "5000"
    assert calls[0]["category"] is None


def test_clarification_when_amount_cannot_be_inferred():
    create, calls = _recording_create()
    state = _state("Gastei um dinheiro no mercado", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(state, create=create)

    response = result["final_response"]
    assert response.action == "none"
    assert calls == []


def test_clarification_when_category_cannot_be_inferred():
    create, calls = _recording_create()
    state = _state("Gastei R$ 40 em algo estranho", intent=Intent.REGISTER_TRANSACTION.value)

    result = transacoes_node(state, find_similar=_find_similar_empty, create=create)

    response = result["final_response"]
    assert response.action == "none"
    assert calls == []


def test_parse_transaction_message_returns_none_without_amount():
    assert parse_transaction_message("Gastei um dinheiro no mercado") is None


def test_parse_transaction_message_extracts_income():
    parsed = parse_transaction_message("Recebi R$ 5000 de salário")

    assert parsed.type == TransactionType.INCOME
    assert parsed.amount == 5000
