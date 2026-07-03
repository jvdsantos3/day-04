"""Unit tests for the Atendimento specialist (T21, CONV-01).

Covers the P1 "plano de gastos" scenario (spec.md AC1): the response must
mention all 5 budget categories with their percentage ranges and spending
examples, grounded via ``query_knowledge`` — no LLM call and no ChromaDB I/O
(both mocked, per Verify: `-m unit`).
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from financial_assistant.agents.specialists import atendimento
from financial_assistant.vector.knowledge_seed import CATEGORY_KNOWLEDGE_DOCS

pytestmark = pytest.mark.unit

CATEGORY_NAMES = [
    "Custos Fixos",
    "Conforto",
    "Investimentos",
    "Conhecimento e Metas",
    "Prazeres",
]

_FIXTURE_DOCS = [
    {"doc_id": doc.doc_id, "document": doc.text, "metadata": {}}
    for doc in CATEGORY_KNOWLEDGE_DOCS
]


class _EchoChatModel:
    """Stands in for the DeepSeek chat model — echoes the grounded prompt back.

    Simulates an LLM that answers strictly from the supplied CONTEXTO, so the
    test proves the retrieved knowledge actually flows into the final answer.
    """

    def invoke(self, messages):
        return AIMessage(content=messages[-1].content)


@pytest.fixture(autouse=True)
def _mock_query_knowledge(monkeypatch):
    calls = {}

    def _fake_query_knowledge(query, n_results=3):
        calls["query"] = query
        calls["n_results"] = n_results
        return _FIXTURE_DOCS

    monkeypatch.setattr(
        "financial_assistant.vector.knowledge_seed.query_knowledge",
        _fake_query_knowledge,
    )
    return calls


def test_answer_plano_de_gastos_mentions_all_five_categories(_mock_query_knowledge):
    response = atendimento.answer("Quero montar um plano de gastos", llm=_EchoChatModel())

    for name in CATEGORY_NAMES:
        assert name in response.text
    assert _mock_query_knowledge["query"] == "Quero montar um plano de gastos"


def test_answer_mentions_percentage_ranges_and_spending_examples():
    response = atendimento.answer("Quero montar um plano de gastos", llm=_EchoChatModel())

    assert "30-40%" in response.text  # Custos Fixos range
    assert "aluguel" in response.text  # Custos Fixos spending example


def test_atendimento_node_sets_final_response(monkeypatch):
    monkeypatch.setattr(atendimento, "get_atendimento_llm", lambda: _EchoChatModel())
    state = {
        "messages": [HumanMessage(content="Quero montar um plano de gastos")],
        "user_id": "u1",
        "session_id": "s1",
        "intent": "explain_budget",
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": [],
        "last_tool_results": None,
        "validation_attempts": 0,
        "final_response": None,
    }

    result = atendimento.atendimento_node(state)

    assert set(result) == {"final_response"}
    for name in CATEGORY_NAMES:
        assert name in result["final_response"].text
