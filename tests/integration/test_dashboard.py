"""Integration tests for the dashboard page (T27, WEB-01/02/03).

Same isolation pattern as ``test_auth.py``: a ``TestClient`` wired to an
in-memory SQLite DB via a ``get_db`` override, with a signed session cookie
standing in for a logged-in user (no need to exercise the login form here).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.auth.dependencies import SESSION_COOKIE_NAME
from financial_assistant.auth.service import create_access_token
from financial_assistant.db.session import Base, get_db
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
    User,
)
from financial_assistant.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    """``TestClient`` + session factory wired to an isolated in-memory SQLite DB."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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


def _login_as(test_client: TestClient, user_id: str) -> None:
    test_client.cookies.set(SESSION_COOKIE_NAME, create_access_token(user_id))


def _seed_user_with_transactions(session_factory) -> str:
    with session_factory() as db:
        user = User(name="Ana", email="ana@example.com", password_hash="x")
        db.add(user)
        db.flush()
        seed_budget_targets(db, user.id)
        today = date.today()
        db.add_all(
            [
                Transaction(
                    user_id=user.id,
                    date=today,
                    description="salário",
                    type=TransactionType.INCOME,
                    amount=Decimal("5000.00"),
                ),
                Transaction(
                    user_id=user.id,
                    date=today,
                    description="aluguel",
                    type=TransactionType.EXPENSE,
                    amount=Decimal("2000.00"),
                    category=BudgetCategory.FIXED,
                ),
            ]
        )
        db.commit()
        return str(user.id)


def test_dashboard_requires_auth(client):
    test_client, _ = client
    response = test_client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login")


def test_dashboard_shows_percentages(client):
    """WEB-01/02: table with the month's transactions + one card per category with its %."""
    test_client, session_factory = client
    user_id = _seed_user_with_transactions(session_factory)
    _login_as(test_client, user_id)

    response = test_client.get("/dashboard")

    assert response.status_code == 200
    body = response.text
    # WEB-02: all 5 categories, each with its computed percentage.
    assert "Custos Fixos" in body and "40.0%" in body
    assert "Conforto" in body and "Investimentos" in body
    assert "Conhecimento e Metas" in body and "Prazeres" in body
    # WEB-01: transaction table with date/description/type/amount/category.
    assert "aluguel" in body
    assert "Despesa" in body
    assert "R$ 2000.00" in body
    assert "salário" in body
    assert "Receita" in body


def test_dashboard_shows_empty_state_without_transactions(client):
    """WEB-03: no transactions this month -> empty state guiding to register income via chat."""
    test_client, session_factory = client
    with session_factory() as db:
        user = User(name="Bruno", email="bruno@example.com", password_hash="x")
        db.add(user)
        db.flush()
        seed_budget_targets(db, user.id)
        db.commit()
        user_id = str(user.id)
    _login_as(test_client, user_id)

    response = test_client.get("/dashboard")

    assert response.status_code == 200
    assert "Nenhuma transação registrada" in response.text
    assert "chat" in response.text.lower()


def test_dashboard_flags_category_over_its_faixa_as_alerta(client):
    """WEB-02: a category spent above its faixa máxima renders with the 'alerta' styling."""
    test_client, session_factory = client
    with session_factory() as db:
        user = User(name="Carla", email="carla@example.com", password_hash="x")
        db.add(user)
        db.flush()
        seed_budget_targets(db, user.id)
        today = date.today()
        db.add_all(
            [
                Transaction(
                    user_id=user.id,
                    date=today,
                    description="salário",
                    type=TransactionType.INCOME,
                    amount=Decimal("1000.00"),
                ),
                Transaction(
                    user_id=user.id,
                    date=today,
                    description="aluguel caro",
                    type=TransactionType.EXPENSE,
                    amount=Decimal("900.00"),
                    category=BudgetCategory.FIXED,
                ),
            ]
        )
        db.commit()
        user_id = str(user.id)
    _login_as(test_client, user_id)

    response = test_client.get("/dashboard")

    assert response.status_code == 200
    assert 'class="category-card alerta"' in response.text
