"""finance-mcp — MCP server exposing financial CRUD + budget tools (T16).

Wraps the domain layer (``TransactionRepository``, ``BudgetService``) behind the
Model Context Protocol so agents (Transações, Orçamento, Validador) can reach
financial data without importing SQLAlchemy directly (spec: "MCPs operacionais",
design.md "finance-mcp"). Every tool takes ``user_id`` as its first, mandatory
parameter — there is no default, so a caller cannot omit it (AD-002 isolation).

``create_transaction``, ``update_transaction`` and ``delete_transaction`` keep the
``transactions`` ChromaDB collection in sync via the T14 indexer (write-through,
spec MCP-02 / VEC-01 / VEC-04) — SQLite stays the source of truth and the vector
write happens after the SQLite commit succeeds.
"""

from __future__ import annotations

import uuid
from datetime import date as date_
from decimal import Decimal

from mcp.server.fastmcp import FastMCP

from financial_assistant.contracts.budget import BudgetSummary as BudgetSummaryContract
from financial_assistant.contracts.transaction import TransactionCreate
from financial_assistant.db.session import SessionLocal
from financial_assistant.domain.models import BudgetCategory, Transaction, TransactionType
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)
from financial_assistant.domain.services.budget_service import BudgetService
from financial_assistant.vector.indexer import delete_transaction_embedding, index_transaction

mcp = FastMCP("finance-mcp")

_ZERO = Decimal("0")


def _serialize_transaction(transaction: Transaction) -> dict:
    return {
        "id": str(transaction.id),
        "date": transaction.date.isoformat(),
        "description": transaction.description,
        "type": transaction.type.value,
        "amount": str(transaction.amount),
        "category": transaction.category.value if transaction.category else None,
    }


@mcp.tool()
def create_transaction(
    user_id: str,
    date: str,
    description: str,
    type: str,
    amount: str,
    category: str | None = None,
) -> dict:
    """Create a transaction for ``user_id`` and index it into ChromaDB (write-through)."""
    payload = TransactionCreate(
        date=date_.fromisoformat(date),
        description=description,
        type=TransactionType(type),
        amount=Decimal(amount),
        category=BudgetCategory(category) if category else None,
    )
    uid = uuid.UUID(user_id)
    with SessionLocal() as session:
        transaction = TransactionRepository(session).create(
            uid,
            date=payload.date,
            description=payload.description,
            type=payload.type,
            amount=payload.amount,
            category=payload.category,
        )
        session.commit()
        result = _serialize_transaction(transaction)
        index_transaction(uid, transaction)
    return result


@mcp.tool()
def list_transactions(
    user_id: str,
    month: str | None = None,
    category: str | None = None,
    type: str | None = None,
) -> list[dict]:
    """List ``user_id``'s transactions, optionally filtered by month/category/type."""
    with SessionLocal() as session:
        transactions = TransactionRepository(session).list(
            uuid.UUID(user_id),
            month=month,
            category=BudgetCategory(category) if category else None,
            type=TransactionType(type) if type else None,
        )
        return [_serialize_transaction(t) for t in transactions]


@mcp.tool()
def get_budget_summary(user_id: str, month: str) -> dict:
    """Return ``user_id``'s budget summary for ``month`` (percent per category, alerts)."""
    with SessionLocal() as session:
        summary = BudgetService(session).get_summary(uuid.UUID(user_id), month)
    return BudgetSummaryContract.model_validate(summary).model_dump(mode="json")


@mcp.tool()
def get_balance(user_id: str, month: str | None = None) -> dict:
    """Return ``user_id``'s income/expense totals and balance for ``month`` (all-time if omitted).

    Authoritative source for the Validador when a response cites a saldo (spec MCP-04).
    """
    uid = uuid.UUID(user_id)
    with SessionLocal() as session:
        repo = TransactionRepository(session)
        incomes = repo.list(uid, month=month, type=TransactionType.INCOME)
        expenses = repo.list(uid, month=month, type=TransactionType.EXPENSE)
    total_income = sum((t.amount for t in incomes), _ZERO)
    total_expense = sum((t.amount for t in expenses), _ZERO)
    return {
        "month": month,
        "total_income": str(total_income),
        "total_expense": str(total_expense),
        "balance": str(total_income - total_expense),
    }


@mcp.tool()
def update_transaction(
    user_id: str,
    transaction_id: str,
    date: str | None = None,
    description: str | None = None,
    type: str | None = None,
    amount: str | None = None,
    category: str | None = None,
) -> dict:
    """Apply the given fields to ``user_id``'s transaction and re-index it (write-through)."""
    changes: dict = {}
    if date is not None:
        changes["date"] = date_.fromisoformat(date)
    if description is not None:
        changes["description"] = description
    if type is not None:
        changes["type"] = TransactionType(type)
    if amount is not None:
        changes["amount"] = Decimal(amount)
    if category is not None:
        changes["category"] = BudgetCategory(category)

    uid = uuid.UUID(user_id)
    with SessionLocal() as session:
        transaction = TransactionRepository(session).update(
            uid, uuid.UUID(transaction_id), changes
        )
        session.commit()
        result = _serialize_transaction(transaction)
        index_transaction(uid, transaction)
    return result


@mcp.tool()
def delete_transaction(user_id: str, transaction_id: str) -> dict:
    """Delete ``user_id``'s transaction and remove its ChromaDB embedding (write-through)."""
    uid = uuid.UUID(user_id)
    tid = uuid.UUID(transaction_id)
    with SessionLocal() as session:
        TransactionRepository(session).delete(uid, tid)
        session.commit()
    delete_transaction_embedding(uid, tid)
    return {"deleted": True, "id": transaction_id}
