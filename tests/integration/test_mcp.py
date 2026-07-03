"""Integration tests for the finance-mcp (T16) and chroma-mcp (T17) servers.

``@mcp.tool()`` returns the decorated function unchanged (verified against the
installed ``mcp`` SDK), so tools are exercised as plain functions — consistent
with design.md's testability principle ("MCPs testados isoladamente") and the
project's existing pattern of calling domain functions directly (e.g. T14's
``tests/unit/test_indexer.py``) rather than spinning up a stdio subprocess.

finance-mcp (T16) coverage:
- MCP-02: ``create_transaction``/``update_transaction``/``delete_transaction``
  write-through the ``transactions`` ChromaDB collection via the T14 indexer.
- MCP-04: ``get_balance`` computes authoritative income/expense totals.
- "Todos recebem user_id como parâmetro obrigatório": every tool scopes to
  ``user_id`` — a second user never sees or mutates the first user's data
  (AD-002).

chroma-mcp (T17) coverage:
- VEC-02: ``search_transactions``/``find_similar_transactions`` isolate by
  ``user_id`` and filter by the configurable similarity threshold.
- VEC-03: ``query_knowledge`` wraps the T15 shared knowledge_base RAG lookup.
- VEC-05: ``search_transactions`` degrades to
  ``TransactionRepository.search_by_description`` when ChromaDB is down.
- ``get_chat_context``/``save_working_memory``: Camada 3 cross-agent memory,
  also scoped by ``user_id``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from langchain_core.tools import StructuredTool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_assistant.config import Settings
from financial_assistant.db.session import Base
from financial_assistant.domain.budget_defaults import seed_budget_targets
from financial_assistant.domain.models import (
    BudgetCategory,
    Transaction,
    TransactionType,
    User,
)
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)
from financial_assistant.mcp import client as mcp_client
from financial_assistant.vector import client as vector_client
from financial_assistant.vector import indexer as indexer_module
from financial_assistant.vector import knowledge_seed as knowledge_seed_module
from financial_assistant.vector.client import require_user_id
from mcp_servers.chroma import server as chroma_mcp
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


# ---------------------------------------------------------------------------
# chroma-mcp (T17)
# ---------------------------------------------------------------------------


class _MappedEmbeddings:
    """Deterministic stand-in for the T13 singleton: exact text -> unit vector lookup.

    Lets a test control cosine similarity exactly (orthogonal/identical basis
    vectors) instead of depending on the real HuggingFace model.
    """

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = vectors

    def embed_query(self, text: str):
        return self._vectors[text]

    def embed_documents(self, texts):
        return [self._vectors[text] for text in texts]


@pytest.fixture
def chroma(tmp_path, monkeypatch):
    """Wire chroma-mcp to an isolated in-memory SQLite DB + tmp ChromaDB, with two seeded users."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(chroma_mcp, "SessionLocal", testing_session)

    monkeypatch.setattr(
        vector_client,
        "get_settings",
        lambda: Settings(_env_file=None, chroma_path=str(tmp_path / "chroma")),
    )
    indexer_module.clear_pending_reindex()

    with testing_session() as db:
        ana = User(name="Ana", email="ana-chroma@example.com", password_hash="x")
        bruno = User(name="Bruno", email="bruno-chroma@example.com", password_hash="x")
        db.add_all([ana, bruno])
        db.commit()
        ana_id, bruno_id = str(ana.id), str(bruno.id)

    yield ana_id, bruno_id
    indexer_module.clear_pending_reindex()


