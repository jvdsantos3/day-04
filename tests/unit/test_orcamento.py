"""Unit tests for the Orçamento specialist (T23, BUD-03/CONV-03/CONV-04).

Covers the third real conversational scenario from spec.md ("Em quais
categorias devo prestar mais atenção ou economizar?"): the specialist must
invoke ``get_budget_summary`` (mocked here, per Verify: `-m unit`), then
- CONV-03: list categories over their faixa máxima or with a tight remaining
  margin, worst first;
- CONV-04: with no income recorded for the month, orient the user to
  register income first instead of computing percentages.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from financial_assistant.agents.specialists import orcamento
from mcp_servers.finance.server import get_budget_summary as finance_mcp_get_budget_summary

pytestmark = pytest.mark.unit


def _category(
    category: str,
    *,
    status: str,
    pct: float,
    max_pct: float,
    remaining_pct: float,
    over_amount: str = "0",
    spent: str = "0",
    min_pct: float = 0.0,
    target_pct: float = 0.0,
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


def _summary(*, has_income: bool, categories: list[dict], warning: str | None = None) -> dict:
    return {
        "month": "2026-07",
        "total_income": "10000" if has_income else "0",
        "has_income": has_income,
        "warning": warning,
        "categories": categories,
    }


def test_get_budget_summary_tool_is_finance_mcp_tool():
    """The specialist's tool is finance-mcp's get_budget_summary, not a reimplementation."""
    assert orcamento._get_budget_summary is finance_mcp_get_budget_summary


# --- CONV-03: categories over faixa or with tight margin -----------------------


def test_budget_advice_over_budget_categories():
    summary = _summary(
        has_income=True,
        categories=[
            _category(
                "custos_fixos",
                status="alerta",
                pct=50.0,
                max_pct=40.0,
                remaining_pct=-10.0,
                over_amount="1000",
            ),
            _category("conforto", status="ok", pct=10.0, max_pct=20.0, remaining_pct=10.0),
        ],
    )

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary
    )

    assert "custos_fixos" in response.text
    assert "50.0%" in response.text
    assert "1000" in response.text  # over_amount cited
    assert "conforto" not in response.text  # ok and outside the tight-margin band


def test_budget_advice_prioritizes_worst_margin_first():
    """Multiple flagged categories are listed worst (most negative) margin first."""
    summary = _summary(
        has_income=True,
        categories=[
            _category(
                "conforto",
                status="alerta",
                pct=25.0,
                max_pct=20.0,
                remaining_pct=-5.0,
                over_amount="500",
            ),
            _category(
                "custos_fixos",
                status="alerta",
                pct=60.0,
                max_pct=40.0,
                remaining_pct=-20.0,
                over_amount="2000",
            ),
        ],
    )

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary
    )

    assert response.text.index("custos_fixos") < response.text.index("conforto")


def test_budget_advice_flags_tight_margin_category_not_yet_over():
    """A category within the tight-margin band (but not yet 'alerta') is still flagged."""
    summary = _summary(
        has_income=True,
        categories=[
            _category("investimentos", status="ok", pct=17.0, max_pct=20.0, remaining_pct=3.0),
            _category("conforto", status="ok", pct=10.0, max_pct=20.0, remaining_pct=10.0),
        ],
    )

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary
    )

    assert "investimentos" in response.text
    assert "conforto" not in response.text


def test_budget_advice_all_categories_ok_returns_positive_message():
    summary = _summary(
        has_income=True,
        categories=[
            _category("custos_fixos", status="ok", pct=35.0, max_pct=40.0, remaining_pct=5.1),
        ],
    )

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary
    )

    assert response.text == orcamento.NO_ATTENTION_TEXT


# --- BUD-03 AC3: "como está meu orçamento?" -> unconditional 5-category summary --


def test_budget_advice_full_summary_lists_every_category_even_when_ok():
    """"Como está meu orçamento?" gets every category, not just flagged ones (BUD-03 AC3)."""
    summary = _summary(
        has_income=True,
        categories=[
            _category("custos_fixos", status="alerta", pct=50.0, max_pct=40.0, remaining_pct=-10.0, over_amount="1000", spent="5000", min_pct=30.0),
            _category("conforto", status="ok", pct=10.0, max_pct=20.0, remaining_pct=10.0, spent="1000", min_pct=15.0),
        ],
    )

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary, message="Como está meu orçamento?"
    )

    # Both categories present — unlike the prioritized CONV-03 answer, "conforto" isn't dropped.
    assert "custos_fixos" in response.text
    assert "conforto" in response.text
    assert "gasto R$ 5000" in response.text
    assert "50.0%" in response.text
    assert "status alerta" in response.text
    assert "status ok" in response.text


def test_budget_advice_full_summary_no_ceiling_category_shows_open_ended_faixa():
    summary = _summary(
        has_income=True,
        categories=[_category("prazeres", status="ok", pct=8.0, max_pct=100.0, remaining_pct=92.0, min_pct=5.0)],
    )

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary, message="como anda meu orçamento"
    )

    assert "faixa ≥5%" in response.text


def test_budget_advice_default_message_keeps_prioritized_conv03_behavior():
    """Without a message (or one that doesn't ask for a summary), CONV-03's
    prioritized-only answer is unchanged — this is the default for existing callers."""
    summary = _summary(
        has_income=True,
        categories=[
            _category("custos_fixos", status="alerta", pct=50.0, max_pct=40.0, remaining_pct=-10.0),
            _category("conforto", status="ok", pct=10.0, max_pct=20.0, remaining_pct=10.0),
        ],
    )

    response = orcamento.budget_advice("u1", "2026-07", get_summary=lambda **kwargs: summary)

    assert "custos_fixos" in response.text
    assert "conforto" not in response.text


# --- CONV-04: no income base -----------------------------------------------------


def test_budget_advice_no_income_orients_to_register_income_first():
    summary = _summary(has_income=False, categories=[], warning="sem receita base")

    response = orcamento.budget_advice(
        "u1", "2026-07", get_summary=lambda **kwargs: summary
    )

    assert response.text == orcamento.NO_INCOME_ADVICE
    assert "receita" in response.text.lower()


def test_budget_advice_no_income_does_not_call_category_analysis(monkeypatch):
    summary = _summary(has_income=False, categories=[])
    monkeypatch.setattr(
        orcamento,
        "_prioritized_categories",
        lambda categories: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    orcamento.budget_advice("u1", "2026-07", get_summary=lambda **kwargs: summary)


# --- Node wiring -----------------------------------------------------------------


def test_orcamento_node_passes_user_id_and_sets_final_response():
    summary = _summary(
        has_income=True,
        categories=[
            _category(
                "custos_fixos",
                status="alerta",
                pct=50.0,
                max_pct=40.0,
                remaining_pct=-10.0,
                over_amount="1000",
            ),
        ],
    )
    seen = {}

    def _fake_get_summary(**kwargs):
        seen.update(kwargs)
        return summary

    state = {
        "messages": [HumanMessage(content="Em quais categorias devo economizar?")],
        "user_id": "u1",
        "session_id": "s1",
        "intent": "budget_advice",
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": [],
        "last_tool_results": None,
        "validation_attempts": 0,
        "final_response": None,
    }

    result = orcamento.orcamento_node(state, get_summary=_fake_get_summary)

    assert set(result) == {"final_response"}
    assert "custos_fixos" in result["final_response"].text
    assert seen["user_id"] == "u1"


def test_orcamento_node_routes_summary_question_to_full_summary():
    summary = _summary(
        has_income=True,
        categories=[
            _category("custos_fixos", status="alerta", pct=50.0, max_pct=40.0, remaining_pct=-10.0),
            _category("conforto", status="ok", pct=10.0, max_pct=20.0, remaining_pct=10.0),
        ],
    )
    state = {
        "messages": [HumanMessage(content="Como está meu orçamento?")],
        "user_id": "u1",
        "session_id": "s1",
        "intent": "budget_advice",
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": [],
        "last_tool_results": None,
        "validation_attempts": 0,
        "final_response": None,
    }

    result = orcamento.orcamento_node(state, get_summary=lambda **kwargs: summary)

    assert "custos_fixos" in result["final_response"].text
    assert "conforto" in result["final_response"].text  # unconditional — not dropped
