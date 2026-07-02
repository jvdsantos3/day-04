"""Unit tests for the Pydantic contracts (T11).

Derived from spec ACs:

- VAL-01: creating an expense (``despesa``) without a ``category`` is rejected.
- VAL-02: creating an income (``receita``) with a ``category`` is rejected.
- CHAT-02: the router/specialist contracts (``IntentClassification``,
  ``AgentResponse``) accept well-formed payloads and reject malformed ones
  (unknown intent, out-of-range confidence).

Also covers the ``budget.py`` contracts building straight from
``BudgetService``'s dataclasses (T10 dependency).
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from financial_assistant.contracts.agent_response import (
    AgentResponse,
    Intent,
    IntentClassification,
)
from financial_assistant.contracts.budget import BudgetSummary, CategoryStatus
from financial_assistant.contracts.transaction import TransactionCreate
from financial_assistant.domain.models import BudgetCategory, TransactionType
from financial_assistant.domain.services.budget_service import (
    BudgetSummary as BudgetSummaryModel,
)
from financial_assistant.domain.services.budget_service import CategoryBudget

pytestmark = pytest.mark.unit


# --- TransactionCreate: VAL-01 / VAL-02 ---------------------------------------


def test_expense_with_category_is_valid():
    transaction = TransactionCreate(
        date=date(2026, 7, 15),
        description="Aluguel",
        type=TransactionType.EXPENSE,
        amount=Decimal("1500"),
        category=BudgetCategory.FIXED,
    )

    assert transaction.category is BudgetCategory.FIXED


def test_income_without_category_is_valid():
    transaction = TransactionCreate(
        date=date(2026, 7, 10),
        description="Salário",
        type=TransactionType.INCOME,
        amount=Decimal("10000"),
    )

    assert transaction.category is None


def test_expense_without_category_is_rejected():
    with pytest.raises(ValidationError, match="obrigatório"):
        TransactionCreate(
            date=date(2026, 7, 15),
            description="Aluguel",
            type=TransactionType.EXPENSE,
            amount=Decimal("1500"),
        )


def test_income_with_category_is_rejected():
    with pytest.raises(ValidationError, match="não é permitido"):
        TransactionCreate(
            date=date(2026, 7, 10),
            description="Salário",
            type=TransactionType.INCOME,
            amount=Decimal("10000"),
            category=BudgetCategory.FIXED,
        )


def test_non_positive_amount_is_rejected():
    with pytest.raises(ValidationError):
        TransactionCreate(
            date=date(2026, 7, 10),
            description="Salário",
            type=TransactionType.INCOME,
            amount=Decimal("0"),
        )


# --- budget.py: mirrors BudgetService's shapes --------------------------------


def test_category_status_builds_from_category_budget_dataclass():
    category_budget = CategoryBudget(
        category=BudgetCategory.FIXED,
        spent=Decimal("5000"),
        pct=50.0,
        min_pct=30.0,
        max_pct=40.0,
        target_pct=35.0,
        status="alerta",
        remaining_pct=-10.0,
        over_amount=Decimal("1000"),
    )

    status = CategoryStatus.model_validate(category_budget)

    assert status.category is BudgetCategory.FIXED
    assert status.status == "alerta"
    assert status.over_amount == Decimal("1000")


def test_budget_summary_builds_from_budget_summary_dataclass():
    domain_summary = BudgetSummaryModel(
        month="2026-07",
        total_income=Decimal("10000"),
        has_income=True,
        warning=None,
        categories=[
            CategoryBudget(
                category=BudgetCategory.PLEASURES,
                spent=Decimal("200"),
                pct=2.0,
                min_pct=5.0,
                max_pct=100.0,
                target_pct=10.0,
                status="ok",
                remaining_pct=98.0,
                over_amount=Decimal("0"),
            )
        ],
    )

    summary = BudgetSummary.model_validate(domain_summary)

    assert summary.month == "2026-07"
    assert summary.has_income is True
    assert len(summary.categories) == 1
    assert summary.categories[0].category is BudgetCategory.PLEASURES


def test_category_status_rejects_unknown_status_literal():
    with pytest.raises(ValidationError):
        CategoryStatus(
            category=BudgetCategory.FIXED,
            spent=Decimal("100"),
            pct=1.0,
            min_pct=0.0,
            max_pct=10.0,
            target_pct=5.0,
            status="pendente",  # not "ok" / "alerta"
            remaining_pct=9.0,
            over_amount=Decimal("0"),
        )


# --- agent_response.py: CHAT-02 -----------------------------------------------


def test_intent_classification_accepts_known_intent_and_confidence():
    classification = IntentClassification(
        intent=Intent.REGISTER_TRANSACTION, confidence=0.92
    )

    assert classification.intent is Intent.REGISTER_TRANSACTION
    assert classification.confidence == pytest.approx(0.92)


def test_intent_classification_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        IntentClassification(intent=Intent.BUDGET_ADVICE, confidence=1.5)


def test_intent_classification_rejects_unknown_intent():
    with pytest.raises(ValidationError):
        IntentClassification(intent="fazer_cafe", confidence=0.5)


def test_agent_response_defaults_to_no_action_and_empty_metadata():
    response = AgentResponse(text="Você gastou 50% em Custos Fixos este mês.")

    assert response.action == "none"
    assert response.metadata == {}
    assert response.suggested_category is None


def test_agent_response_accepts_offer_register_with_suggested_category():
    response = AgentResponse(
        text="Isso parece um gasto em Prazeres. Deseja registrar?",
        suggested_category=BudgetCategory.PLEASURES,
        action="offer_register",
        metadata={"amount": "150.00"},
    )

    assert response.suggested_category is BudgetCategory.PLEASURES
    assert response.action == "offer_register"


def test_agent_response_rejects_unknown_action():
    with pytest.raises(ValidationError):
        AgentResponse(text="ok", action="pendente")
