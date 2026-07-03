"""Integration tests for the JSON auth API (T1, T2).

Covers the spec-defined contracts for the React frontend's auth surface:

- AUTH-API-01: register -> 201, {"user": {...}}, JWT cookie, budget seeded.
- AUTH-API-02: duplicate email -> 400 {"detail": "Email já cadastrado"}.
- AUTH-API-04: short password -> 400 validation; invalid login -> 401 with one
  generic message for wrong password and unknown email (no existence leak).
- AUTH-API-03: /api/auth/me -> 200 {id,name,email} with a valid cookie, 401 without.

Endpoints persist to SQLite; an in-memory DB is injected via a dependency
override so the tests stay isolated and parallel-safe.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.auth.service import verify_password
from financial_assistant.db.session import Base, get_db
from financial_assistant.domain.models import BudgetTarget, User
from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

VALID = {"name": "João", "email": "joao@example.com", "password": "senha-forte-8"}


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


def _register(test_client, **overrides):
    """Register VALID (with optional overrides) and return the response."""
    return test_client.post("/api/auth/register", json={**VALID, **overrides})


# --- T1: register --------------------------------------------------------


def test_register_success(client):
    test_client, TestingSession = client

    resp = _register(test_client)

    # AUTH-API-01: 201 with {"user": {id, name, email}}.
    assert resp.status_code == 201
    body = resp.json()
    assert set(body["user"].keys()) == {"id", "name", "email"}
    assert body["user"]["name"] == VALID["name"]
    assert body["user"]["email"] == VALID["email"]
    assert body["user"]["id"]  # non-empty id string
    # JWT httpOnly session cookie is set.
    assert test_client.cookies.get("access_token")
    set_cookie = resp.headers["set-cookie"].lower()
    assert "access_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    with TestingSession() as db:
        user = db.scalar(select(User).where(User.email == VALID["email"]))
        assert user is not None
        # Password stored bcrypt-hashed, never plaintext.
        assert user.password_hash != VALID["password"]
        assert verify_password(VALID["password"], user.password_hash) is True
        # Budget targets seeded for the new user (five categories).
        targets = db.scalars(
            select(BudgetTarget).where(BudgetTarget.user_id == user.id)
        ).all()
        assert len(targets) == 5


def test_register_duplicate_email_rejected(client):
    test_client, TestingSession = client

    first = _register(test_client)
    assert first.status_code == 201

    second = _register(test_client)

    # AUTH-API-02: 400 with the exact spec message; no second account created.
    assert second.status_code == 400
    assert second.json() == {"detail": "Email já cadastrado"}
    with TestingSession() as db:
        users = db.scalars(select(User).where(User.email == VALID["email"])).all()
        assert len(users) == 1


def test_register_short_password_rejected(client):
    test_client, TestingSession = client

    resp = _register(test_client, password="curta")  # 5 chars < 8

    # AUTH-API-04 validation: 400 with the exact spec message; no account.
    assert resp.status_code == 400
    assert resp.json() == {"detail": "A senha deve ter no mínimo 8 caracteres"}
    with TestingSession() as db:
        user = db.scalar(select(User).where(User.email == VALID["email"]))
        assert user is None


# --- T1: login -----------------------------------------------------------


def test_login_success(client):
    test_client, _ = client
    _register(test_client)
    test_client.cookies.clear()

    resp = test_client.post(
        "/api/auth/login",
        json={"email": VALID["email"], "password": VALID["password"]},
    )

    # 200 with {"user": {...}} and a fresh JWT cookie.
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == VALID["email"]
    assert body["user"]["name"] == VALID["name"]
    token = test_client.cookies.get("access_token")
    assert token and VALID["password"] not in token
    # Cookie is httpOnly + SameSite=Lax (migrated from test_auth.py::test_login_success, T18).
    set_cookie = resp.headers["set-cookie"].lower()
    assert "access_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_login_wrong_password_generic_401(client):
    test_client, _ = client
    _register(test_client)
    test_client.cookies.clear()

    resp = test_client.post(
        "/api/auth/login",
        json={"email": VALID["email"], "password": "senha-errada-8"},
    )

    # AUTH-API-04: 401 generic message, no session cookie.
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Email ou senha inválidos"}
    assert "access_token" not in resp.headers.get("set-cookie", "")


def test_login_unknown_email_same_generic_401(client):
    """AUTH-API-04: unknown email is indistinguishable from a wrong password."""
    test_client, _ = client
    _register(test_client)
    test_client.cookies.clear()

    resp = test_client.post(
        "/api/auth/login",
        json={"email": "ninguem@example.com", "password": VALID["password"]},
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Email ou senha inválidos"}
    assert "access_token" not in resp.headers.get("set-cookie", "")


# --- T1: logout ----------------------------------------------------------


def test_logout_clears_cookie(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.post("/api/auth/logout")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # The access_token cookie is cleared.
    assert test_client.cookies.get("access_token") in (None, "")


# --- T2: /api/auth/me ----------------------------------------------------


def test_me_returns_current_user_with_valid_cookie(client):
    test_client, _ = client
    _register(test_client)  # sets the session cookie on the client

    resp = test_client.get("/api/auth/me")

    # AUTH-API-03: flat {id, name, email} (NOT nested under "user").
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"id", "name", "email"}
    assert body["name"] == VALID["name"]
    assert body["email"] == VALID["email"]
    assert body["id"]  # non-empty id string


def test_me_without_cookie_returns_401(client):
    test_client, _ = client

    resp = test_client.get("/api/auth/me")

    # AUTH-API-03: no cookie -> 401 (reuses get_current_user_api).
    assert resp.status_code == 401


def test_me_with_invalid_cookie_returns_401(client):
    test_client, _ = client
    test_client.cookies.set("access_token", "not-a-valid-jwt")

    resp = test_client.get("/api/auth/me")

    assert resp.status_code == 401
