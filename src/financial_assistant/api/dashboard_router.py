"""Dashboard JSON API — budget summary and transactions (API-DASH-01/02).

Read-only, user-scoped views for the React dashboard. Reuses the domain
``BudgetService`` and ``TransactionRepository`` (so scoping and month bounds
are not re-implemented) and the ``CATEGORY_LABELS`` mapping from the web
router (so the PT-BR labels cannot drift). Money and dates are serialised as
strings/ISO (see ``schemas``) to keep the client free of float rounding.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from financial_assistant.api.schemas import (
    CategoryBudgetOut,
    DashboardSummaryOut,
    TransactionListOut,
    TransactionOut,
)
from financial_assistant.auth.dependencies import get_current_user_api
from financial_assistant.db.session import get_db
from financial_assistant.domain.models import User
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)
from financial_assistant.domain.services.budget_service import BudgetService
from financial_assistant.web.router import CATEGORY_LABELS, _parse_category

router = APIRouter()

_ZERO = Decimal("0")


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


@router.get("/dashboard/summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    month: str | None = None,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
) -> DashboardSummaryOut:
    """Budget summary for ``month`` (default: current month) (API-DASH-01)."""
    resolved_month = month or _current_month()
    summary = BudgetService(db).get_summary(user.id, resolved_month)
    total_expense = sum((c.spent for c in summary.categories), _ZERO)

    categories = [
        CategoryBudgetOut(
            category=c.category.value,
            label=CATEGORY_LABELS[c.category],
            spent=c.spent,
            pct=c.pct,
            min_pct=c.min_pct,
            max_pct=c.max_pct,
            status=c.status,
        )
        for c in summary.categories
    ]

    return DashboardSummaryOut(
        month=summary.month,
        total_income=summary.total_income,
        total_expense=total_expense,
        warning=summary.warning,
        categories=categories,
    )


@router.get("/transactions", response_model=TransactionListOut)
def transactions(
    month: str | None = None,
    category: str | None = None,
    user: User = Depends(get_current_user_api),
    db: Session = Depends(get_db),
) -> TransactionListOut:
    """List the user's transactions, optionally filtered (API-DASH-02).

    An invalid ``category`` slug -> 400 "Categoria inválida" (``_parse_category``).
    """
    category_filter = _parse_category(category)
    rows = TransactionRepository(db).list(
        user.id, month=month or None, category=category_filter
    )
    return TransactionListOut(
        transactions=[
            TransactionOut(
                id=t.id,
                date=t.date,
                description=t.description,
                amount=t.amount,
                type=t.type.value,
                category=t.category.value if t.category is not None else None,
            )
            for t in rows
        ]
    )
