"""Unit tests for the write-through vector indexer (T14, VEC-01/VEC-04)."""

import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest

from financial_assistant.config import Settings
from financial_assistant.domain.models import BudgetCategory, Transaction, TransactionType
from financial_assistant.vector import client as client_mod
from financial_assistant.vector import indexer

pytestmark = pytest.mark.unit


class _StubEmbeddings:
    """Deterministic stand-in for the T13 embedding singleton."""

    def __init__(self, vector=None, error=None):
        self._vector = vector if vector is not None else [0.1, 0.2, 0.3]
        self._error = error

    def embed_query(self, text: str):
        if self._error is not None:
            raise self._error
        return self._vector


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        date=date(2026, 7, 1),
        description="compra no mercado",
        type=TransactionType.EXPENSE,
        amount=Decimal("80.00"),
        category=BudgetCategory.PLEASURES,
    )
    defaults.update(overrides)
    return Transaction(**defaults)


@pytest.fixture(autouse=True)
def _isolate_indexer(tmp_path, monkeypatch):
    """Route ChromaDB at a per-test tmp_path and reset the reindex queue."""
    monkeypatch.setattr(
        client_mod,
        "get_settings",
        lambda: Settings(_env_file=None, chroma_path=str(tmp_path / "chroma")),
    )
    indexer.clear_pending_reindex()
    yield
    indexer.clear_pending_reindex()


def test_index_transaction_upserts_embedding_with_metadata(monkeypatch):
    """VEC-01: creating a transaction indexes its embedding with metadata linked to the SQLite id."""
    user_id = uuid.uuid4()
    transaction = _make_transaction(user_id=user_id)
    monkeypatch.setattr(indexer, "get_embeddings", lambda: _StubEmbeddings([0.1, 0.2, 0.3]))

    indexer.index_transaction(user_id, transaction)

    result = indexer._get_transactions_collection().get(
        ids=[str(transaction.id)], include=["metadatas", "documents", "embeddings"]
    )
    assert result["documents"][0] == "compra no mercado"
    assert result["metadatas"][0] == {
        "user_id": str(user_id),
        "transaction_id": str(transaction.id),
        "category": "prazeres",
        "amount": 80.0,
        "date": "2026-07-01",
    }
    assert list(result["embeddings"][0]) == pytest.approx([0.1, 0.2, 0.3])


def test_index_transaction_income_omits_category(monkeypatch):
    """Spec: incomes carry `categoria = NULL` — no category key is stored for them."""
    user_id = uuid.uuid4()
    transaction = _make_transaction(
        user_id=user_id, type=TransactionType.INCOME, category=None, description="salário"
    )
    monkeypatch.setattr(indexer, "get_embeddings", lambda: _StubEmbeddings())

    indexer.index_transaction(user_id, transaction)

    metadata = indexer._get_transactions_collection().get(ids=[str(transaction.id)])["metadatas"][0]
    assert "category" not in metadata


def test_index_transaction_upsert_replaces_previous_embedding(monkeypatch):
    """Fluxo write-through: re-indexing an updated transaction syncs (not duplicates) its embedding."""
    user_id = uuid.uuid4()
    transaction = _make_transaction(user_id=user_id)
    monkeypatch.setattr(indexer, "get_embeddings", lambda: _StubEmbeddings([0.1, 0.2, 0.3]))
    indexer.index_transaction(user_id, transaction)

    transaction.description = "compra atualizada no mercado"
    monkeypatch.setattr(indexer, "get_embeddings", lambda: _StubEmbeddings([0.9, 0.9, 0.9]))
    indexer.index_transaction(user_id, transaction)

    collection = indexer._get_transactions_collection()
    assert collection.count() == 1
    result = collection.get(ids=[str(transaction.id)], include=["documents", "embeddings"])
    assert result["documents"][0] == "compra atualizada no mercado"
    assert list(result["embeddings"][0]) == pytest.approx([0.9, 0.9, 0.9])


def test_delete_transaction_embedding_removes_vector(monkeypatch):
    """VEC-04: deleting a transaction in SQLite removes the corresponding ChromaDB embedding."""
    user_id = uuid.uuid4()
    transaction = _make_transaction(user_id=user_id)
    monkeypatch.setattr(indexer, "get_embeddings", lambda: _StubEmbeddings())
    indexer.index_transaction(user_id, transaction)

    indexer.delete_transaction_embedding(user_id, transaction.id)

    collection = indexer._get_transactions_collection()
    assert collection.count() == 0
    assert collection.get(ids=[str(transaction.id)])["ids"] == []


def test_delete_transaction_embedding_does_not_cross_user_boundary(monkeypatch):
    """AD-002 isolation: a mismatched user_id must not delete another user's embedding."""
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    transaction = _make_transaction(user_id=owner_id)
    monkeypatch.setattr(indexer, "get_embeddings", lambda: _StubEmbeddings())
    indexer.index_transaction(owner_id, transaction)

    indexer.delete_transaction_embedding(other_user_id, transaction.id)

    assert indexer._get_transactions_collection().count() == 1


def test_index_transaction_embedding_failure_queues_reindex_without_raising(monkeypatch, caplog):
    """Edge case: embedding failure logs, queues a reindex, and never raises — SQLite is untouched."""
    user_id = uuid.uuid4()
    transaction = _make_transaction(user_id=user_id)
    monkeypatch.setattr(
        indexer, "get_embeddings", lambda: _StubEmbeddings(error=RuntimeError("embedding backend down"))
    )

    with caplog.at_level(logging.ERROR):
        indexer.index_transaction(user_id, transaction)

    assert indexer.get_pending_reindex() == [
        {"user_id": str(user_id), "transaction_id": str(transaction.id)}
    ]
    assert indexer._get_transactions_collection().count() == 0
    assert any("failed to index transaction" in record.message for record in caplog.records)


def test_index_transaction_requires_user_id():
    """AD-002 guard reused before every write (per T12 handoff note)."""
    transaction = _make_transaction()

    with pytest.raises(ValueError, match="user_id"):
        indexer.index_transaction(None, transaction)


def test_delete_transaction_embedding_requires_user_id():
    """AD-002 guard reused before delete as well."""
    with pytest.raises(ValueError, match="user_id"):
        indexer.delete_transaction_embedding(None, uuid.uuid4())
