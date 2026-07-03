"""JSON auth API — register, login, logout (AUTH-API-01, -02, -04).

Parallel to the form-based ``auth/router.py``: same rules and messages, but
JSON in/out and status codes suited to a programmatic (React) client. Reuses
the existing password hashing, JWT cookie, budget seeding, and message
constants so behaviour cannot drift between the two surfaces.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_assistant.auth.dependencies import (
    SESSION_COOKIE_NAME,
    get_current_user_api,
)
from financial_assistant.auth.router import (
    DUPLICATE_EMAIL_MESSAGE,
    INVALID_CREDENTIALS_MESSAGE,
    MIN_PASSWORD_LENGTH,
    SHORT_PASSWORD_MESSAGE,
    _set_session_cookie,
)
from financial_assistant.auth.service import hash_password, verify_password
from financial_assistant.api.schemas import LoginRequest, RegisterRequest, UserOut
from financial_assistant.db.session import get_db
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import User

router = APIRouter()


def _user_envelope(user: User) -> dict:
    """Serialise ``{"user": {id, name, email}}`` (AUTH-API-01/02 body)."""
    return {"user": UserOut.model_validate(user, from_attributes=True).model_dump()}


@router.post("/auth/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Create an account (201 + cookie); reject short password / duplicate (400)."""
    if len(body.password) < MIN_PASSWORD_LENGTH:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": SHORT_PASSWORD_MESSAGE},
        )

    if db.scalar(select(User).where(User.email == body.email)) is not None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": DUPLICATE_EMAIL_MESSAGE},
        )

    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()  # assign user.id before seeding targets
    seed_budget_targets(db, user.id)
    db.commit()

    response = JSONResponse(
        status_code=status.HTTP_201_CREATED, content=_user_envelope(user)
    )
    _set_session_cookie(response, str(user.id))
    return response


@router.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Verify credentials (200 + cookie) or reject with a generic 401 (AUTH-API-04)."""
    user = db.scalar(select(User).where(User.email == body.email))
    # AUTH-API-04: identical response for unknown email and wrong password so
    # the account's existence is never leaked.
    if user is None or not verify_password(body.password, user.password_hash):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": INVALID_CREDENTIALS_MESSAGE},
        )

    response = JSONResponse(
        status_code=status.HTTP_200_OK, content=_user_envelope(user)
    )
    _set_session_cookie(response, str(user.id))
    return response


@router.post("/auth/logout")
def logout() -> Response:
    """Clear the session cookie and return ``{"ok": true}`` (200)."""
    response = JSONResponse(status_code=status.HTTP_200_OK, content={"ok": True})
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


@router.get("/auth/me")
def me(user: User = Depends(get_current_user_api)) -> dict:
    """Return the authenticated user ``{id, name, email}`` (AUTH-API-03).

    Flat (not nested under ``user``) to match design.md's ``/api/auth/me``
    example. Unauthenticated callers get a 401 via ``get_current_user_api``.
    """
    return UserOut.model_validate(user, from_attributes=True).model_dump()
