"""ChromaDB persistent client and collection setup (T12, VEC-01).

SQLite is the source of truth; ChromaDB is the semantic index. This module owns
the persistent client and the five collections the assistant uses, and enforces
the multi-user isolation invariant (AD-002): every vector's metadata MUST carry
a non-empty ``user_id`` so reads can be filtered per user.

Embedding generation lives in the indexer (T14) using the local model (T13);
this module deliberately stays embedding-agnostic — it only wires up the
persistent store and its collections.
"""

from __future__ import annotations

from typing import Mapping

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from financial_assistant.config import get_settings

# The five semantic collections (spec: "ChromaDB — coleções vetoriais").
COLLECTIONS: tuple[str, ...] = (
    "transactions",
    "chat_memory",
    "knowledge_base",
    "category_examples",
    "working_memory",
)

# Metadata keys required on every stored vector, in every collection.
# Enforces per-user isolation (AD-002 / VEC-01).
REQUIRED_METADATA_KEYS: frozenset[str] = frozenset({"user_id"})


def get_chroma_client(path: str | None = None) -> ClientAPI:
    """Return a persistent ChromaDB client rooted at ``path``.

    Defaults to ``settings.chroma_path`` (CHROMA_PATH). ChromaDB creates the
    directory on first use.
    """
    chroma_path = path or get_settings().chroma_path
    return chromadb.PersistentClient(path=chroma_path)


def get_or_create_collections(client: ClientAPI) -> dict[str, Collection]:
    """Create (or fetch) all five semantic collections. Idempotent."""
    return {name: client.get_or_create_collection(name=name) for name in COLLECTIONS}


def require_user_id(metadata: Mapping[str, object] | None) -> dict[str, object]:
    """Validate that ``metadata`` carries a non-empty ``user_id``.

    Every vector written to any collection must be attributable to a user so
    reads can be filtered by ``user_id`` (AD-002). Returns a plain ``dict`` copy
    of the validated metadata; raises :class:`ValueError` when the invariant is
    violated.
    """
    if metadata is None:
        raise ValueError("metadata is required and must include: user_id")
    missing = sorted(key for key in REQUIRED_METADATA_KEYS if not metadata.get(key))
    if missing:
        raise ValueError(f"metadata missing required keys: {', '.join(missing)}")
    return dict(metadata)