def test_chroma_search_isolation(chroma, monkeypatch):
    """AD-002: search_transactions never returns another user's transactions, even with an identical embedding."""
    ana_id, bruno_id = chroma
    description = "pizza da esquina"
    stub = _MappedEmbeddings({description: [1.0, 0.0, 0.0]})
    monkeypatch.setattr(indexer_module, "get_embeddings", lambda: stub)
    monkeypatch.setattr(chroma_mcp, "get_embeddings", lambda: stub)

    ana_tx = Transaction(
        id=uuid.uuid4(),
        user_id=uuid.UUID(ana_id),
        date=date(2026, 7, 1),
        description=description,
        type=TransactionType.EXPENSE,
        amount=Decimal("45.00"),
        category=BudgetCategory.PLEASURES,
    )
    bruno_tx = Transaction(
        id=uuid.uuid4(),
        user_id=uuid.UUID(bruno_id),
        date=date(2026, 7, 1),
        description=description,
        type=TransactionType.EXPENSE,
        amount=Decimal("45.00"),
        category=BudgetCategory.PLEASURES,
    )
    indexer_module.index_transaction(uuid.UUID(ana_id), ana_tx)
    indexer_module.index_transaction(uuid.UUID(bruno_id), bruno_tx)

    hits = chroma_mcp.search_transactions(user_id=ana_id, query=description)

    assert [hit["id"] for hit in hits] == [str(ana_tx.id)]


def test_chroma_search_transactions_filters_by_score_threshold(chroma, monkeypatch):
    """VEC-02: hits below the configurable similarity threshold are dropped."""
    ana_id, _ = chroma
    stub = _MappedEmbeddings(
        {
            "pizza da esquina": [1.0, 0.0, 0.0],
            "troca de pneu": [0.0, 1.0, 0.0],
            "pizza": [1.0, 0.0, 0.0],
        }
    )
    monkeypatch.setattr(indexer_module, "get_embeddings", lambda: stub)
    monkeypatch.setattr(chroma_mcp, "get_embeddings", lambda: stub)
    close_tx = Transaction(
        id=uuid.uuid4(),
        user_id=uuid.UUID(ana_id),
        date=date(2026, 7, 1),
        description="pizza da esquina",
        type=TransactionType.EXPENSE,
        amount=Decimal("45.00"),
        category=BudgetCategory.PLEASURES,
    )
    unrelated_tx = Transaction(
        id=uuid.uuid4(),
        user_id=uuid.UUID(ana_id),
        date=date(2026, 7, 1),
        description="troca de pneu",
        type=TransactionType.EXPENSE,
        amount=Decimal("120.00"),
        category=BudgetCategory.FIXED,
    )
    indexer_module.index_transaction(uuid.UUID(ana_id), close_tx)
    indexer_module.index_transaction(uuid.UUID(ana_id), unrelated_tx)

    hits = chroma_mcp.search_transactions(user_id=ana_id, query="pizza")

    assert [hit["id"] for hit in hits] == [str(close_tx.id)]


def test_chroma_fallback_sqlite_like(chroma, monkeypatch):
    """VEC-05: when ChromaDB is down, search_transactions degrades to the SQL LIKE repository search."""
    ana_id, _ = chroma
    monkeypatch.setattr(
        chroma_mcp, "get_chroma_client", lambda: (_ for _ in ()).throw(RuntimeError("chromadb down"))
    )

    with chroma_mcp.SessionLocal() as session:
        TransactionRepository(session).create(
            uuid.UUID(ana_id),
            date=date(2026, 7, 1),
            description="compra no mercado da esquina",
            type=TransactionType.EXPENSE,
            amount=Decimal("80.00"),
            category=BudgetCategory.FIXED,
        )
        session.commit()

    hits = chroma_mcp.search_transactions(user_id=ana_id, query="mercado")

    assert len(hits) == 1
    assert hits[0]["document"] == "compra no mercado da esquina"
    assert hits[0]["score"] is None


