"""Unit tests for the Orchestrator's intent classification (T20).

Covers the 3 real conversational scenarios from spec.md's "Cenários
conversacionais reais" (CONV-01/02/03) plus the "gastei"/"recebi" pattern,
and the MVP one-specialist-per-turn routing rule (ORCH-01/02). The LLM is
mocked — no real DeepSeek call.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from financial_assistant.agents.orchestrator import (
    AMBIGUITY_CONFIDENCE_THRESHOLD,
    SYSTEM_PROMPT,
    classify_intent,
    orchestrator_node,
    specialist_for_intent,
)
from financial_assistant.contracts.agent_response import Intent, IntentClassification

pytestmark = pytest.mark.unit


class _FakeStructuredModel:
    def __init__(self, classification: IntentClassification) -> None:
        self._classification = classification

    def invoke(self, messages):
        return self._classification


class _FakeChatModel:
    """Stands in for ChatOpenAI's structured-output contract."""

    def __init__(self, classification: IntentClassification) -> None:
        self._classification = classification

    def with_structured_output(self, schema, method=None):
        assert schema is IntentClassification
        # DeepSeek rejects the json_schema-based response_format that
        # with_structured_output defaults to for unrecognized models —
        # classify_intent must pin method="function_calling" (confirmed
        # against the real API).
        assert method == "function_calling"
        return _FakeStructuredModel(self._classification)


def _fake_llm(intent: Intent, confidence: float = 0.9) -> _FakeChatModel:
    return _FakeChatModel(IntentClassification(intent=intent, confidence=confidence))


@pytest.mark.parametrize(
    "message,intent,specialist",
    [
        (
            "Quero montar um plano de gastos",
            Intent.EXPLAIN_BUDGET,
            "atendimento",
        ),
        (
            "Gastei 20 reais num pedido de delivery, em qual categoria "
            "essa despesa se encaixa?",
            Intent.CATEGORIZE,
            "transacoes",
        ),
        (
            "Em quais categorias devo prestar mais atenção ou economizar?",
            Intent.BUDGET_ADVICE,
            "orcamento",
        ),
        (
            "Recebi meu salário de 5000 reais hoje",
            Intent.REGISTER_TRANSACTION,
            "transacoes",
        ),
    ],
)
def test_classify_intent_routes_real_scenarios(message, intent, specialist):
    llm = _fake_llm(intent)

    classification = classify_intent(message, llm=llm)

    assert classification.intent is intent
    assert specialist_for_intent(classification.intent, classification.confidence) == (
        specialist
    )


def test_specialist_for_intent_covers_every_intent():
    for intent in Intent:
        assert specialist_for_intent(intent) in {"atendimento", "transacoes", "orcamento"}


def test_low_confidence_intent_routes_to_atendimento_for_clarification():
    ambiguous_confidence = AMBIGUITY_CONFIDENCE_THRESHOLD - 0.1

    specialist = specialist_for_intent(Intent.REGISTER_TRANSACTION, ambiguous_confidence)

    assert specialist == "atendimento"


def test_system_prompt_mentions_imperative_registration_examples():
    lowered_prompt = SYSTEM_PROMPT.lower()

    assert "registre" in lowered_prompt
    assert "adicione" in lowered_prompt
    assert "despesa" in lowered_prompt
    assert "receita" in lowered_prompt


def test_orchestrator_node_sets_intent_on_state(monkeypatch):
    monkeypatch.setattr(
        "financial_assistant.agents.orchestrator.classify_intent",
        lambda message: IntentClassification(intent=Intent.BUDGET_ADVICE, confidence=0.8),
    )
    state = {
        "messages": [HumanMessage(content="Em quais categorias devo economizar?")],
        "user_id": "u1",
        "session_id": "s1",
        "intent": None,
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": [],
        "last_tool_results": None,
        "validation_attempts": 0,
        "final_response": None,
    }

    result = orchestrator_node(state)

    assert result == {"intent": "budget_advice", "intent_confidence": 0.8}
