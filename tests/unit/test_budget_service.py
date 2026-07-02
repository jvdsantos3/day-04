"""Unit tests for BudgetService (T10).

Derived from spec ACs, not the implementation:

- BUD-01: percentages are of the month's total income; income/expenses outside
  the month are excluded; every access is scoped to ``user_id`` (AD-002).
- BUD-02: a category that exceeds its faixa máxima is flagged ``"alerta"`` with
  the category, current %, faixa alvo and the excess amount (``over_amount``).
- BUD-03: the summary covers the five categories with spend, %, faixa and
  status ok/alerta.
- CONV-03: ``remaining_pct`` (max_pct − pct) exposes the tightest margin.
- CONV-04 / action 4: with no income the summary carries ``has_income=False``
  and the ``"sem receita base"`` warning instead of percentages.

The core fixture is intentionally *desbalanceada*: on R$ 10.000 income, Custos
Fixos is at 50% (over its 40% ceiling → alerta) and Prazeres at 2% (below its
5% floor but never alerted, since its max is open-ended).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from financial_assistant.db.session import Base
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
    User,
)
from financial_assistant.domain.services.budget_service import (
    NO_INCOME_WARNING,
    BudgetService,
)

pytestmark = pytest.mark.unit

MONTH = "2026-07"


@pytest.fixture
def session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess
    Base.metadata.drop_all(engine)


@pytest.fixture
def service(session):
    return BudgetService(session)


def _make_user(session, email: str = "ana@example.com") -> uuid.UUID:
    user = User(name="Ana", email=email, password_hash="x")
    session.add(user)
    session.flush()
    seed_budget_targets(session, user.id)
    return user.id


def _income(session, user_id, amount, *, when=date(2026, 7, 10)):
    session.add(
        Transaction(
            user_id=user_id,
            date=when,
            description="Salário",
            type=TransactionType.INCOME,
            amount=Decimal(amount),
            category=None,
        )
    )


def _expense(session, user_id, category, amount, *, when=date(2026, 7, 15)):
    session.add(
        Transaction(
            user_id=user_id,
            date=when,
            description=f"Gasto {category.value}",
            type=TransactionType.EXPENSE,
            amount=Decimal(amount),
            category=category,
        )
    )


@pytest.fixture
def unbalanced_user(session):
    """R$ 10.000 income; Custos Fixos 50% (over max), Prazeres 2% (under min).

    Conforto sits inside its faixa (10% of 15–20%) as the ok/in-range control.
    """
    user_id = _make_user(session)
    _income(session, user_id, "10000")
    _expense(session, user_id, BudgetCategory.FIXED, "5000")  # 50%
    _expense(session, user_id, BudgetCategory.COMFORT, "1000")  # 10%
    _expense(session, user_id, BudgetCategory.PLEASURES, "200")  # 2%
    session.flush()
    return user_id


def _by_category(summary):
    return {c.category: c for c in summary.categories}


# --- BUD-01: percentages over monthly income ---------------------------------


def test_percentages_are_computed_over_total_monthly_income(service, unbalanced_user):
    summary = service.get_summary(unbalanced_user, MONTH)

    assert summary.total_income == Decimal("10000")
    assert summary.has_income is True
    assert summary.warning is None

    cats = _by_category(summary)
    assert cats[BudgetCategory.FIXED].pct == pytest.approx(50.0)
    assert cats[BudgetCategory.COMFORT].pct == pytest.approx(10.0)
    assert cats[BudgetCategory.PLEASURES].pct == pytest.approx(2.0)


def test_income_and_expenses_outside_the_month_are_excluded(service, session):
    user_id = _make_user(session)
    _income(session, user_id, "10000", when=date(2026, 7, 5))
    _income(session, user_id, "99999", when=date(2026, 6, 30))  # previous month
    _expense(session, user_id, BudgetCategory.FIXED, "4000", when=date(2026, 7, 20))
    _expense(session, user_id, BudgetCategory.FIXED, "8000", when=date(2026, 8, 1))
    session.flush()

    summary = service.get_summary(user_id, MONTH)

    assert summary.total_income == Decimal("10000")  # June income excluded
    assert _by_category(summary)[BudgetCategory.FIXED].spent == Decimal("4000")


def test_summary_is_scoped_to_the_requested_user(service, session):
    user_a = _make_user(session, email="a@example.com")
    user_b = _make_user(session, email="b@example.com")
    _income(session, user_a, "10000")
    _expense(session, user_a, BudgetCategory.FIXED, "5000")
    _income(session, user_b, "50000")
    _expense(session, user_b, BudgetCategory.FIXED, "1000")
    session.flush()

    summary = service.get_summary(user_a, MONTH)

    assert summary.total_income == Decimal("10000")  # not affected by user B
    assert _by_category(summary)[BudgetCategory.FIXED].spent == Decimal("5000")


# --- BUD-02: over-max category is flagged with the excess ---------------------


def test_category_over_max_is_flagged_alerta_with_faixa_and_excess(
    service, unbalanced_user
):
    fixed = _by_category(service.get_summary(unbalanced_user, MONTH))[
        BudgetCategory.FIXED
    ]

    assert fixed.status == "alerta"
    assert fixed.pct == pytest.approx(50.0)
    # faixa alvo carried on the alert (BUD-02)
    assert fixed.min_pct == 30.0
    assert fixed.max_pct == 40.0
    assert fixed.target_pct == 35.0
    # valor excedente = spent − (max_pct% of income) = 5000 − 4000
    assert fixed.over_amount == Decimal("1000")


def test_category_within_its_faixa_is_ok_with_zero_excess(service, unbalanced_user):
    comfort = _by_category(service.get_summary(unbalanced_user, MONTH))[
        BudgetCategory.COMFORT
    ]

    assert comfort.status == "ok"
    assert comfort.over_amount == Decimal("0")


def test_prazeres_below_min_is_not_alerted(service, unbalanced_user):
    """Prazeres has an open-ended max (100%), so 2% never triggers an alert."""
    pleasures = _by_category(service.get_summary(unbalanced_user, MONTH))[
        BudgetCategory.PLEASURES
    ]

    assert pleasures.pct == pytest.approx(2.0)
    assert pleasures.status == "ok"
    assert pleasures.over_amount == Decimal("0")


# --- BUD-03: five categories with spend, %, faixa and status ------------------


def test_summary_covers_the_five_categories_in_spec_order(service, unbalanced_user):
    summary = service.get_summary(unbalanced_user, MONTH)

    assert [c.category for c in summary.categories] == list(BudgetCategory)


def test_category_with_no_expense_reports_zero_spend_ok(service, unbalanced_user):
    invest = _by_category(service.get_summary(unbalanced_user, MONTH))[
        BudgetCategory.INVESTMENTS
    ]

    assert invest.spent == Decimal("0")
    assert invest.pct == pytest.approx(0.0)
    assert invest.status == "ok"


# --- CONV-03: remaining margin ------------------------------------------------


def test_remaining_pct_is_points_until_the_ceiling(service, unbalanced_user):
    cats = _by_category(service.get_summary(unbalanced_user, MONTH))

    # Conforto at 10% with a 20% ceiling → 10 points of room left.
    assert cats[BudgetCategory.COMFORT].remaining_pct == pytest.approx(10.0)
    # Custos Fixos at 50% past a 40% ceiling → negative (tightest) margin.
    assert cats[BudgetCategory.FIXED].remaining_pct == pytest.approx(-10.0)


# --- CONV-04 / action 4: no income base ---------------------------------------


def test_no_income_returns_sem_receita_base_warning(service, session):
    user_id = _make_user(session)
    _expense(session, user_id, BudgetCategory.FIXED, "500")
    session.flush()

    summary = service.get_summary(user_id, MONTH)

    assert summary.has_income is False
    assert summary.warning == NO_INCOME_WARNING
    assert summary.total_income == Decimal("0")
    # No percentage basis, so no category is alerted despite the spend.
    assert all(c.status == "ok" for c in summary.categories)
