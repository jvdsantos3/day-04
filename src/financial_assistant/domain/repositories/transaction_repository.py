"""Transaction CRUD repository — user-scoped access to the SQLite source of truth (T9).

Every operation is filtered by ``user_id`` so a user only ever touches their own
rows (spec AUTH-06). Fetching a transaction that does not exist *or* belongs to
another user raises ``HTTPException(404)`` — the same response for both cases so
the existence of another user's data is never leaked (spec edge case: "usuário A
tenta acessar transação do usuário B THEN retornar 404 (não 403)").

``search_by_description`` is the SQL ``LIKE`` fallback used when ChromaDB is
unavailable (spec VEC-05) — degraded text search that keeps CRUD working.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
)

# Columns a caller may change via ``update`` — ownership/identity columns
# (``id``, ``user_id``, ``created_at``) are intentionally excluded.
_MUTABLE_FIELDS = frozenset({"date", "description", "type", "amount", "category"})


def _month_bounds(month: str) -> tuple[date, date]:
    """Return the ``[start, next_month_start)`` date range for a ``YYYY-MM`` string."""
    year, mon = (int(part) for part in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


class TransactionRepository:
    """User-scoped CRUD over the ``transactions`` table.

    Writes ``flush`` (not ``commit``); the caller owns the transaction boundary,
    consistent with the rest of the domain layer.
    """

    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        user_id: uuid.UUID,
        *,
        date: date,
        description: str,
        type: TransactionType,
        amount: Decimal,
        category: BudgetCategory | None = None,
    ) -> Transaction:
        """Persist a new transaction for ``user_id`` and return it (flushed)."""
        transaction = Transaction(
            user_id=user_id,
            date=date,
            description=description,
            type=type,
            amount=amount,
            category=category,
        )
        self._session.add(transaction)
        self._session.flush()
        return transaction

    def get_by_id(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> Transaction:
        """Return the user's transaction or raise 404 (missing or another user's)."""
        transaction = self._session.scalar(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,
            )
        )
        if transaction is None:
            raise HTTPException(status_code=404, detail="Transação não encontrada")
        return transaction

    def list(
        self,
        user_id: uuid.UUID,
        *,
        month: str | None = None,
        category: BudgetCategory | None = None,
        type: TransactionType | None = None,
    ) -> list[Transaction]:
        """List the user's transactions, most recent first, with optional filters.

        ``month`` is a ``YYYY-MM`` string; ``category`` and ``type`` filter on the
        matching columns. Filters combine (AND). Returns ``[]`` when nothing matches.
        """
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        if month is not None:
            start, end = _month_bounds(month)
            stmt = stmt.where(Transaction.date >= start, Transaction.date < end)
        if category is not None:
            stmt = stmt.where(Transaction.category == category)
        if type is not None:
            stmt = stmt.where(Transaction.type == type)
        stmt = stmt.order_by(Transaction.date.desc(), Transaction.created_at.desc())
        return list(self._session.scalars(stmt).all())

    def update(
        self,
        user_id: uuid.UUID,
        transaction_id: uuid.UUID,
        changes: dict,
    ) -> Transaction:
        """Apply ``changes`` to the user's transaction and return it (404 if not owned)."""
        transaction = self.get_by_id(user_id, transaction_id)
        for field, value in changes.items():
            if field in _MUTABLE_FIELDS:
                setattr(transaction, field, value)
        self._session.flush()
        return transaction

    def delete(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
        """Delete the user's transaction (404 if missing or another user's)."""
        transaction = self.get_by_id(user_id, transaction_id)
        self._session.delete(transaction)
        self._session.flush()

    def search_by_description(
        self, user_id: uuid.UUID, query: str
    ) -> list[Transaction]:
        """Case-insensitive ``LIKE`` search over the user's descriptions (VEC-05 fallback)."""
        stmt = (
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.description.ilike(f"%{query}%"),
            )
            .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        )
        return list(self._session.scalars(stmt).all())
