"""Budget knowledge base + category examples seed (T15, CONV-01/VEC-03).

Seeds two of the five ChromaDB collections (T12) with shared reference content:

- ``knowledge_base``: the five envelope-budget categories, their target ranges
  and spending examples (spec "Framework de Orçamento") — RAG source for the
  Atendimento specialist's ``query_knowledge`` tool.
- ``category_examples``: labeled expense descriptions per category — few-shot
  source for the Transações specialist's auto-categorization.

Both collections hold shared knowledge, not data owned by a single user — but
every ChromaDB vector must carry a non-empty ``user_id`` (AD-002, enforced by
``vector.client.require_user_id``). ``GLOBAL_USER_ID`` is the sentinel used for
this shared content, distinct from the per-user isolation applied to
``transactions``/``chat_memory``/``working_memory``.

Seeding upserts by a fixed, deterministic id per doc/example, so re-running it
is idempotent — safe to call on every app startup.
"""

from __future__ import annotations

from dataclasses import dataclass

from chromadb.api.models.Collection import Collection

from financial_assistant.domain.models import BudgetCategory
from financial_assistant.vector.client import (
    get_chroma_client,
    get_or_create_collections,
    require_user_id,
)
from financial_assistant.vector.embeddings import get_embeddings

_KNOWLEDGE_BASE_COLLECTION = "knowledge_base"
_CATEGORY_EXAMPLES_COLLECTION = "category_examples"

GLOBAL_USER_ID = "system"


@dataclass(frozen=True)
class KnowledgeDoc:
    """A single RAG-able document for the ``knowledge_base`` collection."""

    doc_id: str
    category: BudgetCategory | None
    text: str


@dataclass(frozen=True)
class CategoryExample:
    """A labeled expense description for the ``category_examples`` collection."""

    example_id: str
    category: BudgetCategory
    description: str


# One rule doc per category (range + examples, spec "Framework de Orçamento")
# plus an overview doc summarizing all five for "plano de gastos"-style questions.
CATEGORY_KNOWLEDGE_DOCS: tuple[KnowledgeDoc, ...] = (
    KnowledgeDoc(
        "kb-custos_fixos",
        BudgetCategory.FIXED,
        "Custos Fixos (30-40% da renda mensal): despesas essenciais e recorrentes — "
        "aluguel, condomínio, luz, água, parcelas de financiamento e compras de mercado.",
    ),
    KnowledgeDoc(
        "kb-conforto",
        BudgetCategory.COMFORT,
        "Conforto (15-20% da renda mensal): itens que elevam a qualidade de vida sem "
        "ser essenciais — diarista, assinaturas de streaming, internet.",
    ),
    KnowledgeDoc(
        "kb-investimentos",
        BudgetCategory.INVESTMENTS,
        "Investimentos (15-25% da renda mensal): aportes em reserva de emergência, "
        "ações, CDBs e formação de patrimônio de longo prazo.",
    ),
    KnowledgeDoc(
        "kb-conhecimento_metas",
        BudgetCategory.KNOWLEDGE,
        "Conhecimento e Metas (5-15% da renda mensal): cursos, livros e viagens "
        "planejadas — investimento em desenvolvimento pessoal e objetivos futuros.",
    ),
    KnowledgeDoc(
        "kb-prazeres",
        BudgetCategory.PLEASURES,
        "Prazeres (mínimo 5% da renda mensal, sem teto): cinema, restaurantes, "
        "delivery e lazer em geral.",
    ),
    KnowledgeDoc(
        "kb-overview",
        None,
        "O orçamento do Assistente Financeiro divide a renda mensal em 5 categorias: "
        "Custos Fixos (30-40%), Conforto (15-20%), Investimentos (15-25%), "
        "Conhecimento e Metas (5-15%) e Prazeres (mínimo 5%). Os defaults somam 90%, "
        "deixando 10% de margem de flexibilidade.",
    ),
)

