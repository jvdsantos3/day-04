"""Auth router — user registration (T6, AUTH-01/AUTH-02).

Login/logout and JWT session cookies arrive in T7; this router only registers
new accounts. On success it seeds the user's default budget targets and
redirects to the dashboard (per AUTH-01). Validation failures re-render the
form with the offending message.

Spec-precision gap: the spec does not fix an HTTP status for validation
failures (short password / duplicate email) — we re-render the form with 400.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_assistant.auth.service import hash_password
from financial_assistant.db.session import get_db
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import User

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

MIN_PASSWORD_LENGTH = 8
DUPLICATE_EMAIL_MESSAGE = "Email já cadastrado"
SHORT_PASSWORD_MESSAGE = "A senha deve ter no mínimo 8 caracteres"


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
