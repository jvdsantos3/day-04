"""Unit tests for the Validator node (T24, VAL-01/02/03, CONV-05).

Covers design.md's four Validator checks plus the retry loop
(``MAX_VALIDATION_ATTEMPTS`` = 2, "Validator reject | Retry specialist ≤2"):
``get_balance``/``get_budget_summary`` are injected as fakes — no DB, no
LLM. The spec's own Independent Test for this story ("Mock de resposta com
saldo incorreto; verificar rejeição pelo validador") is
``test_validate_rejects_wrong_balance`` below.
"""

from __future__ import annotations

import pytest

from financial_assistant.agents.validator import (
    MAX_VALIDATION_ATTEMPTS,
    FALLBACK_TEXT,
    validate,
    validator_node,
)
from financial_assistant.contracts.agent_response import AgentResponse

pytestmark = pytest.mark.unit


def _category(
    category: str,
    *,
    status: str = "ok",
    pct: float = 10.0,
    min_pct: float = 0.0,
    max_pct: float = 20.0,
    target_pct: float = 10.0,
    remaining_pct: float = 10.0,
    over_amount: str = "0",
    spent: str = "0",
) -> dict:
    return {
        "category": category,
        "spent": spent,
        "pct": pct,
        "min_pct": min_pct,
        "max_pct": max_pct,
        "target_pct": target_pct,
        "status": status,
        "remaining_pct": remaining_pct,
        "over_amount": over_amount,
    }


def _balance(*, total_income: str = "5000.00", total_expense: str = "3000.00", balance: str = "2000.00") -> dict:
    return {"total_income": total_income, "total_expense": total_expense, "balance": balance}


def _summary(*, categories: list[dict], total_income: str = "5000.00") -> dict:
    return {"month": "2026-07", "total_income": total_income, "has_income": True, "warning": None, "categories": categories}


def _fakes(balance: dict, summary: dict):
    return (lambda **kwargs: balance), (lambda **kwargs: summary)


def _state(
    *,
    final_response,
    validation_attempts: int = 0,
    agent_notes: list[str] | None = None,
    intent: str | None = "budget_advice",
) -> dict:
    return {
        "messages": [],
        "user_id": "u1",
        "session_id": "s1",
        "intent": intent,
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": agent_notes if agent_notes is not None else [],
        "last_tool_results": None,
        "validation_attempts": validation_attempts,
        "final_response": final_response,
    }


# --- Check 1: AgentResponse Pydantic válido (VAL-01) ------------------------


def test_validate_rejects_missing_response():
    result = validate(None, user_id="u1")
    assert result.approved is False


def test_validate_rejects_response_of_wrong_type():
    result = validate("plain string, not a contract", user_id="u1")
    assert result.approved is False


def test_validate_accepts_raw_dict_matching_the_contract():
    result = validate({"text": "Olá, tudo bem com você?"}, user_id="u1")
    assert result.approved is True


def test_validate_rejects_raw_dict_violating_the_contract():
    result = validate({"text": "oi", "action": "invalid-action-not-in-literal"}, user_id="u1")
    assert result.approved is False


# --- Check 2/CONV-05: R$ e % conferem com o banco (VAL-03) -------------------


def test_validate_approves_consistent_balance_mention():
    balance = _balance(balance="2000.00")
    summary = _summary(categories=[])
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(text="Seu saldo atual é de R$ 2000.00.")
    result = validate(
        response,
        user_id="u1",
        intent="budget_advice",
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )

    assert result.approved is True


def test_validate_rejects_wrong_balance():
    """Spec's Independent Test: mocked response with an incorrect saldo is rejected."""
    balance = _balance(balance="2000.00")
    summary = _summary(categories=[])
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(text="Seu saldo atual é de R$ 9999.00.")
    result = validate(
        response,
        user_id="u1",
        intent="budget_advice",
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )

    assert result.approved is False
    assert "VAL-03" in result.reason


def test_validate_rejects_wrong_budget_percentage():
    balance = _balance()
    summary = _summary(categories=[_category("prazeres", pct=30.0, max_pct=40.0)])
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(text="Você já usou 99.0% da faixa de prazeres.")
    result = validate(
        response,
        user_id="u1",
        intent="budget_advice",
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )

    assert result.approved is False
    assert "CONV-05" in result.reason


def test_validate_approves_correct_budget_percentage():
    balance = _balance()
    summary = _summary(categories=[_category("prazeres", pct=30.0, max_pct=40.0)])
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(text="Você já usou 30.0% da faixa de prazeres (até 40.0%).")
    result = validate(
        response,
        user_id="u1",
        intent="budget_advice",
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )

    assert result.approved is True


