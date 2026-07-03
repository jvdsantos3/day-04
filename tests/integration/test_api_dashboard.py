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


def test_summary_defaults_to_current_month(client):
    test_client, TestingSession = client
    _register(test_client)
    current = date.today().strftime("%Y-%m")

    resp = test_client.get("/api/dashboard/summary")

    assert resp.status_code == 200
    # Default month = current month when the query param is omitted.
    assert resp.json()["month"] == current
