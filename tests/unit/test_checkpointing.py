"""Unit tests for LangGraph checkpointing support (AHR-CHK-01/AHR-CHK-02)."""

import pytest

from financial_assistant.agents import checkpointing
from financial_assistant.config import Settings

pytestmark = pytest.mark.unit


def test_graph_config_uses_session_id_as_thread_id():
    config = checkpointing.graph_config("sessao-123")

    assert config == {"configurable": {"thread_id": "sessao-123"}}


def test_build_checkpointer_returns_injected_saver():
    injected = object()

    checkpointer = checkpointing.build_checkpointer(checkpointer=injected)

    assert checkpointer is injected


def test_build_checkpointer_uses_configured_sqlite_path(monkeypatch):
    created = {}

    class FakeSqliteSaver:
        @classmethod
        def from_conn_string(cls, conn_string):
            created["conn_string"] = conn_string
            return "sqlite-saver"

    monkeypatch.setattr(checkpointing, "SqliteSaver", FakeSqliteSaver)

    checkpointer = checkpointing.build_checkpointer(
        settings=Settings(_env_file=None, checkpoint_db_path="/tmp/checkpoints.sqlite")
    )

    assert checkpointer == "sqlite-saver"
    assert created["conn_string"] == "/tmp/checkpoints.sqlite"
