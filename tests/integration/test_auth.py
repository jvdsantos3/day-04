"""Integration tests for registration and login/logout (T6, T7).

Registration (T6) — spec AUTH-01, AUTH-02 + "senha < 8 caracteres" edge case:

- AUTH-01: valid name/email/password -> account with bcrypt-hashed password,
  budget targets seeded, redirect to the dashboard.
- AUTH-02: duplicate email -> rejected with the message "Email já cadastrado".
- Edge case: password shorter than 8 chars -> registration rejected (validation).

Login/session (T7) — spec AUTH-03, AUTH-04, AUTH-05:

- AUTH-03: correct credentials -> JWT in an httpOnly cookie + redirect dashboard.
- AUTH-04: wrong credentials -> generic error that does not reveal whether the
  email exists (same message for wrong password and unknown email).
- AUTH-05: unauthenticated access to a protected route -> redirect to /login.

The endpoints persist to SQLite; these tests point them at an in-memory
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


# --- T7: login / logout / route protection -------------------------------


def _register(test_client, **overrides):
    """Register VALID (with optional overrides) and assert it succeeded."""
    data = {**VALID, **overrides}
    resp = test_client.post("/register", data=data, follow_redirects=False)
    assert resp.status_code == 303
    return data


def test_get_login_renders_form(client):
    test_client, _ = client

    resp = test_client.get("/login")

    assert resp.status_code == 200
    body = resp.text
    # The login form collects email and password (spec AUTH-03).
    assert 'name="email"' in body
    assert 'name="password"' in body


def test_login_success(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.post(
        "/login",
        data={"email": VALID["email"], "password": VALID["password"]},
        follow_redirects=False,
    )

    # AUTH-03: valid login redirects to the dashboard...
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    # ...and issues a JWT session cookie that is httpOnly + SameSite=Lax.
    set_cookie = resp.headers["set-cookie"].lower()
    assert "access_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    # The cookie value must not be the raw password / email (it is a signed JWT).
    token = test_client.cookies.get("access_token")
    assert token and VALID["password"] not in token


def test_login_grants_access_to_protected_route(client):
    test_client, _ = client
    _register(test_client)

    test_client.post(
        "/login",
        data={"email": VALID["email"], "password": VALID["password"]},
        follow_redirects=False,
    )
    # The session cookie authenticates subsequent requests (AUTH-03 round-trip).
    resp = test_client.get("/dashboard")

    assert resp.status_code == 200
    assert VALID["name"] in resp.text


def test_login_invalid_password_generic_error(client):
    test_client, _ = client
    _register(test_client)

    resp = test_client.post(
        "/login",
        data={"email": VALID["email"], "password": "senha-errada-8"},
        follow_redirects=False,
    )

    # AUTH-04: rejected, no session cookie, generic message.
    assert resp.status_code == 400
    assert "access_token" not in resp.headers.get("set-cookie", "")
    assert "Email ou senha inválidos" in resp.text


def test_login_unknown_email_uses_same_generic_error(client):
    """AUTH-04: an unknown email must not be distinguishable from a wrong password."""
    test_client, _ = client
    _register(test_client)

    wrong_pw = test_client.post(
        "/login",
        data={"email": VALID["email"], "password": "senha-errada-8"},
        follow_redirects=False,
    )
    unknown_email = test_client.post(
        "/login",
        data={"email": "ninguem@example.com", "password": VALID["password"]},
        follow_redirects=False,
    )

    assert unknown_email.status_code == wrong_pw.status_code == 400
    # Same status and same message -> existence of the email is not leaked.
    assert "Email ou senha inválidos" in unknown_email.text
    assert "access_token" not in unknown_email.headers.get("set-cookie", "")


def test_protected_route_redirect(client):
    test_client, _ = client

    resp = test_client.get("/dashboard", follow_redirects=False)

    # AUTH-05: unauthenticated access to a protected route redirects to /login.
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].startswith("/login")


def test_logout_clears_session(client):
    test_client, _ = client
    _register(test_client)
    test_client.post(
        "/login",
        data={"email": VALID["email"], "password": VALID["password"]},
        follow_redirects=False,
    )

    resp = test_client.post("/logout", follow_redirects=False)

    # Logout redirects to /login and clears the session cookie.
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    # After logout the protected route is no longer reachable.
    assert test_client.cookies.get("access_token") in (None, "")
    after = test_client.get("/dashboard", follow_redirects=False)
    assert after.status_code in (302, 307)
    assert after.headers["location"].startswith("/login")
