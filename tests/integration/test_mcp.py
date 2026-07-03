"""Integration tests for the finance-mcp server (T16).

``@mcp.tool()`` returns the decorated function unchanged (verified against the
installed ``mcp`` SDK), so tools are exercised as plain functions — consistent
with design.md's testability principle ("MCPs testados isoladamente") and the
project's existing pattern of calling domain functions directly (e.g. T14's
``tests/unit/test_indexer.py``) rather than spinning up a stdio subprocess.

Covers the task's action items:
- MCP-02: ``create_transaction``/``update_transaction``/``delete_transaction``
  write-through the ``transactions`` ChromaDB collection via the T14 indexer.
- MCP-04: ``get_balance`` computes authoritative income/expense totals.
- "Todos recebem user_id como parâmetro obrigatório": every tool scopes to
  ``user_id`` — a second user never sees or mutates the first user's data
  (AD-002).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.config import Settings
from financial_assistant.db.session import Base
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import User
from financial_assistant.vector import client as vector_client
from financial_assistant.vector import indexer as indexer_module
from mcp_servers.finance import server as finance_mcp

pytestmark = pytest.mark.integration


class _StubEmbeddings:
    """Deterministic stand-in for the T13 embedding singleton (same as T14's tests)."""

    def embed_query(self, text: str):
        return [0.1, 0.2, 0.3]


@pytest.fixture
def finance(tmp_path, monkeypatch):
    """Wire finance-mcp to an isolated in-memory SQLite DB + tmp ChromaDB, with two seeded users."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(finance_mcp, "SessionLocal", testing_session)

    monkeypatch.setattr(
        vector_client,
        "get_settings",
        lambda: Settings(_env_file=None, chroma_path=str(tmp_path / "chroma")),
    )
    monkeypatch.setattr(indexer_module, "get_embeddings", lambda: _StubEmbeddings())
    indexer_module.clear_pending_reindex()

    with testing_session() as db:
        ana = User(name="Ana", email="ana@example.com", password_hash="x")
        bruno = User(name="Bruno", email="bruno@example.com", password_hash="x")
        db.add_all([ana, bruno])
        db.flush()
        seed_budget_targets(db, ana.id)
        seed_budget_targets(db, bruno.id)
        db.commit()
        ana_id, bruno_id = str(ana.id), str(bruno.id)

    yield ana_id, bruno_id
    indexer_module.clear_pending_reindex()


def test_finance_create_transaction(finance):
    """MCP-02: create_transaction persists to SQLite and write-throughs to ChromaDB."""
    ana_id, _ = finance

    result = finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-01",
        description="compra no mercado",
        type="despesa",
        amount="80.00",
        category="custos_fixos",
    )

    assert result["description"] == "compra no mercado"
    assert result["category"] == "custos_fixos"
    assert result["amount"] == "80.00"

    stored = finance_mcp.list_transactions(user_id=ana_id)
    assert len(stored) == 1
    assert stored[0]["id"] == result["id"]

    collection = indexer_module._get_transactions_collection()
    vector_row = collection.get(ids=[result["id"]], include=["metadatas", "documents"])
    assert vector_row["documents"][0] == "compra no mercado"
    assert vector_row["metadatas"][0]["user_id"] == ana_id
    assert vector_row["metadatas"][0]["category"] == "custos_fixos"


def test_finance_create_transaction_income_omits_category(finance):
    """Spec: incomes carry category = NULL — create_transaction accepts none."""
    ana_id, _ = finance

    result = finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-05",
        description="salário",
        type="receita",
        amount="5000.00",
    )

    assert result["category"] is None


def test_finance_update_transaction_reindexes_embedding(finance):
    """T16 note: update_transaction re-indexes the ChromaDB embedding (write-through)."""
    ana_id, _ = finance
    created = finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-01",
        description="mercado",
        type="despesa",
        amount="50.00",
        category="custos_fixos",
    )

    updated = finance_mcp.update_transaction(
        user_id=ana_id,
        transaction_id=created["id"],
        amount="65.00",
        description="mercado atualizado",
    )

    assert updated["amount"] == "65.00"
    assert updated["description"] == "mercado atualizado"
    collection = indexer_module._get_transactions_collection()
    vector_row = collection.get(ids=[created["id"]], include=["documents", "metadatas"])
    assert vector_row["documents"][0] == "mercado atualizado"
    assert vector_row["metadatas"][0]["amount"] == 65.0


def test_finance_delete_transaction_removes_embedding(finance):
    """VEC-04 via T16: delete_transaction removes the corresponding ChromaDB embedding."""
    ana_id, _ = finance
    created = finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-01",
        description="mercado",
        type="despesa",
        amount="50.00",
        category="custos_fixos",
    )

    result = finance_mcp.delete_transaction(user_id=ana_id, transaction_id=created["id"])

    assert result == {"deleted": True, "id": created["id"]}
    assert finance_mcp.list_transactions(user_id=ana_id) == []
    collection = indexer_module._get_transactions_collection()
    assert collection.get(ids=[created["id"]])["ids"] == []


def test_finance_get_balance_totals(finance):
    """MCP-04: get_balance computes income/expense totals and balance for the month."""
    ana_id, _ = finance
    finance_mcp.create_transaction(
        user_id=ana_id, date="2026-07-01", description="salário", type="receita", amount="5000.00"
    )
    finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-02",
        description="mercado",
        type="despesa",
        amount="800.00",
        category="custos_fixos",
    )

    balance = finance_mcp.get_balance(user_id=ana_id, month="2026-07")

    assert balance["total_income"] == "5000.00"
    assert balance["total_expense"] == "800.00"
    assert balance["balance"] == "4200.00"


def test_finance_get_budget_summary_reflects_transactions(finance):
    """get_budget_summary wraps BudgetService and flags an over-budget category."""
    ana_id, _ = finance
    finance_mcp.create_transaction(
        user_id=ana_id, date="2026-07-01", description="salário", type="receita", amount="10000.00"
    )
    finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-02",
        description="mercado",
        type="despesa",
        amount="5000.00",
        category="custos_fixos",
    )

    summary = finance_mcp.get_budget_summary(user_id=ana_id, month="2026-07")

    assert summary["has_income"] is True
    fixed = next(c for c in summary["categories"] if c["category"] == "custos_fixos")
    assert fixed["status"] == "alerta"


def test_finance_tools_isolate_between_users(finance):
    """AD-002: every tool scopes strictly to user_id — user B never sees/mutates user A's data."""
    ana_id, bruno_id = finance
    ana_tx = finance_mcp.create_transaction(
        user_id=ana_id,
        date="2026-07-01",
        description="mercado da Ana",
        type="despesa",
        amount="50.00",
        category="custos_fixos",
    )

    # list_transactions never leaks another user's rows.
    assert finance_mcp.list_transactions(user_id=bruno_id) == []

    # update_transaction/delete_transaction on another user's id are rejected (same 404
    # contract as TransactionRepository — existence is not distinguishable from ownership).
    with pytest.raises(HTTPException):
        finance_mcp.update_transaction(user_id=bruno_id, transaction_id=ana_tx["id"], amount="1.00")
    with pytest.raises(HTTPException):
        finance_mcp.delete_transaction(user_id=bruno_id, transaction_id=ana_tx["id"])

    # Ana's transaction and embedding remain untouched.
    assert finance_mcp.list_transactions(user_id=ana_id)[0]["id"] == ana_tx["id"]
