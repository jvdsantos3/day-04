"""Unit tests for TransactionRepository (T9).

Derived from spec ACs, not the implementation:

- CHAT-01 (create): a despesa/receita is persisted with the correct fields;
  receitas carry ``category = NULL``.
- TBL-01 / TBL-03 (list + filters): the user's transactions are returned with
  their columns (data, descrição, tipo, valor, categoria); filtering by month,
  category and type returns only matching rows; no transactions -> empty list.
- AUTH-06 + edge case (isolation / 404): every operation is scoped to
  ``user_id``; accessing, updating or deleting another user's transaction is
  indistinguishable from "not found" -> HTTP 404 (never 403, no data leak).
- VEC-05 (search fallback): ``search_by_description`` does a case-insensitive
  substring match scoped to the user (the ChromaDB-down SQL LIKE fallback).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from financial_assistant.db.session import Base
from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
    User,
)
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess
    Base.metadata.drop_all(engine)


@pytest.fixture
def repo(session):
    return TransactionRepository(session)


def _make_user(session, email: str = "ana@example.com") -> uuid.UUID:
    user = User(name="Ana", email=email, password_hash="x")
    session.add(user)
    session.flush()
    return user.id


# --- create (CHAT-01) -----------------------------------------------------


def test_create_persists_expense_with_all_fields(repo, session):
    user_id = _make_user(session)

    tx = repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Cinema",
        type=TransactionType.EXPENSE,
        amount=Decimal("150.00"),
        category=BudgetCategory.PLEASURES,
    )

    # CHAT-01: an expense is persisted with the exact fields provided.
    stored = session.scalar(select(Transaction).where(Transaction.id == tx.id))
    assert stored is not None
    assert stored.user_id == user_id
    assert stored.date == date(2026, 7, 1)
    assert stored.description == "Cinema"
    assert stored.type == TransactionType.EXPENSE
    assert stored.amount == Decimal("150.00")
    assert stored.category == BudgetCategory.PLEASURES


def test_create_income_has_null_category(repo, session):
    user_id = _make_user(session)

    tx = repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Salário",
        type=TransactionType.INCOME,
        amount=Decimal("5000.00"),
    )

    # CHAT-01 / business rule: receitas carry category = NULL.
    stored = session.scalar(select(Transaction).where(Transaction.id == tx.id))
    assert stored.type == TransactionType.INCOME
    assert stored.category is None


# --- get_by_id (isolation / 404) ------------------------------------------


def test_get_by_id_returns_own_transaction(repo, session):
    user_id = _make_user(session)
    tx = repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    fetched = repo.get_by_id(user_id, tx.id)

    assert fetched.id == tx.id
    assert fetched.description == "Mercado"


def test_get_by_id_missing_raises_404(repo, session):
    user_id = _make_user(session)

    with pytest.raises(HTTPException) as exc:
        repo.get_by_id(user_id, uuid.uuid4())

    assert exc.value.status_code == 404


def test_get_by_id_other_users_transaction_raises_404(repo, session):
    owner = _make_user(session, "owner@example.com")
    other = _make_user(session, "other@example.com")
    tx = repo.create(
        owner,
        date=date(2026, 7, 1),
        description="Mercado do dono",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    # Edge case: user B accessing user A's transaction -> 404 (not 403, no leak).
    with pytest.raises(HTTPException) as exc:
        repo.get_by_id(other, tx.id)

    assert exc.value.status_code == 404


# --- list + filters (TBL-01, TBL-03) --------------------------------------


def test_list_returns_only_own_transactions(repo, session):
    owner = _make_user(session, "owner@example.com")
    other = _make_user(session, "other@example.com")
    repo.create(
        owner,
        date=date(2026, 7, 1),
        description="Meu gasto",
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        category=BudgetCategory.FIXED,
    )
    repo.create(
        other,
        date=date(2026, 7, 1),
        description="Gasto alheio",
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        category=BudgetCategory.FIXED,
    )

    rows = repo.list(owner)

    # AUTH-06: only the caller's rows are visible.
    assert [r.description for r in rows] == ["Meu gasto"]


def test_list_empty_returns_empty_list(repo, session):
    user_id = _make_user(session)

    # TBL-02 basis: no transactions -> empty list (empty state).
    assert repo.list(user_id) == []


def test_list_exposes_all_columns(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 7, 15),
        description="Aluguel",
        type=TransactionType.EXPENSE,
        amount=Decimal("1200.00"),
        category=BudgetCategory.FIXED,
    )

    row = repo.list(user_id)[0]

    # TBL-01: rows carry data, descrição, tipo, valor, categoria.
    assert row.date == date(2026, 7, 15)
    assert row.description == "Aluguel"
    assert row.type == TransactionType.EXPENSE
    assert row.amount == Decimal("1200.00")
    assert row.category == BudgetCategory.FIXED


def test_list_filters_by_category(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Aluguel",
        type=TransactionType.EXPENSE,
        amount=Decimal("1200.00"),
        category=BudgetCategory.FIXED,
    )
    repo.create(
        user_id,
        date=date(2026, 7, 2),
        description="Cinema",
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        category=BudgetCategory.PLEASURES,
    )

    rows = repo.list(user_id, category=BudgetCategory.PLEASURES)

    # TBL-03: only the requested category is returned.
    assert [r.description for r in rows] == ["Cinema"]


def test_list_filters_by_month(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 6, 30),
        description="Junho",
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        category=BudgetCategory.FIXED,
    )
    repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Julho início",
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        category=BudgetCategory.FIXED,
    )
    repo.create(
        user_id,
        date=date(2026, 7, 31),
        description="Julho fim",
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        category=BudgetCategory.FIXED,
    )
    repo.create(
        user_id,
        date=date(2026, 8, 1),
        description="Agosto",
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        category=BudgetCategory.FIXED,
    )

    rows = repo.list(user_id, month="2026-07")

    # TBL-03: month filter returns only rows within that calendar month (inclusive
    # of the 1st and last day, exclusive of adjacent months).
    assert {r.description for r in rows} == {"Julho início", "Julho fim"}


def test_list_filters_by_type(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Salário",
        type=TransactionType.INCOME,
        amount=Decimal("5000.00"),
    )
    repo.create(
        user_id,
        date=date(2026, 7, 2),
        description="Mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    rows = repo.list(user_id, type=TransactionType.INCOME)

    # TBL-03: type filter returns only receitas.
    assert [r.description for r in rows] == ["Salário"]


def test_list_combines_filters(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Cinema julho",
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        category=BudgetCategory.PLEASURES,
    )
    repo.create(
        user_id,
        date=date(2026, 7, 2),
        description="Aluguel julho",
        type=TransactionType.EXPENSE,
        amount=Decimal("1200.00"),
        category=BudgetCategory.FIXED,
    )
    repo.create(
        user_id,
        date=date(2026, 8, 1),
        description="Cinema agosto",
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        category=BudgetCategory.PLEASURES,
    )

    rows = repo.list(
        user_id, month="2026-07", category=BudgetCategory.PLEASURES
    )

    # TBL-03: filters combine (AND) — only July + Prazeres.
    assert [r.description for r in rows] == ["Cinema julho"]


# --- update (isolation / 404) ---------------------------------------------


def test_update_changes_own_transaction(repo, session):
    user_id = _make_user(session)
    tx = repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    updated = repo.update(
        user_id,
        tx.id,
        {"amount": Decimal("95.50"), "category": BudgetCategory.COMFORT},
    )

    assert updated.amount == Decimal("95.50")
    assert updated.category == BudgetCategory.COMFORT
    # Change is persisted.
    stored = session.scalar(select(Transaction).where(Transaction.id == tx.id))
    assert stored.amount == Decimal("95.50")
    assert stored.category == BudgetCategory.COMFORT


def test_update_other_users_transaction_raises_404_and_leaves_it_unchanged(
    repo, session
):
    owner = _make_user(session, "owner@example.com")
    other = _make_user(session, "other@example.com")
    tx = repo.create(
        owner,
        date=date(2026, 7, 1),
        description="Mercado do dono",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    with pytest.raises(HTTPException) as exc:
        repo.update(other, tx.id, {"amount": Decimal("0.01")})

    assert exc.value.status_code == 404
    # The owner's row is untouched.
    stored = session.scalar(select(Transaction).where(Transaction.id == tx.id))
    assert stored.amount == Decimal("80.00")


# --- delete (isolation / 404) ---------------------------------------------


def test_delete_removes_own_transaction(repo, session):
    user_id = _make_user(session)
    tx = repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    repo.delete(user_id, tx.id)

    stored = session.scalar(select(Transaction).where(Transaction.id == tx.id))
    assert stored is None


def test_delete_other_users_transaction_raises_404_and_keeps_it(repo, session):
    owner = _make_user(session, "owner@example.com")
    other = _make_user(session, "other@example.com")
    tx = repo.create(
        owner,
        date=date(2026, 7, 1),
        description="Mercado do dono",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    with pytest.raises(HTTPException) as exc:
        repo.delete(other, tx.id)

    assert exc.value.status_code == 404
    # The owner's row still exists.
    stored = session.scalar(select(Transaction).where(Transaction.id == tx.id))
    assert stored is not None


# --- search_by_description (VEC-05 fallback) -------------------------------


def test_search_by_description_matches_partial_case_insensitive(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Pizzaria do Zé",
        type=TransactionType.EXPENSE,
        amount=Decimal("60.00"),
        category=BudgetCategory.PLEASURES,
    )
    repo.create(
        user_id,
        date=date(2026, 7, 2),
        description="Mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    rows = repo.search_by_description(user_id, "pizza")

    # VEC-05: case-insensitive substring match returns the matching row only.
    assert [r.description for r in rows] == ["Pizzaria do Zé"]


def test_search_by_description_is_scoped_to_user(repo, session):
    owner = _make_user(session, "owner@example.com")
    other = _make_user(session, "other@example.com")
    repo.create(
        owner,
        date=date(2026, 7, 1),
        description="Pizzaria do dono",
        type=TransactionType.EXPENSE,
        amount=Decimal("60.00"),
        category=BudgetCategory.PLEASURES,
    )
    repo.create(
        other,
        date=date(2026, 7, 1),
        description="Pizzaria alheia",
        type=TransactionType.EXPENSE,
        amount=Decimal("60.00"),
        category=BudgetCategory.PLEASURES,
    )

    rows = repo.search_by_description(owner, "pizzaria")

    # AUTH-06: search never crosses the user boundary.
    assert [r.description for r in rows] == ["Pizzaria do dono"]


def test_search_by_description_no_match_returns_empty(repo, session):
    user_id = _make_user(session)
    repo.create(
        user_id,
        date=date(2026, 7, 1),
        description="Mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.FIXED,
    )

    # VEC-05 / spec: 0 results is a valid, non-error outcome.
    assert repo.search_by_description(user_id, "inexistente") == []
