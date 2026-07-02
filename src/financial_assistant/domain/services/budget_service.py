"""Budget summary service — envelope-budget status per category (T10).

Computes, for one user and one ``YYYY-MM`` month, how each of the five budget
categories is tracking against its target range (spec BUD-01/02/03, CONV-03):

- Percentages are of the month's **total income** (BUD-01). No income → no
  meaningful percentages, so ``get_summary`` returns ``has_income=False`` and the
  ``"sem receita base"`` warning instead (spec CONV-04: guide the user to record
  income first).
- A category is flagged ``"alerta"`` only when its spend **exceeds the maximum**
  of its faixa (BUD-02); the alert carries the category, current %, target range
  and the excess amount (``over_amount``). Spending below the minimum is *not* an
  alert — the spec only alerts on overshoot.
- Prazeres carries ``max_pct = 100.0`` (T4 open-ended "≥ 5%" gap) so it never
  alerts by overshoot — the data models this; no special-casing here.

Expenses and incomes are read through :class:`TransactionRepository` (T9), so the
``user_id`` scoping (AD-002) and month bounds live in one place.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_assistant.domain.models import (
    BudgetCategory,
    BudgetTarget,
    TransactionType,
)
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)

# Returned in place of percentages when the month has no recorded income
# (spec CONV-04 — percentages of zero income are meaningless).
NO_INCOME_WARNING = "sem receita base"

_ZERO = Decimal("0")
# Canonical display order for the five categories (matches the spec table).
_CATEGORY_ORDER = {category: index for index, category in enumerate(BudgetCategory)}


@dataclass(frozen=True)
class CategoryBudget:
    """One category's spend against its faixa for the month.

    ``pct`` and ``remaining_pct`` are percentage points of the month's income;
    ``remaining_pct`` is ``max_pct - pct`` (negative once the ceiling is passed),
    so the smallest value marks the tightest category (CONV-03 prioritisation).
    ``over_amount`` is the currency spent above the ceiling, and is ``0`` unless
    ``status == "alerta"``.
    """

    category: BudgetCategory
    spent: Decimal
    pct: float
    min_pct: float
    max_pct: float
    target_pct: float
    status: Literal["ok", "alerta"]
    remaining_pct: float
    over_amount: Decimal


@dataclass(frozen=True)
class BudgetSummary:
    """Whole-month budget picture for one user."""

    month: str
    total_income: Decimal
    has_income: bool
    warning: str | None
    categories: list[CategoryBudget]


class BudgetService:
    """Read-only budget summariser over the user's transactions and targets."""

    def __init__(self, session: Session):
        self._session = session
        self._transactions = TransactionRepository(session)

    def get_summary(self, user_id: uuid.UUID, month: str) -> BudgetSummary:
        """Summarise ``user_id``'s budget for ``month`` (a ``YYYY-MM`` string).

        Returns one :class:`CategoryBudget` per seeded target, ordered as in the
        spec table. When the month has no income, percentages are left at ``0``
        and ``warning`` is set to :data:`NO_INCOME_WARNING`.
        """
        incomes = self._transactions.list(
            user_id, month=month, type=TransactionType.INCOME
        )
        total_income = sum((t.amount for t in incomes), _ZERO)
        has_income = total_income > _ZERO

        expenses = self._transactions.list(
            user_id, month=month, type=TransactionType.EXPENSE
        )
        spent_by_category: dict[BudgetCategory, Decimal] = {}
        for transaction in expenses:
            spent_by_category[transaction.category] = (
                spent_by_category.get(transaction.category, _ZERO)
                + transaction.amount
            )

        targets = self._session.scalars(
            select(BudgetTarget).where(BudgetTarget.user_id == user_id)
        ).all()

        categories = [
            self._category_budget(target, spent_by_category, total_income, has_income)
            for target in sorted(targets, key=lambda t: _CATEGORY_ORDER[t.category])
        ]

        return BudgetSummary(
            month=month,
            total_income=total_income,
            has_income=has_income,
            warning=None if has_income else NO_INCOME_WARNING,
            categories=categories,
        )

    @staticmethod
    def _category_budget(
        target: BudgetTarget,
        spent_by_category: dict[BudgetCategory, Decimal],
        total_income: Decimal,
        has_income: bool,
    ) -> CategoryBudget:
        spent = spent_by_category.get(target.category, _ZERO)
        pct = float(spent / total_income * 100) if has_income else 0.0

        # Alert only on overshoot of the faixa máxima (BUD-02); no income means
        # no percentage basis, hence no alert.
        is_alert = has_income and pct > target.max_pct
        if is_alert:
            max_allowed = total_income * Decimal(str(target.max_pct)) / Decimal("100")
            over_amount = spent - max_allowed
        else:
            over_amount = _ZERO

        return CategoryBudget(
            category=target.category,
            spent=spent,
            pct=pct,
            min_pct=target.min_pct,
            max_pct=target.max_pct,
            target_pct=target.target_pct,
            status="alerta" if is_alert else "ok",
            remaining_pct=target.max_pct - pct,
            over_amount=over_amount,
        )