def test_chroma_find_similar_transactions_combines_history_and_category_examples(chroma, monkeypatch):
    """T15 handoff: find_similar_transactions blends the user's own history with global category_examples."""
    ana_id, _ = chroma
    stub = _MappedEmbeddings(
        {
            "ifood": [1.0, 0.0, 0.0],
            "pedido de delivery": [1.0, 0.0, 0.0],
            "aporte na reserva": [0.0, 1.0, 0.0],
        }
    )
    monkeypatch.setattr(indexer_module, "get_embeddings", lambda: stub)
    monkeypatch.setattr(chroma_mcp, "get_embeddings", lambda: stub)

    past_tx = Transaction(
        id=uuid.uuid4(),
        user_id=uuid.UUID(ana_id),
        date=date(2026, 7, 1),
        description="pedido de delivery",
        type=TransactionType.EXPENSE,
        amount=Decimal("60.00"),
        category=BudgetCategory.PLEASURES,
    )
    indexer_module.index_transaction(uuid.UUID(ana_id), past_tx)

    example_metadata = require_user_id(
        {"user_id": knowledge_seed_module.GLOBAL_USER_ID, "example_id": "ex-prazeres-2", "category": "prazeres"}
    )
    chroma_mcp._collection(chroma_mcp._CATEGORY_EXAMPLES).upsert(
        ids=["ex-prazeres-2"],
        embeddings=[stub.embed_query("pedido de delivery")],
        documents=["pedido de delivery"],
        metadatas=[example_metadata],
    )
    unrelated_example_metadata = require_user_id(
        {"user_id": knowledge_seed_module.GLOBAL_USER_ID, "example_id": "ex-investimentos-1", "category": "investimentos"}
    )
    chroma_mcp._collection(chroma_mcp._CATEGORY_EXAMPLES).upsert(
        ids=["ex-investimentos-1"],
        embeddings=[stub.embed_query("aporte na reserva")],
        documents=["aporte na reserva"],
        metadatas=[unrelated_example_metadata],
    )

    hits = chroma_mcp.find_similar_transactions(user_id=ana_id, description="ifood", n_results=2)

    sources = {hit["source"] for hit in hits}
    assert "transaction" in sources
    assert "category_example" in sources
    assert all(hit["document"] == "pedido de delivery" for hit in hits)


def test_chroma_query_knowledge_delegates_to_knowledge_seed(chroma, monkeypatch):
    """VEC-03: query_knowledge wraps the T15 knowledge_seed RAG lookup over the shared knowledge_base."""
    ana_id, _ = chroma
    doc_text = "Prazeres (mínimo 5% da renda mensal, sem teto): cinema, restaurantes, delivery."
    stub = _MappedEmbeddings({doc_text: [1.0, 0.0, 0.0], "o que é prazeres": [1.0, 0.0, 0.0]})
    monkeypatch.setattr(knowledge_seed_module, "get_embeddings", lambda: stub)
    metadata = require_user_id(
        {"user_id": knowledge_seed_module.GLOBAL_USER_ID, "doc_id": "kb-prazeres", "category": "prazeres"}
    )
    knowledge_seed_module._get_collection(knowledge_seed_module._KNOWLEDGE_BASE_COLLECTION).upsert(
        ids=["kb-prazeres"], embeddings=[stub.embed_query(doc_text)], documents=[doc_text], metadatas=[metadata]
    )

    hits = chroma_mcp.query_knowledge(user_id=ana_id, query="o que é prazeres")

    assert hits[0]["doc_id"] == "kb-prazeres"
    assert hits[0]["metadata"]["category"] == "prazeres"


def test_chroma_get_chat_context_isolates_by_user(chroma, monkeypatch):
    """Camada 3: get_chat_context only recalls the caller's own chat_memory turns."""
    ana_id, bruno_id = chroma
    turn = "usuário mencionou viagem para o Japão"
    stub = _MappedEmbeddings({turn: [1.0, 0.0, 0.0]})
    monkeypatch.setattr(chroma_mcp, "get_embeddings", lambda: stub)

    for uid in (ana_id, bruno_id):
        chroma_mcp._collection(chroma_mcp._CHAT_MEMORY).upsert(
            ids=[f"turn-{uid}"],
            embeddings=[stub.embed_query(turn)],
            documents=[turn],
            metadatas=[require_user_id({"user_id": uid})],
        )

    hits = chroma_mcp.get_chat_context(user_id=ana_id, query=turn)

    assert [hit["id"] for hit in hits] == [f"turn-{ana_id}"]


def test_chroma_save_working_memory_persists_fact(chroma, monkeypatch):
    """Camada 3: save_working_memory upserts a structured fact scoped to user_id."""
    ana_id, _ = chroma
    fact = "meta: viagem para o Japão, valor estimado 8000"
    stub = _MappedEmbeddings({fact: [1.0, 0.0, 0.0]})
    monkeypatch.setattr(chroma_mcp, "get_embeddings", lambda: stub)

    result = chroma_mcp.save_working_memory(
        user_id=ana_id, fact=fact, metadata={"meta": "viagem", "valor_estimado": 8000}
    )

    stored = chroma_mcp._collection(chroma_mcp._WORKING_MEMORY).get(
        ids=[result["id"]], include=["documents", "metadatas"]
    )
    assert stored["documents"][0] == fact
    assert stored["metadatas"][0]["user_id"] == ana_id
    assert stored["metadatas"][0]["valor_estimado"] == 8000


