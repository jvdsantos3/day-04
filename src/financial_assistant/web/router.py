"""Web router — authenticated pages.

``/dashboard`` (T27, WEB-01/02/03) renders the current month's picture for
the authenticated user: income/expense totals, one progress card per budget
category (``BudgetService.get_summary``, T10), and the month's transaction
table (``TransactionRepository.list``, T9). The ``get_current_user``
dependency enforces authentication; unauthenticated requests are redirected
to /login before this handler runs (AUTH-05).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from financial_assistant.auth.dependencies import get_current_user
from financial_assistant.db.session import get_db
from financial_assistant.domain.models import BudgetCategory, User
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)
from financial_assistant.domain.services.budget_service import BudgetService

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Display labels for the spec's five categories (BudgetCategory stores the
# SQL/agent-facing slug, e.g. "custos_fixos" — the dashboard shows the
# human-readable name instead).
CATEGORY_LABELS: dict[BudgetCategory, str] = {
    BudgetCategory.FIXED: "Custos Fixos",
    BudgetCategory.COMFORT: "Conforto",
    BudgetCategory.INVESTMENTS: "Investimentos",
    BudgetCategory.KNOWLEDGE: "Conhecimento e Metas",
    BudgetCategory.PLEASURES: "Prazeres",
}


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    month = date.today().strftime("%Y-%m")
    summary = BudgetService(db).get_summary(user.id, month)
    transactions = TransactionRepository(db).list(user.id, month=month)
    total_expense = sum((category.spent for category in summary.categories), Decimal("0"))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "month": month,
            "summary": summary,
            "total_expense": total_expense,
            "transactions": transactions,
            "category_labels": CATEGORY_LABELS,
        },
    )
