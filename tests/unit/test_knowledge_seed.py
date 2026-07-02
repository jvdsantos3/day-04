"""Unit tests for the budget knowledge base + category examples seed (T15, CONV-01/VEC-03)."""

import pytest

from financial_assistant.config import Settings
from financial_assistant.domain.models import BudgetCategory
from financial_assistant.vector import client as client_mod
from financial_assistant.vector import knowledge_seed

pytestmark = pytest.mark.unit


class _KeywordEmbeddings:
    """Deterministic stand-in for the T13 singleton — one-hot vector by category keyword."""

    _KEYWORDS = [category.value.replace("_", " ") for category in BudgetCategory]

    def _vector_for(self, text: str) -> list[float]:
        lowered = text.lower()
        vector = [0.0] * (len(self._KEYWORDS) + 1)
        matched = False
        for index, keyword in enumerate(self._KEYWORDS):
            if keyword in lowered:
                vector[index] = 1.0
                matched = True
        if not matched:
            vector[-1] = 1.0
        return vector

    def embed_documents(self, texts):
        return [self._vector_for(text) for text in texts]

    def embed_query(self, text):
        return self._vector_for(text)


@pytest.fixture(autouse=True)
def _isolate_knowledge_seed(tmp_path, monkeypatch):
    """Route ChromaDB at a per-test tmp_path and stub embeddings deterministically."""
    monkeypatch.setattr(
        client_mod,
        "get_settings",
        lambda: Settings(_env_file=None, chroma_path=str(tmp_path / "chroma")),
    )
    monkeypatch.setattr(knowledge_seed, "get_embeddings", lambda: _KeywordEmbeddings())
    yield


def test_seed_knowledge_base_indexes_all_five_categories_plus_overview():
    count = knowledge_seed.seed_knowledge_base()

    collection = knowledge_seed._get_collection(knowledge_seed._KNOWLEDGE_BASE_COLLECTION)
    stored = collection.get(include=["metadatas"])
    categories = {meta["category"] for meta in stored["metadatas"] if "category" in meta}

    assert count == len(knowledge_seed.CATEGORY_KNOWLEDGE_DOCS)
    assert categories == {category.value for category in BudgetCategory}
    assert all(meta["user_id"] == knowledge_seed.GLOBAL_USER_ID for meta in stored["metadatas"])


def test_seed_knowledge_base_is_idempotent():
    knowledge_seed.seed_knowledge_base()
    knowledge_seed.seed_knowledge_base()

    collection = knowledge_seed._get_collection(knowledge_seed._KNOWLEDGE_BASE_COLLECTION)
    assert collection.count() == len(knowledge_seed.CATEGORY_KNOWLEDGE_DOCS)


def test_seed_category_examples_labels_by_category():
    count = knowledge_seed.seed_category_examples()

    collection = knowledge_seed._get_collection(knowledge_seed._CATEGORY_EXAMPLES_COLLECTION)
    stored = collection.get(include=["documents", "metadatas"])
    category_by_description = dict(
        zip(stored["documents"], (meta["category"] for meta in stored["metadatas"]))
    )

    assert count == len(knowledge_seed.CATEGORY_EXAMPLE_SEEDS)
    assert category_by_description["compra no mercado"] == BudgetCategory.FIXED.value
    assert category_by_description["cinema com amigos"] == BudgetCategory.PLEASURES.value
    assert all(meta["user_id"] == knowledge_seed.GLOBAL_USER_ID for meta in stored["metadatas"])


def test_seed_category_examples_is_idempotent():
    knowledge_seed.seed_category_examples()
    knowledge_seed.seed_category_examples()

    collection = knowledge_seed._get_collection(knowledge_seed._CATEGORY_EXAMPLES_COLLECTION)
    assert collection.count() == len(knowledge_seed.CATEGORY_EXAMPLE_SEEDS)


def test_seed_all_seeds_both_collections():
    counts = knowledge_seed.seed_all()

    assert counts == {
        "knowledge_base": len(knowledge_seed.CATEGORY_KNOWLEDGE_DOCS),
        "category_examples": len(knowledge_seed.CATEGORY_EXAMPLE_SEEDS),
    }


def test_query_knowledge_returns_relevant_doc_for_custos_fixos():
    """VEC-03: query_knowledge("custos fixos") surfaces the Custos Fixos rule doc."""
    knowledge_seed.seed_knowledge_base()

    results = knowledge_seed.query_knowledge("custos fixos")

    assert results
    assert results[0]["metadata"]["category"] == BudgetCategory.FIXED.value
    assert "Custos Fixos" in results[0]["document"]


def test_query_knowledge_returns_empty_when_not_seeded():
    results = knowledge_seed.query_knowledge("custos fixos")

    assert results == []
