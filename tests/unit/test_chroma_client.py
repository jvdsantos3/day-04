"""Unit tests for the ChromaDB persistent client and collections (T12, VEC-01)."""

import os

import pytest

from financial_assistant.vector.client import (
    COLLECTIONS,
    get_chroma_client,
    get_or_create_collections,
    require_user_id,
)

pytestmark = pytest.mark.unit

EXPECTED_COLLECTIONS = {
    "transactions",
    "chat_memory",
    "knowledge_base",
    "category_examples",
    "working_memory",
}


def test_collections_are_the_five_semantic_stores():
    """Spec (Persistência Dual): exactly these five collections exist."""
    assert set(COLLECTIONS) == EXPECTED_COLLECTIONS


def test_get_or_create_creates_all_five_collections(tmp_path):
    client = get_chroma_client(str(tmp_path / "chroma"))

    cols = get_or_create_collections(client)

    assert set(cols) == EXPECTED_COLLECTIONS
    assert {c.name for c in client.list_collections()} == EXPECTED_COLLECTIONS


def test_get_or_create_collections_is_idempotent(tmp_path):
    client = get_chroma_client(str(tmp_path / "chroma"))

    first = get_or_create_collections(client)
    second = get_or_create_collections(client)

    assert {c.id for c in first.values()} == {c.id for c in second.values()}
    assert len(client.list_collections()) == len(EXPECTED_COLLECTIONS)


def test_persistent_client_survives_reopen(tmp_path):
    """VEC-01: the client persists to disk; data (with user_id) survives reopen."""
    path = str(tmp_path / "chroma")

    client = get_chroma_client(path)
    get_or_create_collections(client)["transactions"].add(
        ids=["t1"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"user_id": "u1", "transaction_id": "t1"}],
        documents=["mercado"],
    )
    del client

    reopened = get_chroma_client(path)
    col = reopened.get_collection("transactions")
    assert col.count() == 1
    assert col.get(ids=["t1"])["metadatas"][0]["user_id"] == "u1"


def test_get_chroma_client_defaults_to_settings_path(tmp_path, monkeypatch):
    """T8/T2 dependency: with no explicit path, the client roots at CHROMA_PATH."""
    import financial_assistant.vector.client as client_mod
    from financial_assistant.config import Settings

    target = str(tmp_path / "from-settings")
    monkeypatch.setattr(
        client_mod,
        "get_settings",
        lambda: Settings(_env_file=None, chroma_path=target),
    )

    get_or_create_collections(get_chroma_client())

    assert os.path.isdir(target)


def test_require_user_id_returns_validated_copy():
    metadata = {"user_id": "u1", "transaction_id": "t1"}

    result = require_user_id(metadata)

    assert result == metadata
    assert result is not metadata  # defensive copy, not the caller's dict


@pytest.mark.parametrize(
    "bad_metadata",
    [
        {},  # no user_id at all
        {"transaction_id": "t1"},  # other fields but user_id missing
        {"user_id": ""},  # present but empty
        {"user_id": None},  # present but null
    ],
)
def test_require_user_id_rejects_metadata_without_user_id(bad_metadata):
    """AD-002: every vector must be attributable to a user."""
    with pytest.raises(ValueError, match="user_id"):
        require_user_id(bad_metadata)


def test_require_user_id_rejects_none_metadata():
    with pytest.raises(ValueError, match="user_id"):
        require_user_id(None)
