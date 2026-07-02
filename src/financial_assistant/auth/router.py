"""Auth router — registration, login, and logout (T6/T7, AUTH-01..05).

Registration (T6) creates the account, seeds default budget targets, and
redirects to the dashboard. Login (T7) verifies credentials and issues a JWT
in an httpOnly, SameSite=Lax cookie before redirecting to the dashboard;
logout clears that cookie. Form validation / auth failures re-render the form.

Spec-precision gaps: the spec does not fix HTTP statuses — validation and
invalid-login failures re-render the form with 400; successful auth redirects
with 303 (POST -> GET). Invalid login uses one generic message for both wrong
password and unknown email so the email's existence is not leaked (AUTH-04).
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_assistant.auth.dependencies import SESSION_COOKIE_NAME
from financial_assistant.auth.service import (
    create_access_token,
    hash_password,
    verify_password,
)
from financial_assistant.config import get_settings
from financial_assistant.db.session import get_db
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

MIN_PASSWORD_LENGTH = 8
DUPLICATE_EMAIL_MESSAGE = "Email já cadastrado"
SHORT_PASSWORD_MESSAGE = "A senha deve ter no mínimo 8 caracteres"
INVALID_CREDENTIALS_MESSAGE = "Email ou senha inválidos"


def _set_session_cookie(response: RedirectResponse, user_id: str) -> None:
    """Attach the signed JWT as an httpOnly, SameSite=Lax cookie (AUTH-03)."""
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_access_token(user_id),
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="lax",
    )


def _render_form(
    request: Request,
    *,
    error: str | None = None,
    name: str = "",
    email: str = "",
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "register.html",
        {"error": error, "name": name, "email": email},
        status_code=status_code,
    )


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request) -> HTMLResponse:
    """Render the empty registration form."""
    return _render_form(request)


@router.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Create an account, seed budget targets, and redirect to the dashboard."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return _render_form(
            request,
            error=SHORT_PASSWORD_MESSAGE,
            name=name,
            email=email,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if db.scalar(select(User).where(User.email == email)) is not None:
        return _render_form(
            request,
            error=DUPLICATE_EMAIL_MESSAGE,
            name=name,
            email=email,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user = User(name=name, email=email, password_hash=hash_password(password))
    db.add(user)
    db.flush()  # assign user.id before seeding targets
    seed_budget_targets(db, user.id)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    """Render the empty login form."""
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "email": ""}
    )


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Verify credentials, set the session cookie, and redirect to the dashboard."""
    user = db.scalar(select(User).where(User.email == email))
    # AUTH-04: same generic outcome whether the email is unknown or the
    # password is wrong — never reveal which. verify_password only runs when a
    # user exists; the message and status are identical in both branches.
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": INVALID_CREDENTIALS_MESSAGE, "email": email},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    response = RedirectResponse(
        url="/dashboard", status_code=status.HTTP_303_SEE_OTHER
    )
    _set_session_cookie(response, str(user.id))
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    """Clear the session cookie and return to the login page."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response
