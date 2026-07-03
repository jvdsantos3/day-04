"""Unit tests for graph-build-time concerns (MCP-01/MCP-03).

Covers the fix for a gap the feature Verifier found: ``get_mcp_tools()``
(T18) was fully unit-tested in isolation but nothing in the running app ever
called it, so the finance-mcp/chroma-mcp connect-or-fallback lifecycle never
actually happened. ``build_graph()`` now triggers it via ``_load_mcp_tools``,
cached so the connection attempt only runs once per process.
"""

from __future__ import annotations

import pytest

from financial_assistant.agents import graph as graph_module

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_mcp_tools_cache():
    """Isolate the process-wide cache so tests don't leak state into each other."""
    graph_module._load_mcp_tools.cache_clear()
    yield
    graph_module._load_mcp_tools.cache_clear()


def test_build_graph_loads_mcp_tools_exactly_once(monkeypatch):
    calls = {"n": 0}

    async def fake_get_mcp_tools():
        calls["n"] += 1
        return []

    monkeypatch.setattr(graph_module, "get_mcp_tools", fake_get_mcp_tools)

    graph_module.build_graph()
    graph_module.build_graph()

    assert calls["n"] == 1  # MCP-01: connects at startup, cached — not per build_graph() call


def test_build_graph_succeeds_when_mcp_falls_back_to_in_process_tools(monkeypatch):
    """MCP-03's fallback (already unit-tested in isolation at
    tests/integration/test_mcp.py::test_mcp_fallback_on_failure) doesn't
    prevent the graph from compiling once it resolves."""
    from financial_assistant.mcp.client import in_process_tools

    async def fallback_get_mcp_tools():
        return in_process_tools()

    monkeypatch.setattr(graph_module, "get_mcp_tools", fallback_get_mcp_tools)

    compiled = graph_module.build_graph()

    assert compiled is not None