def test_validate_approves_just_registered_transaction_amount():
    """A confirmation citing the amount it just persisted isn't an inconsistency (T22 flow)."""
    balance = _balance()
    summary = _summary(categories=[])
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(
        text='Registrei uma despesa de R$ 20 na categoria prazeres: "cinema".',
        action="registered",
        metadata={"transaction": {"amount": "20"}},
    )
    result = validate(
        response,
        user_id="u1",
        intent="register_transaction",
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )

    assert result.approved is True


def test_validate_skips_financial_check_for_explain_budget_illustrative_figures():
    """CONV-01: Atendimento's plan explanation cites illustrative %/R$ examples that
    have nothing to do with the user's real data ("sem exigir transações
    pré-existentes") — found live against the real DeepSeek API, where a
    "quero montar um plano de gastos" answer walking through an example income
    of R$ 5.000 was wrongly rejected before this intent scoping existed.
    """
    balance = _balance(balance="0")
    summary = _summary(categories=[], total_income="0")
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(
        text=(
            "Custos Fixos (30-40% da renda mensal). Por exemplo, se sua renda for "
            "R$ 5.000, você pode reservar 35% (R$ 1.750) para Custos Fixos."
        )
    )
    result = validate(
        response,
        user_id="u1",
        intent="explain_budget",
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )

    assert result.approved is True


def test_validate_rejects_wrong_balance_even_when_intent_is_none():
    """Without a known intent (e.g. a raw dict/plain call), the check still runs —
    only the explicitly-safe intents (explain_budget) are exempted."""
    balance = _balance(balance="2000.00")
    summary = _summary(categories=[])
    get_balance, get_budget_summary = _fakes(balance, summary)

    response = AgentResponse(text="Seu saldo atual é de R$ 9999.00.")
    result = validate(response, user_id="u1", get_balance=get_balance, get_budget_summary=get_budget_summary)

    assert result.approved is False


# --- Check 3: categoria válida ------------------------------------------------


def test_validate_rejects_invalid_category():
    response = AgentResponse.model_construct(
        text="Isso se encaixa em outra categoria.",
        suggested_category="categoria_inexistente",
        action="none",
        metadata={},
    )
    result = validate(response, user_id="u1")
    assert result.approved is False


def test_validate_accepts_valid_category():
    response = AgentResponse(text="Isso se encaixa em prazeres.", suggested_category="prazeres")
    result = validate(response, user_id="u1")
    assert result.approved is True


# --- Check 4: não vazia e PT-BR -----------------------------------------------


def test_validate_rejects_empty_text():
    response = AgentResponse(text="   ")
    result = validate(response, user_id="u1")
    assert result.approved is False


def test_validate_rejects_non_portuguese_text():
    response = AgentResponse(text="Your balance looks fine, thank you very much for asking today.")
    result = validate(response, user_id="u1")
    assert result.approved is False


# --- Retry loop: rejeição -> retry specialist (max 2) -------------------------


def test_validator_node_approves_and_advances_attempts():
    state = _state(final_response=AgentResponse(text="Olá, como você está?"), validation_attempts=0)
    update = validator_node(state)
    assert update == {"validation_attempts": 1}


def test_validator_node_rejects_and_signals_retry_below_max():
    balance = _balance(balance="2000.00")
    summary = _summary(categories=[])
    get_balance, get_budget_summary = _fakes(balance, summary)
    state = _state(final_response=AgentResponse(text="Seu saldo é R$ 9999.00."), validation_attempts=0)

    update = validator_node(state, get_balance=get_balance, get_budget_summary=get_budget_summary)

    assert update["validation_attempts"] == 1
    assert update["final_response"] is None
    assert len(update["agent_notes"]) == 1


def test_validator_node_falls_back_after_max_attempts():
    balance = _balance(balance="2000.00")
    summary = _summary(categories=[])
    get_balance, get_budget_summary = _fakes(balance, summary)
    state = _state(
        final_response=AgentResponse(text="Seu saldo é R$ 9999.00."),
        validation_attempts=MAX_VALIDATION_ATTEMPTS - 1,
    )

    update = validator_node(state, get_balance=get_balance, get_budget_summary=get_budget_summary)

    assert update["validation_attempts"] == MAX_VALIDATION_ATTEMPTS
    assert update["final_response"] == AgentResponse(text=FALLBACK_TEXT)
