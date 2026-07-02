"""Integration tests for user registration (T6).

Derived from spec AUTH-01, AUTH-02 and the "senha < 8 caracteres" edge case:

- AUTH-01: valid name/email/password -> account with bcrypt-hashed password,
  budget targets seeded, redirect to the dashboard.
- AUTH-02: duplicate email -> rejected with the message "Email já cadastrado".
- Edge case: password shorter than 8 chars -> registration rejected (validation).

The register endpoint persists to SQLite; these tests point it at an in-memory
database via a dependency override so they stay isolated and parallel-safe.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.auth.service import verify_password
from financial_assistant.db.session import Base, get_db
from financial_assistant.domain.models import BudgetTarget, User
from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

VALID = {"name": "Ana", "email": "ana@example.com", "password": "senha-forte-8"}


@pytest.fixture
def client():
    """TestClient wired to an in-memory SQLite DB (shared across the app)."""
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


def test_register_success(client):
    test_client, TestingSession = client

    resp = test_client.post("/register", data=VALID, follow_redirects=False)

    # AUTH-01: successful registration redirects to the dashboard.
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"

    with TestingSession() as db:
        user = db.scalar(select(User).where(User.email == VALID["email"]))
        assert user is not None
        assert user.name == VALID["name"]
        # AUTH-01: password stored bcrypt-hashed, never in plaintext.
        assert user.password_hash != VALID["password"]
        assert user.password_hash.startswith(("$2a$", "$2b$", "$2y$"))
        assert verify_password(VALID["password"], user.password_hash) is True
        # T6 action #4: seed the five default budget targets for the new user.
        targets = db.scalars(
            select(BudgetTarget).where(BudgetTarget.user_id == user.id)
        ).all()
        assert len(targets) == 5


def test_register_duplicate_email_rejected(client):
    test_client, TestingSession = client

    first = test_client.post("/register", data=VALID, follow_redirects=False)
    assert first.status_code == 303

    second = test_client.post("/register", data=VALID, follow_redirects=False)

    # AUTH-02: duplicate email is rejected with the exact spec message.
    assert second.status_code == 400
    assert "Email já cadastrado" in second.text

    with TestingSession() as db:
        users = db.scalars(
            select(User).where(User.email == VALID["email"])
        ).all()
        assert len(users) == 1


def test_register_short_password_rejected(client):
    test_client, TestingSession = client

    resp = test_client.post(
        "/register",
        data={**VALID, "password": "curta"},  # 5 chars < 8
        follow_redirects=False,
    )

    # Edge case: password under 8 chars is rejected with a validation error.
    assert resp.status_code == 400
    with TestingSession() as db:
        user = db.scalar(select(User).where(User.email == VALID["email"]))
        assert user is None


def test_get_register_renders_form(client):
    test_client, _ = client

    resp = test_client.get("/register")

    assert resp.status_code == 200
    body = resp.text
    # The form must collect name, email and password (spec: register with all three).
    assert 'name="name"' in body
    assert 'name="email"' in body
    assert 'name="password"' in body
