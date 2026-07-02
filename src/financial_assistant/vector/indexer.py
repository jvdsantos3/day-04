"""Write-through vector indexer — sync SQLite ``Transaction`` rows into ChromaDB (T14).

SQLite stays the source of truth (spec: "Persistência Dual"); this module keeps the
``transactions`` ChromaDB collection in sync on create/update/delete. Embedding
generation uses the local model singleton (T13); client/collection setup and the
``user_id`` isolation guard come from T12 (``vector/client.py``).

Indexing failures never propagate to the caller — the SQLite write already
happened before this runs, so a ChromaDB or embedding hiccup must not crash the
write-through call. Failures are logged and queued for a later reindex attempt
(spec edge case: "embedding falhar na indexação").
"""

from __future__ import annotations

import logging
import uuid

from chromadb.api.models.Collection import Collection

from financial_assistant.domain.models import Transaction
from financial_assistant.vector.client import (
    get_chroma_client,
    get_or_create_collections,
    require_user_id,
)
from financial_assistant.vector.embeddings import get_embeddings

logger = logging.getLogger(__name__)

_TRANSACTIONS_COLLECTION = "transactions"

# In-memory queue of transactions whose indexing attempt failed and needs a retry.
_pending_reindex: list[dict[str, str]] = []


def get_pending_reindex() -> list[dict[str, str]]:
    """Return a snapshot of transactions queued for reindexing after a failure."""
    return list(_pending_reindex)


def clear_pending_reindex() -> None:
    """Empty the reindex queue (called by a future reindex worker after processing)."""
    _pending_reindex.clear()


def _get_transactions_collection() -> Collection:
    return get_or_create_collections(get_chroma_client())[_TRANSACTIONS_COLLECTION]


def _transaction_metadata(user_id: uuid.UUID, transaction: Transaction) -> dict[str, object]:
    require_user_id({"user_id": user_id})
    return {
        "user_id": str(user_id),
        "transaction_id": str(transaction.id),
        "category": transaction.category.value if transaction.category else None,
        "amount": float(transaction.amount),
        "date": transaction.date.isoformat(),
    }


def index_transaction(user_id: uuid.UUID, transaction: Transaction) -> None:
    """Embed ``transaction.description`` and upsert it into the ``transactions`` collection.

    On any failure (embedding generation or the ChromaDB write), logs the error and
    queues the transaction for a later reindex — SQLite is unaffected either way.
    """
    metadata = _transaction_metadata(user_id, transaction)
    try:
        vector = get_embeddings().embed_query(transaction.description)
        _get_transactions_collection().upsert(
            ids=[str(transaction.id)],
            embeddings=[vector],
            metadatas=[metadata],
            documents=[transaction.description],
        )
    except Exception:
        logger.exception(
            "failed to index transaction %s for user %s; queued for reindex",
            transaction.id,
            user_id,
        )
        _pending_reindex.append({"user_id": str(user_id), "transaction_id": str(transaction.id)})


def delete_transaction_embedding(user_id: uuid.UUID, transaction_id: uuid.UUID) -> None:
    """Remove the embedding for ``transaction_id`` scoped to ``user_id``.

    The ``where`` filter means a mismatched ``user_id`` deletes nothing — the same
    isolation invariant enforced on writes (AD-002).
    """
    require_user_id({"user_id": user_id})
    _get_transactions_collection().delete(
        ids=[str(transaction_id)],
        where={"user_id": str(user_id)},
    )
