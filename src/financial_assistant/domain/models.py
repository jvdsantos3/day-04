"""SQLAlchemy ORM models — SQLite source of truth for the financial assistant.

Business rule (spec): incomes (``type == receita``) carry ``category = NULL``;
expenses require a category. The column is nullable at the DB layer; the
``type``-vs-``category`` invariant is enforced by the ``TransactionCreate``
Pydantic contract (T11).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from financial_assistant.db.session import Base


class TransactionType(str, Enum):
    """Whether a transaction adds to (income) or subtracts from (expense) funds."""

    INCOME = "receita"
    EXPENSE = "despesa"


class BudgetCategory(str, Enum):
    """The five envelope-budgeting categories applied to expenses."""

    FIXED = "custos_fixos"
    COMFORT = "conforto"
    INVESTMENTS = "investimentos"
    KNOWLEDGE = "conhecimento_metas"
    PLEASURES = "prazeres"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist enums by their string value (e.g. ``receita``) rather than name."""
    return [member.value for member in enum_cls]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255))
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, values_callable=_enum_values)
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # NULL for incomes; set for expenses (enforced by TransactionCreate contract).
    category: Mapped[BudgetCategory | None] = mapped_column(
        SAEnum(BudgetCategory, values_callable=_enum_values), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BudgetTarget(Base):
    __tablename__ = "budget_targets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    category: Mapped[BudgetCategory] = mapped_column(
        SAEnum(BudgetCategory, values_callable=_enum_values)
    )
    min_pct: Mapped[float] = mapped_column(Float)
    max_pct: Mapped[float] = mapped_column(Float)
    target_pct: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
