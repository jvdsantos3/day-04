"""Unit tests for the local embedding model loader (T13)."""

import pytest

from financial_assistant.vector.embeddings import EMBEDDING_DIMENSION, get_embeddings

pytestmark = pytest.mark.unit


def test_embedding_dimension_is_384():
    embeddings = get_embeddings()

    vector = embeddings.embed_query("compra no mercado")

    assert len(vector) == EMBEDDING_DIMENSION == 384


def test_get_embeddings_returns_cached_singleton():
    first = get_embeddings()
    second = get_embeddings()

    assert first is second