# Labeled historical-style descriptions per category — few-shot examples for
# auto-categorization (e.g. "mercado" -> custos_fixos, "cinema" -> prazeres).
CATEGORY_EXAMPLE_SEEDS: tuple[CategoryExample, ...] = (
    CategoryExample("ex-custos_fixos-1", BudgetCategory.FIXED, "compra no mercado"),
    CategoryExample("ex-custos_fixos-2", BudgetCategory.FIXED, "conta de luz"),
    CategoryExample("ex-custos_fixos-3", BudgetCategory.FIXED, "aluguel do apartamento"),
    CategoryExample("ex-conforto-1", BudgetCategory.COMFORT, "assinatura de streaming"),
    CategoryExample("ex-conforto-2", BudgetCategory.COMFORT, "diarista quinzenal"),
    CategoryExample("ex-investimentos-1", BudgetCategory.INVESTMENTS, "aporte na reserva de emergência"),
    CategoryExample("ex-investimentos-2", BudgetCategory.INVESTMENTS, "compra de ações"),
    CategoryExample("ex-conhecimento_metas-1", BudgetCategory.KNOWLEDGE, "curso de inglês online"),
    CategoryExample("ex-conhecimento_metas-2", BudgetCategory.KNOWLEDGE, "livro de finanças pessoais"),
    CategoryExample("ex-prazeres-1", BudgetCategory.PLEASURES, "cinema com amigos"),
    CategoryExample("ex-prazeres-2", BudgetCategory.PLEASURES, "pedido de delivery"),
    CategoryExample("ex-prazeres-3", BudgetCategory.PLEASURES, "jantar em restaurante"),
)


def _get_collection(name: str) -> Collection:
    return get_or_create_collections(get_chroma_client())[name]


def seed_knowledge_base() -> int:
    """Upsert the category rule docs + overview into ``knowledge_base``. Idempotent."""
    metadata = require_user_id({"user_id": GLOBAL_USER_ID})
    docs = CATEGORY_KNOWLEDGE_DOCS
    vectors = get_embeddings().embed_documents([doc.text for doc in docs])
    _get_collection(_KNOWLEDGE_BASE_COLLECTION).upsert(
        ids=[doc.doc_id for doc in docs],
        embeddings=vectors,
        documents=[doc.text for doc in docs],
        metadatas=[
            {
                **metadata,
                "doc_id": doc.doc_id,
                **({"category": doc.category.value} if doc.category else {}),
            }
            for doc in docs
        ],
    )
    return len(docs)


def seed_category_examples() -> int:
    """Upsert labeled expense descriptions into ``category_examples``. Idempotent."""
    metadata = require_user_id({"user_id": GLOBAL_USER_ID})
    examples = CATEGORY_EXAMPLE_SEEDS
    vectors = get_embeddings().embed_documents([example.description for example in examples])
    _get_collection(_CATEGORY_EXAMPLES_COLLECTION).upsert(
        ids=[example.example_id for example in examples],
        embeddings=vectors,
        documents=[example.description for example in examples],
        metadatas=[
            {**metadata, "example_id": example.example_id, "category": example.category.value}
            for example in examples
        ],
    )
    return len(examples)


def seed_all() -> dict[str, int]:
    """Seed both collections. Returns the number of docs written to each."""
    return {
        "knowledge_base": seed_knowledge_base(),
        "category_examples": seed_category_examples(),
    }


def query_knowledge(query: str, n_results: int = 3) -> list[dict[str, object]]:
    """Semantic search over ``knowledge_base`` (VEC-03) — RAG for the Atendimento specialist.

    Returns up to ``n_results`` hits, each with ``doc_id``, ``document`` and
    ``metadata`` (carries ``category`` when the doc is category-specific), so
    callers can cite the source collection + doc (spec AC: "citar a fonte").
    """
    vector = get_embeddings().embed_query(query)
    collection = _get_collection(_KNOWLEDGE_BASE_COLLECTION)
    if collection.count() == 0:
        return []
    result = collection.query(query_embeddings=[vector], n_results=n_results)
    return [
        {"doc_id": doc_id, "document": document, "metadata": metadata}
        for doc_id, document, metadata in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0]
        )
    ]
