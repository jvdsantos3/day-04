"""chroma-mcp — MCP server exposing semantic search + cross-agent memory (T17).

Wraps the ChromaDB collections (T12) behind the Model Context Protocol so the
Atendimento, Transações and Insights specialists can search/remember without
touching ChromaDB directly (spec: "chroma-mcp — busca semântica", design.md
"chroma-mcp"). Every tool takes ``user_id`` as its first, mandatory parameter
and every user-scoped collection query (``transactions``, ``chat_memory``,
``working_memory``) filters ``where={"user_id": ...}`` — a vector written
under one user_id is never returned to another (AD-002).

``knowledge_base`` and ``category_examples`` hold shared content (T15,
``GLOBAL_USER_ID`` sentinel) rather than per-user data, so ``query_knowledge``
and the ``category_examples`` half of ``find_similar_transactions`` are not
filtered by the caller's ``user_id`` — ``user_id`` is still required on those
tools for signature consistency across chroma-mcp, not for row filtering.

``search_transactions`` is the only tool with a fallback: when the ChromaDB
query raises (ChromaDB down), it degrades to
``TransactionRepository.search_by_description`` (SQL LIKE) so search keeps
working without semantic ranking (spec VEC-05).
"""

from __future__ import annotations

import logging
import uuid

from mcp.server.fastmcp import FastMCP

from financial_assistant.config import get_settings
from financial_assistant.db.session import SessionLocal
from financial_assistant.domain.repositories.transaction_repository import (
    TransactionRepository,
)
from financial_assistant.vector.client import (
    get_chroma_client,
    get_or_create_collections,
    require_user_id,
)
from financial_assistant.vector.embeddings import get_embeddings
from financial_assistant.vector.knowledge_seed import GLOBAL_USER_ID
from financial_assistant.vector.knowledge_seed import query_knowledge as _query_knowledge_base

logger = logging.getLogger(__name__)

mcp = FastMCP("chroma-mcp")

_TRANSACTIONS = "transactions"
_CHAT_MEMORY = "chat_memory"
_CATEGORY_EXAMPLES = "category_examples"
_WORKING_MEMORY = "working_memory"


def _collection(name: str):
    return get_or_create_collections(get_chroma_client())[name]


def _similarity(distance: float) -> float:
    """Cosine similarity derived from ChromaDB's squared-L2 distance on normalized vectors.

    T13's embeddings are L2-normalized, so for unit vectors ``distance == 2 * (1 - cos)``.
    """
    return 1 - distance / 2


def _semantic_query(collection_name: str, query_text: str, n_results: int, where: dict) -> list[dict]:
    collection = _collection(collection_name)
    if collection.count() == 0:
        return []
    vector = get_embeddings().embed_query(query_text)
    result = collection.query(query_embeddings=[vector], n_results=n_results, where=where)
    return [
        {"id": id_, "document": document, "metadata": metadata, "score": _similarity(distance)}
        for id_, document, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


def _fallback_hit(transaction) -> dict:
    return {
        "id": str(transaction.id),
        "document": transaction.description,
        "metadata": {
            "transaction_id": str(transaction.id),
            "category": transaction.category.value if transaction.category else None,
            "amount": float(transaction.amount),
            "date": transaction.date.isoformat(),
        },
        "score": None,
    }


@mcp.tool()
def search_transactions(user_id: str, query: str, n_results: int = 5) -> list[dict]:
    """VEC-02: semantic search over the caller's transactions, filtered by a configurable score threshold.

    VEC-05 fallback: if the ChromaDB query fails (ChromaDB down), degrades to
    ``TransactionRepository.search_by_description`` (SQL LIKE) so search never
    blocks CRUD.
    """
    try:
        hits = _semantic_query(_TRANSACTIONS, query, n_results, where={"user_id": user_id})
        threshold = get_settings().chroma_similarity_threshold
        return [hit for hit in hits if hit["score"] >= threshold]
    except Exception:
        logger.exception(
            "chroma-mcp: search_transactions failed for user %s; falling back to SQL LIKE (VEC-05)",
            user_id,
        )
        with SessionLocal() as session:
            rows = TransactionRepository(session).search_by_description(uuid.UUID(user_id), query)
            return [_fallback_hit(row) for row in rows]


@mcp.tool()
def find_similar_transactions(user_id: str, description: str, n_results: int = 3) -> list[dict]:
    """Blend the caller's own transaction history with the shared category_examples for auto-categorization.

    Combines the ``transactions`` (user-scoped) and ``category_examples``
    (global, T15) collections, sorted by similarity — the T15 handoff note's
    "combina transactions + category_examples".
    """
    own = _semantic_query(_TRANSACTIONS, description, n_results, where={"user_id": user_id})
    for hit in own:
        hit["source"] = "transaction"
    examples = _semantic_query(
        _CATEGORY_EXAMPLES, description, n_results, where={"user_id": GLOBAL_USER_ID}
    )
    for hit in examples:
        hit["source"] = "category_example"
    combined = sorted(own + examples, key=lambda hit: hit["score"], reverse=True)
    return combined[:n_results]


@mcp.tool()
def query_knowledge(user_id: str, query: str, n_results: int = 3) -> list[dict]:
    """VEC-03: RAG over the shared knowledge_base (T15).

    ``knowledge_base`` holds global content, not per-user data (T15 handoff
    note) — ``user_id`` is accepted for signature consistency across
    chroma-mcp tools but is not used to filter rows here.
    """
    del user_id
    return _query_knowledge_base(query, n_results=n_results)


@mcp.tool()
def get_chat_context(user_id: str, query: str, n_results: int = 5) -> list[dict]:
    """Semantic recall over the caller's chat_memory turns (cross-session memory, Camada 3)."""
    return _semantic_query(_CHAT_MEMORY, query, n_results, where={"user_id": user_id})


@mcp.tool()
def save_working_memory(user_id: str, fact: str, metadata: dict | None = None) -> dict:
    """Persist a structured fact extracted by a specialist, visible to other agents this session.

    E.g. ``{"meta": "viagem", "valor_estimado": 8000, "categoria": "conhecimento_metas"}``
    (spec "Camada 3 — working_memory").
    """
    fact_id = str(uuid.uuid4())
    payload = require_user_id({"user_id": user_id, **(metadata or {})})
    vector = get_embeddings().embed_query(fact)
    _collection(_WORKING_MEMORY).upsert(
        ids=[fact_id], embeddings=[vector], documents=[fact], metadatas=[payload]
    )
    return {"id": fact_id, "fact": fact}
