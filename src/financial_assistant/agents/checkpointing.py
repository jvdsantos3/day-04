"""LangGraph checkpointing helpers."""

from __future__ import annotations

import atexit
from contextlib import AbstractContextManager
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from financial_assistant.config import Settings, get_settings

_ACTIVE_CONTEXTS: list[AbstractContextManager[Any]] = []


def _close_active_contexts() -> None:
    while _ACTIVE_CONTEXTS:
        _ACTIVE_CONTEXTS.pop().__exit__(None, None, None)


atexit.register(_close_active_contexts)


def graph_config(session_id: str) -> dict:
    """Return LangGraph invocation config keyed by the stable chat session id."""
    return {"configurable": {"thread_id": session_id}}


def build_checkpointer(
    *, settings: Settings | None = None, checkpointer: Any | None = None
) -> Any:
    """Build the runtime SQLite checkpointer, or return an injected test saver."""
    if checkpointer is not None:
        return checkpointer

    active_settings = settings if settings is not None else get_settings()
    saver_context = SqliteSaver.from_conn_string(active_settings.checkpoint_db_path)
    if hasattr(saver_context, "__enter__"):
        saver = saver_context.__enter__()
        _ACTIVE_CONTEXTS.append(saver_context)
        return saver
    return saver_context
