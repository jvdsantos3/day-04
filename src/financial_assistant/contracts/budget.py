"""Read-model contracts mirroring ``BudgetService``'s output shapes (T11, dep T10).

Pydantic twins of ``domain.services.budget_service``'s ``CategoryBudget`` /
``BudgetSummary`` dataclasses (BUD-01/02/03). ``from_attributes`` lets them be
built straight from those dataclass instances for API/agent responses,
without re-deriving the budgeting logic here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from financial_assistant.domain.models import BudgetCategory


class CategoryStatus(BaseModel):
    """One category's spend against its faixa for the month."""

    model_config = ConfigDict(from_attributes=True)

    category: BudgetCategory
    spent: Decimal
    pct: float
    min_pct: float
    max_pct: float
    target_pct: float
    status: Literal["ok", "alerta"]
    remaining_pct: float
    over_amount: Decimal


class BudgetSummary(BaseModel):
    """Whole-month budget picture for one user."""

    model_config = ConfigDict(from_attributes=True)

    month: str
    total_income: Decimal
    has_income: bool
    warning: str | None
    categories: list[CategoryStatus]
