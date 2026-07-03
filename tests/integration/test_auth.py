"""Integration tests for the auth API dependency's isolation boundary (T8, AUTH-06).

The old form-based ``/register``, ``/login``, ``GET /register``,
``GET /login`` and ``POST /logout`` HTML-route tests (T6/T7, AUTH-01..05)
were removed in T18 along with the Jinja2 routes themselves. Their domain
coverage (bcrypt hashing, budget-target seeding, duplicate-email / short-
password rejection, generic invalid-credentials message, httpOnly+SameSite
cookie) already exists against the JSON surface in ``test_api_auth.py``
(T1/T2) — see that file for AUTH-API-01..04.

What remains here is AUTH-06 (API 401 vs. web redirect, and per-user data
isolation), which never depended on HTML and has no equivalent elsewhere.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.auth.dependencies import get_current_user_api
from financial_assistant.db.session import Base, get_db
from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
    User,
)
from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

VALID = {"name": "Ana", "email": "ana@example.com", "password": "senha-forte-8"}


def _register(test_client, **overrides):
    """Register VALID (with optional overrides) via the JSON API and assert success."""
    data = {**VALID, **overrides}
    resp = test_client.post("/api/auth/register", json=data)
    assert resp.status_code == 201
    return data


# --- T8: auth dependency — API 401 + user_id isolation (AUTH-06) ----------

PROBE_PATH = "/api/_probe/my-transactions"


@pytest.fixture
def api_client():
    """Like ``client`` but mounts an API probe route guarded by the API auth
    dependency.

    The probe returns the caller's transactions scoped by the *authenticated*
    ``user_id`` (``get_current_user_api``) — the isolation boundary AUTH-06
    requires. It stands in for the T9 ``TransactionRepository`` (not yet built)
    so the dependency's scoping can be verified now.
    """
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

    @app.get(PROBE_PATH)
    def _probe_my_transactions(
        user: User = Depends(get_current_user_api),
        db: Session = Depends(get_db),
    ):
        rows = db.scalars(
            select(Transaction).where(Transaction.user_id == user.id)
        ).all()
        return [{"description": r.description} for r in rows]

    with TestClient(app) as test_client:
        yield test_client, TestingSession
    Base.metadata.drop_all(engine)


def test_api_route_returns_401_when_unauthenticated(api_client):
    """AUTH-06: an API route rejects an unauthenticated caller with 401 (not a
    redirect, which is the web-route behaviour)."""
    test_client, _ = api_client

    resp = test_client.get(PROBE_PATH, follow_redirects=False)

    assert resp.status_code == 401


def test_user_isolation_in_repository(api_client):
    """AUTH-06: data access is scoped to the authenticated session's user_id —
    user A never sees user B's transactions."""
    test_client, TestingSession = api_client

    _register(test_client, name="Ana", email="ana@example.com")
    _register(test_client, name="Bruno", email="bruno@example.com")

    # Seed one transaction for each user directly.
    with TestingSession() as db:
        ana = db.scalar(select(User).where(User.email == "ana@example.com"))
        bruno = db.scalar(select(User).where(User.email == "bruno@example.com"))
        db.add(
            Transaction(
                user_id=ana.id,
                date=date(2026, 7, 1),
                description="Mercado da Ana",
                type=TransactionType.EXPENSE,
                amount=Decimal("50.00"),
                category=BudgetCategory.FIXED,
            )
        )
        db.add(
            Transaction(
                user_id=bruno.id,
                date=date(2026, 7, 1),
                description="Mercado do Bruno",
                type=TransactionType.EXPENSE,
                amount=Decimal("70.00"),
                category=BudgetCategory.FIXED,
            )
        )
        db.commit()

    # Authenticate as Ana and query "my" transactions through the guarded route.
    test_client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": VALID["password"]},
    )
    resp = test_client.get(PROBE_PATH)

    assert resp.status_code == 200
    descriptions = [row["description"] for row in resp.json()]
    # Ana sees only her own row; Bruno's is invisible to her session.
    assert descriptions == ["Mercado da Ana"]
    assert "Mercado do Bruno" not in descriptions
