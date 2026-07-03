"""Pydantic request/response models for the JSON API (Phase 1).

Response shapes mirror design.md exactly so the React frontend's TypeScript
types can be a 1:1 reflection. Money values (``Decimal``) are serialised as
strings (e.g. ``"2000.00"``) to avoid float rounding in the client.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_serializer


class RegisterRequest(BaseModel):
    """Body for ``POST /api/auth/register``."""

    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    """Body for ``POST /api/auth/login``."""

    email: str
    password: str


class UserOut(BaseModel):
    """A user as exposed to the client (never includes the password hash)."""

    id: UUID
    name: str
    email: str

    @field_serializer("id")
    def _serialize_id(self, value: UUID) -> str:
        return str(value)


class UserEnvelope(BaseModel):
    """``{"user": {...}}`` — register/login success bodies (AUTH-API-01/02)."""

    user: UserOut


class CategoryBudgetOut(BaseModel):
    """One budget category's status for the month (API-DASH-01)."""

    category: str
    label: str
    spent: Decimal
    pct: float
    min_pct: float
    max_pct: float
    status: str

    @field_serializer("spent")
    def _serialize_spent(self, value: Decimal) -> str:
        return str(value)


class DashboardSummaryOut(BaseModel):
    """``GET /api/dashboard/summary`` response body (API-DASH-01)."""

    month: str
    total_income: Decimal
    total_expense: Decimal
    warning: str | None
    categories: list[CategoryBudgetOut]

    @field_serializer("total_income", "total_expense")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value)