# ---------------------------------------------------------------------------
# MCP client adapter + fallback (T18)
# ---------------------------------------------------------------------------


class _FailingMCPClient:
    """Stand-in for ``MultiServerMCPClient`` whose init/handshake fails (e.g. server won't spawn)."""

    async def get_tools(self):
        raise RuntimeError("mcp server failed to start")


class _SuccessfulMCPClient:
    def __init__(self, tools):
        self._tools = tools

    async def get_tools(self):
        return self._tools


_EXPECTED_FALLBACK_TOOL_NAMES = {
    "create_transaction",
    "list_transactions",
    "get_budget_summary",
    "get_balance",
    "update_transaction",
    "delete_transaction",
    "search_transactions",
    "find_similar_transactions",
    "query_knowledge",
    "get_chat_context",
    "save_working_memory",
}


def _fake_tool(name: str):
    def fake_tool():
        """Fake MCP tool used by client adapter tests."""
        return {"ok": True}

    return StructuredTool.from_function(fake_tool, name=name, description=f"{name} fake tool")


async def test_mcp_fallback_on_failure(caplog):
    """MCP-03: when the MCP client fails to initialize, the system logs a warning and starts with in-process tools."""
    with caplog.at_level(logging.WARNING):
        tools = await mcp_client.get_mcp_tools(client=_FailingMCPClient())

    assert {tool.name for tool in tools} == _EXPECTED_FALLBACK_TOOL_NAMES
    assert any(
        "falling back to in-process tools" in record.message for record in caplog.records
    )


async def test_mcp_tool_bundle_keeps_fallback_tools_on_success():
    primary_tools = [_fake_tool(name) for name in _EXPECTED_FALLBACK_TOOL_NAMES]

    bundle = await mcp_client.get_mcp_tool_bundle(client=_SuccessfulMCPClient(primary_tools))

    assert set(bundle.primary) == _EXPECTED_FALLBACK_TOOL_NAMES
    assert set(bundle.fallback) == _EXPECTED_FALLBACK_TOOL_NAMES
    assert bundle.primary["create_transaction"].name == "create_transaction"
    assert bundle.fallback["create_transaction"].name == "create_transaction"
    assert bundle.source == "mcp"


async def test_mcp_tool_bundle_falls_back_to_in_process_tools_on_failure(caplog):
    with caplog.at_level(logging.WARNING):
        bundle = await mcp_client.get_mcp_tool_bundle(client=_FailingMCPClient())

    assert set(bundle.primary) == _EXPECTED_FALLBACK_TOOL_NAMES
    assert set(bundle.fallback) == _EXPECTED_FALLBACK_TOOL_NAMES
    assert bundle.source == "fallback"
    assert bundle.primary["query_knowledge"] is bundle.fallback["query_knowledge"]
    assert any(
        "falling back to in-process tools" in record.message for record in caplog.records
    )


async def test_mcp_tool_bundle_uses_fallback_when_required_primary_tool_is_missing(caplog):
    missing_one = _EXPECTED_FALLBACK_TOOL_NAMES - {"query_knowledge"}
    primary_tools = [_fake_tool(name) for name in missing_one]

    with caplog.at_level(logging.WARNING):
        bundle = await mcp_client.get_mcp_tool_bundle(client=_SuccessfulMCPClient(primary_tools))

    assert set(bundle.primary) == _EXPECTED_FALLBACK_TOOL_NAMES
    assert bundle.source == "fallback"
    assert any("missing required MCP tools" in record.message for record in caplog.records)


def test_tool_map_rejects_duplicate_tool_names():
    duplicate_tools = [_fake_tool("query_knowledge"), _fake_tool("query_knowledge")]

    with pytest.raises(ValueError, match="Duplicate MCP tool name"):
        mcp_client.tool_map(duplicate_tools)
