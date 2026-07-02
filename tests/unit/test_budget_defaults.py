"""Unit tests for budget categories and default targets (T4).

Derived from spec "Framework de Orçamento" (ranges table + defaults line) and
CONV-01 / BUD-01. The default target_pct values sum to 90% by design.
"""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from financial_assistant.db.session import Base
from financial_assistant.domain.budget_defaults import (
    DEFAULT_BUDGET_TARGETS,
    seed_budget_targets,
)
from financial_assistant.domain.models import BudgetCategory, BudgetTarget, User

pytestmark = pytest.mark.unit

# (category, min_pct, max_pct, target_pct) — the spec's five categories.
# Prazeres is "≥ 5%" (open max modelled as 100.0).
EXPECTED_RANGES = {
    BudgetCategory.FIXED: (30.0, 40.0, 35.0),
    BudgetCategory.COMFORT: (15.0, 20.0, 17.0),
    BudgetCategory.INVESTMENTS: (15.0, 25.0, 20.0),
    BudgetCategory.KNOWLEDGE: (5.0, 15.0, 10.0),
    BudgetCategory.PLEASURES: (5.0, 100.0, 8.0),
}


@pytest.fixture
def session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess
    Base.metadata.drop_all(engine)


def test_enum_has_exactly_the_five_spec_categories():
    assert {c.value for c in BudgetCategory} == {
        "custos_fixos",
        "conforto",
        "investimentos",
        "conhecimento_metas",
        "prazeres",
    }


def test_defaults_cover_all_five_categories():
    assert {d.category for d in DEFAULT_BUDGET_TARGETS} == set(BudgetCategory)
    assert len(DEFAULT_BUDGET_TARGETS) == 5


@pytest.mark.parametrize("category", list(BudgetCategory))
def test_default_ranges_match_spec(category):
    default = next(d for d in DEFAULT_BUDGET_TARGETS if d.category == category)
    expected_min, expected_max, expected_target = EXPECTED_RANGES[category]

    assert default.min_pct == expected_min
    assert default.max_pct == expected_max
    assert default.target_pct == expected_target


def test_target_pct_sum_is_ninety_percent():
    assert sum(d.target_pct for d in DEFAULT_BUDGET_TARGETS) == 90.0


@pytest.mark.parametrize("category", list(BudgetCategory))
def test_target_pct_lies_within_its_range(category):
    """Defaults sit inside their faixa (spec: 'centro das faixas')."""
    default = next(d for d in DEFAULT_BUDGET_TARGETS if d.category == category)
    assert default.min_pct <= default.target_pct <= default.max_pct


def test_seed_inserts_five_targets_for_user(session):
    user = User(name="Ana", email="ana@example.com", password_hash="x")
    session.add(user)
    session.flush()

    created = seed_budget_targets(session, user.id)

    assert len(created) == 5
    rows = session.scalars(
        select(BudgetTarget).where(BudgetTarget.user_id == user.id)
    ).all()
    assert len(rows) == 5
    persisted = {
        r.category: (r.min_pct, r.max_pct, r.target_pct) for r in rows
    }
    assert persisted == EXPECTED_RANGES


def test_seed_is_scoped_to_the_given_user(session):
    user_a = User(name="A", email="a@example.com", password_hash="x")
    user_b = User(name="B", email="b@example.com", password_hash="x")
    session.add_all([user_a, user_b])
    session.flush()

    seed_budget_targets(session, user_a.id)

    a_rows = session.scalars(
        select(BudgetTarget).where(BudgetTarget.user_id == user_a.id)
    ).all()
    b_rows = session.scalars(
        select(BudgetTarget).where(BudgetTarget.user_id == user_b.id)
    ).all()
    assert len(a_rows) == 5
    assert b_rows == []


def test_seeded_target_pct_sums_to_ninety(session):
    user = User(name="Ana", email="ana@example.com", password_hash="x")
    session.add(user)
    session.flush()

    created = seed_budget_targets(session, user.id)

    assert sum(t.target_pct for t in created) == 90.0
