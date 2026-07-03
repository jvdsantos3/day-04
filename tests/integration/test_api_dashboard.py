"""Integration tests for the dashboard JSON API (T3, T4).

- API-DASH-01: GET /api/dashboard/summary — month default = current month;
  200 shape with string Decimals, PT-BR labels, total_expense = sum of spent,
  warning when no income; 401 without a cookie.
- API-DASH-02: GET /api/transactions — optional month/category filters; string
  amount/ISO date/enum-value strings; 400 for an invalid category slug; empty
  list when nothing matches; 401 without a cookie.

An in-memory SQLite DB is injected via a dependency override; the API is
exercised through the real /api paths so routing is verified end to end.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.db.session import Base, get_db
from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
    User,
)
from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

VALID = {"name": "João", "email": "joao@example.com", "password": "senha-forte-8"}
MONTH = "2026-07"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSession
    Base.metadata.drop_all(engine)


def _register(test_client):
    resp = test_client.post("/api/auth/register", json=VALID)
    assert resp.status_code == 201


def _user(TestingSession) -> User:
    with TestingSession() as db:
        return db.scalar(select(User).where(User.email == VALID["email"]))


def _add(TestingSession, user_id, **kwargs):
    with TestingSession() as db:
        db.add(Transaction(user_id=user_id, **kwargs))
        db.commit()


# --- T3: /api/dashboard/summary ------------------------------------------


def test_summary_requires_auth(client):
    test_client, _ = client
    resp = test_client.get("/api/dashboard/summary", params={"month": MONTH})
    # API-DASH-01: protected — no cookie -> 401.
    assert resp.status_code == 401


def test_summary_shape_and_values(client):
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)

    # Income 5000; FIXED spend 2500 (=50% > max 40 -> alerta); COMFORT 500 (10% ok).
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 1), description="Salário",
        type=TransactionType.INCOME, amount=Decimal("5000.00"), category=None,
    )
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 2), description="Aluguel",
        type=TransactionType.EXPENSE, amount=Decimal("2500.00"),
        category=BudgetCategory.FIXED,
    )
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 3), description="Streaming",
        type=TransactionType.EXPENSE, amount=Decimal("500.00"),
        category=BudgetCategory.COMFORT,
    )

    resp = test_client.get("/api/dashboard/summary", params={"month": MONTH})

    assert resp.status_code == 200
    body = resp.json()
    assert body["month"] == "2026-07"
    # Decimals serialised as strings.
    assert body["total_income"] == "5000.00"
    # total_expense = sum of category.spent = 2500 + 500 = 3000.00
    assert body["total_expense"] == "3000.00"
    assert body["warning"] is None
    # Five categories in spec order; first is Custos Fixos.
    assert len(body["categories"]) == 5
    fixed = body["categories"][0]
    assert fixed["category"] == "custos_fixos"
    assert fixed["label"] == "Custos Fixos"
    assert fixed["spent"] == "2500.00"
    assert fixed["pct"] == 50.0
    assert fixed["min_pct"] == 30
    assert fixed["max_pct"] == 40
    assert fixed["status"] == "alerta"
    # Conforto is within its faixa -> ok.
    comfort = body["categories"][1]
    assert comfort["category"] == "conforto"
    assert comfort["label"] == "Conforto"
    assert comfort["spent"] == "500.00"
    assert comfort["status"] == "ok"


def test_summary_warning_when_no_income(client):
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 2), description="Aluguel",
        type=TransactionType.EXPENSE, amount=Decimal("2500.00"),
        category=BudgetCategory.FIXED,
    )

    resp = test_client.get("/api/dashboard/summary", params={"month": MONTH})

    assert resp.status_code == 200
    body = resp.json()
    # No income -> non-null warning string, income "0".
    assert body["total_income"] == "0"
    assert isinstance(body["warning"], str) and body["warning"]


def test_summary_invalid_month_format_returns_400(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.get("/api/dashboard/summary", params={"month": "not-a-month"})

    # API-DASH-01 edge case: malformed month -> 400, not 500.
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Mês inválido"}


def test_summary_month_out_of_range_returns_400(client):
    test_client, _ = client
    _register(test_client)

    # Month 13 doesn't exist; datetime.strptime("%Y-%m") already rejects it,
    # so no separate bounds check is needed beyond the parse in _validate_month.
    resp = test_client.get("/api/dashboard/summary", params={"month": "2026-13"})

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Mês inválido"}


def test_summary_defaults_to_current_month(client):
    test_client, TestingSession = client
    _register(test_client)
    current = date.today().strftime("%Y-%m")

    resp = test_client.get("/api/dashboard/summary")

    assert resp.status_code == 200
    # Default month = current month when the query param is omitted.
    assert resp.json()["month"] == current


# --- T4: /api/transactions -----------------------------------------------


def test_transactions_requires_auth(client):
    test_client, _ = client
    resp = test_client.get("/api/transactions")
    # API-DASH-02: protected — no cookie -> 401.
    assert resp.status_code == 401


def test_transactions_shape_and_serialisation(client):
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 15), description="Aluguel",
        type=TransactionType.EXPENSE, amount=Decimal("-1500.00"),
        category=BudgetCategory.FIXED,
    )
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 1), description="Salário",
        type=TransactionType.INCOME, amount=Decimal("5000.00"), category=None,
    )

    resp = test_client.get("/api/transactions", params={"month": MONTH})

    assert resp.status_code == 200
    rows = resp.json()["transactions"]
    assert len(rows) == 2
    # Ordered most-recent first: the 15th before the 1st.
    expense = rows[0]
    assert expense["date"] == "2026-07-15"
    assert expense["description"] == "Aluguel"
    # amount serialised as string, type/category as enum-value strings.
    assert expense["amount"] == "-1500.00"
    assert expense["type"] == "despesa"
    assert expense["category"] == "custos_fixos"
    assert isinstance(expense["id"], str) and expense["id"]
    # Income carries a null category.
    income = rows[1]
    assert income["type"] == "receita"
    assert income["category"] is None
    assert income["amount"] == "5000.00"


def test_transactions_filtered_by_category(client):
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 2), description="Aluguel",
        type=TransactionType.EXPENSE, amount=Decimal("1500.00"),
        category=BudgetCategory.FIXED,
    )
    _add(
        TestingSession, user.id,
        date=date(2026, 7, 3), description="Cinema",
        type=TransactionType.EXPENSE, amount=Decimal("50.00"),
        category=BudgetCategory.PLEASURES,
    )

    resp = test_client.get(
        "/api/transactions", params={"month": MONTH, "category": "custos_fixos"}
    )

    assert resp.status_code == 200
    rows = resp.json()["transactions"]
    # Only the matching category is returned.
    assert [r["description"] for r in rows] == ["Aluguel"]
    assert rows[0]["category"] == "custos_fixos"


def test_transactions_invalid_category_returns_400(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.get("/api/transactions", params={"category": "inexistente"})

    # API-DASH-02: invalid slug -> 400 with the exact spec message.
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Categoria inválida"}


def test_transactions_invalid_month_format_returns_400(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.get("/api/transactions", params={"month": "not-a-month"})

    # API-DASH-02 edge case: malformed month -> 400, not 500.
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Mês inválido"}


def test_transactions_empty_when_nothing_matches(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.get("/api/transactions", params={"month": "2020-01"})

    assert resp.status_code == 200
    assert resp.json() == {"transactions": []}


def _seed_varied_transactions(TestingSession, user_id):
    """Two categories, two months — enough to prove filters actually filter.

    Migrated from test_dashboard.py::_seed_user_with_varied_transactions (T18):
    the underlying TransactionRepository.list() filtering behaviour (TBL-03)
    was only exercised through the old HTML partial route; these cases have
    no equivalent yet against the JSON /api/transactions route.
    """
    _add(
        TestingSession, user_id,
        date=date(2026, 7, 5), description="aluguel de julho",
        type=TransactionType.EXPENSE, amount=Decimal("2000.00"),
        category=BudgetCategory.FIXED,
    )
    _add(
        TestingSession, user_id,
        date=date(2026, 7, 10), description="cinema",
        type=TransactionType.EXPENSE, amount=Decimal("50.00"),
        category=BudgetCategory.PLEASURES,
    )
    _add(
        TestingSession, user_id,
        date=date(2026, 6, 5), description="aluguel de junho",
        type=TransactionType.EXPENSE, amount=Decimal("1900.00"),
        category=BudgetCategory.FIXED,
    )


def test_transactions_filtered_by_month(client):
    """TBL-03 (migrated): filtering by month returns only that month's rows, across categories."""
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)
    _seed_varied_transactions(TestingSession, user.id)

    resp = test_client.get("/api/transactions", params={"month": "2026-06"})

    assert resp.status_code == 200
    descriptions = [r["description"] for r in resp.json()["transactions"]]
    assert descriptions == ["aluguel de junho"]


def test_transactions_month_and_category_filters_combine(client):
    """TBL-03 (migrated): month and category filters combine (AND), not just either alone."""
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)
    _seed_varied_transactions(TestingSession, user.id)

    resp = test_client.get(
        "/api/transactions", params={"month": "2026-07", "category": "custos_fixos"}
    )

    assert resp.status_code == 200
    descriptions = [r["description"] for r in resp.json()["transactions"]]
    assert descriptions == ["aluguel de julho"]


def test_transactions_explicit_empty_month_means_all_time(client):
    """(migrated) An explicit empty ``month`` query param clears the filter (all-time), not zero rows."""
    test_client, TestingSession = client
    _register(test_client)
    user = _user(TestingSession)
    _seed_varied_transactions(TestingSession, user.id)

    resp = test_client.get("/api/transactions", params={"month": ""})

    assert resp.status_code == 200
    descriptions = {r["description"] for r in resp.json()["transactions"]}
    assert descriptions == {"aluguel de julho", "aluguel de junho", "cinema"}
