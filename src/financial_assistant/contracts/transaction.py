"""Transaction input contract — enforces the type/category invariant (T11).

Business rule (spec VAL-01/VAL-02): expenses require a ``category`` (envelope
budgeting needs it to compute :class:`BudgetService`'s percentages); incomes
forbid one (there is nothing to categorise). This is the single point where
the rule is checked before a transaction reaches the ORM — see the note in
``domain/models.py``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from financial_assistant.domain.models import BudgetCategory, TransactionType


class TransactionCreate(BaseModel):
    """Payload for creating a transaction (income or expense)."""

    date: date
    description: str = Field(min_length=1, max_length=255)
    type: TransactionType
    amount: Decimal = Field(gt=Decimal("0"))
    category: BudgetCategory | None = None

    @model_validator(mode="after")
    def _check_category_matches_type(self) -> "TransactionCreate":
        if self.type is TransactionType.EXPENSE and self.category is None:
            raise ValueError("category é obrigatório para despesas")
        if self.type is TransactionType.INCOME and self.category is not None:
            raise ValueError("category não é permitido para receitas")
        return self
