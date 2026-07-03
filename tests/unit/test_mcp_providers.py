"""Unit tests for typed MCP providers (AHR-MCP-01/AHR-MCP-02/AHR-MCP-03/AHR-MEM-01)."""

from __future__ import annotations

import logging

import pytest

from financial_assistant.mcp.client import ToolBundle
from financial_assistant.mcp.providers import (
    ChromaToolProvider,
    FinanceToolProvider,
    ProviderToolError,
    ToolResult,
)

pytestmark = pytest.mark.unit


class RecordingTool:
    def __init__(self, name: str, result=None, exc: Exception | None = None):
        self.name = name
        self.result = result
        self.exc = exc
        self.calls: list[dict] = []

    def invoke(self, arguments: dict):
        self.calls.append(arguments)
        if self.exc is not None:
            raise self.exc
        return self.result


def _bundle(primary: dict[str, RecordingTool], fallback: dict[str, RecordingTool] | None = None):
    return ToolBundle(primary=primary, fallback=fallback or {}, source="mcp")


def test_tool_result_audit_metadata_excludes_raw_payload_fields():
    result = ToolResult(
        data={"description": "pedido de delivery", "amount": "20.00"},
        tool_name="create_transaction",
        source="mcp",
        fallback_used=False,
    )

    assert result.audit_metadata() == {
        "tool": "create_transaction",
        "source": "mcp",
        "fallback_used": False,
        "status": "ok",
    }


@pytest.mark.parametrize(
    ("provider_factory", "method_name", "arguments"),
    [
        (FinanceToolProvider, "create_transaction", {"date": "2026-07-01", "description": "mercado", "type": "despesa", "amount": "80.00", "category": "custos_fixos"}),
        (FinanceToolProvider, "list_transactions", {}),
        (FinanceToolProvider, "get_budget_summary", {"month": "2026-07"}),
        (FinanceToolProvider, "get_balance", {}),
        (FinanceToolProvider, "update_transaction", {"transaction_id": "tx-1", "amount": "90.00"}),
        (FinanceToolProvider, "delete_transaction", {"transaction_id": "tx-1"}),
        (ChromaToolProvider, "search_transactions", {"query": "mercado"}),
        (ChromaToolProvider, "find_similar_transactions", {"description": "delivery"}),
        (ChromaToolProvider, "query_knowledge", {"query": "plano de gastos"}),
        (ChromaToolProvider, "get_chat_context", {"query": "viagem"}),
        (ChromaToolProvider, "save_working_memory", {"fact": "usuario tem meta de viagem", "metadata": {"kind": "goal"}}),
    ],
)
def test_provider_methods_reject_empty_user_id_before_invoking_tools(
    provider_factory, method_name, arguments
):
    tool = RecordingTool(method_name, result={"ok": True})
    provider = provider_factory(_bundle({method_name: tool}))

    with pytest.raises(ProviderToolError, match="user_id is required"):
        getattr(provider, method_name)(user_id=" ", **arguments)

    assert tool.calls == []


def test_finance_provider_calls_primary_tool_and_emits_sanitized_events():
    events = []
    primary = RecordingTool(
        "create_transaction",
        result={"id": "tx-1", "description": "pedido de delivery", "amount": "20.00"},
    )
    provider = FinanceToolProvider(
        _bundle({"create_transaction": primary}),
        event_emitter=events.append,
    )

    result = provider.create_transaction(
        user_id="user-1",
        date="2026-07-01",
        description="pedido de delivery",
        type="despesa",
        amount="20.00",
        category="prazeres",
    )

    assert result == ToolResult(
        data={"id": "tx-1", "description": "pedido de delivery", "amount": "20.00"},
        tool_name="create_transaction",
        source="mcp",
        fallback_used=False,
    )
    assert primary.calls == [
        {
            "user_id": "user-1",
            "date": "2026-07-01",
            "description": "pedido de delivery",
            "type": "despesa",
            "amount": "20.00",
            "category": "prazeres",
        }
    ]
    assert [event.event for event in events] == ["tool_call", "tool_result"]
    assert events[0].data == {"tool": "create_transaction", "source": "mcp", "status": "started"}
    assert events[1].data == {
        "tool": "create_transaction",
        "source": "mcp",
        "fallback_used": False,
        "status": "ok",
    }


def test_provider_uses_fallback_when_primary_tool_fails(caplog):
    primary = RecordingTool("query_knowledge", exc=RuntimeError("stdio down"))
    fallback = RecordingTool(
        "query_knowledge",
        result=[{"doc_id": "kb-budget", "metadata": {"category": "overview"}}],
    )
    provider = ChromaToolProvider(
        _bundle({"query_knowledge": primary}, {"query_knowledge": fallback})
    )

    with caplog.at_level(logging.WARNING):
        result = provider.query_knowledge(
            user_id="user-1",
            query="plano de gastos",
            n_results=6,
        )

    assert result.data == [{"doc_id": "kb-budget", "metadata": {"category": "overview"}}]
    assert result.audit_metadata() == {
        "tool": "query_knowledge",
        "source": "fallback",
        "fallback_used": True,
        "status": "ok",
    }
    assert primary.calls == [{"user_id": "user-1", "query": "plano de gastos", "n_results": 6}]
    assert fallback.calls == [{"user_id": "user-1", "query": "plano de gastos", "n_results": 6}]
    assert any(
        record.tool == "query_knowledge" and record.fallback_used is True
        for record in caplog.records
    )


def test_provider_raises_typed_error_when_primary_and_fallback_fail():
    primary = RecordingTool("get_balance", exc=RuntimeError("mcp down"))
    fallback = RecordingTool("get_balance", exc=RuntimeError("sqlite down"))
    provider = FinanceToolProvider(_bundle({"get_balance": primary}, {"get_balance": fallback}))

    with pytest.raises(ProviderToolError) as exc_info:
        provider.get_balance(user_id="user-1", month="2026-07")

    assert exc_info.value.tool_name == "get_balance"
    assert exc_info.value.recoverable is False
    assert primary.calls == [{"user_id": "user-1", "month": "2026-07"}]
    assert fallback.calls == [{"user_id": "user-1", "month": "2026-07"}]
