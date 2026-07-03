"""Web router — authenticated pages.

``/dashboard`` (T27, WEB-01/02/03) renders the current month's picture for
the authenticated user: income/expense totals, one progress card per budget
category (``BudgetService.get_summary``, T10), and the month's transaction
table (``TransactionRepository.list``, T9). ``/dashboard/transactions``
(T28, WEB-04/TBL-03) is the HTMX partial the dashboard's filter form targets
to re-render just the table on a month/category change, without a full page
reload. The ``get_current_user`` dependency enforces authentication;
unauthenticated requests are redirected to /login before either handler runs
(AUTH-05).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
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


def _parse_category(category: str | None) -> BudgetCategory | None:
    if not category:
        return None
    try:
        return BudgetCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail="Categoria inválida") from None


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
            "category": None,
            "summary": summary,
            "total_expense": total_expense,
            "transactions": transactions,
            "category_labels": CATEGORY_LABELS,
        },
    )


@router.get("/dashboard/transactions", response_class=HTMLResponse)
def dashboard_transactions(
    request: Request,
    month: str | None = None,
    category: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial (WEB-04): the transaction table filtered by month/category (TBL-03)."""
    month_filter = month or None
    category_filter = _parse_category(category)
    transactions = TransactionRepository(db).list(
        user.id, month=month_filter, category=category_filter
    )
    return templates.TemplateResponse(
        request,
        "_transactions_table.html",
        {
            "month": month_filter,
            "category": category_filter,
            "transactions": transactions,
            "category_labels": CATEGORY_LABELS,
        },
    )
