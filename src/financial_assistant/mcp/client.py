"""MCP client wrapper with in-process fallback (T18).

Connects to the ``finance-mcp`` (T16) and ``chroma-mcp`` (T17) servers as
stdio subprocesses via ``langchain-mcp-adapters``' ``MultiServerMCPClient``
(design.md "MCPs — Usabilidade no Projeto" conceptual snippet). If the MCP
client fails to initialize (either server fails to spawn/handshake), the
system SHALL log a warning and start with in-process tools equivalent to the
MCP tools (spec P1 "MCPs operacionais" AC3, requirement MCP-03) instead of
crashing agent startup.

The in-process fallback wraps the same Python functions the MCP servers
expose (``@mcp.tool()`` returns the original function unchanged, per T16's
handoff note) as LangChain ``StructuredTool``s — no subprocess/stdio, just a
direct in-memory call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection

from mcp_servers.chroma import server as chroma_mcp
from mcp_servers.finance import server as finance_mcp

logger = logging.getLogger(__name__)

MCP_CONNECTIONS: dict[str, StdioConnection] = {
    "finance": {"transport": "stdio", "command": "python", "args": ["-m", "mcp_servers.finance"]},
    "chroma": {"transport": "stdio", "command": "python", "args": ["-m", "mcp_servers.chroma"]},
}

_FINANCE_TOOL_FUNCS = (
    finance_mcp.create_transaction,
    finance_mcp.list_transactions,
    finance_mcp.get_budget_summary,
    finance_mcp.get_balance,
    finance_mcp.update_transaction,
    finance_mcp.delete_transaction,
)

_CHROMA_TOOL_FUNCS = (
    chroma_mcp.search_transactions,
    chroma_mcp.find_similar_transactions,
    chroma_mcp.query_knowledge,
    chroma_mcp.get_chat_context,
    chroma_mcp.save_working_memory,
)

_REQUIRED_TOOL_NAMES = frozenset(
    func.__name__ for func in (*_FINANCE_TOOL_FUNCS, *_CHROMA_TOOL_FUNCS)
)


@dataclass(frozen=True)
class ToolBundle:
    """Primary MCP tools plus in-process fallback tools keyed by tool name."""

    primary: dict[str, BaseTool]
    fallback: dict[str, BaseTool]
    source: Literal["mcp", "fallback"]


def in_process_tools() -> list[BaseTool]:
    """Build the fallback tool set: finance-mcp + chroma-mcp functions called directly, in-process."""
    return [
        StructuredTool.from_function(func) for func in (*_FINANCE_TOOL_FUNCS, *_CHROMA_TOOL_FUNCS)
    ]


def tool_map(tools: list[BaseTool]) -> dict[str, BaseTool]:
    """Return tools keyed by name, rejecting duplicates deterministically."""
    mapped: dict[str, BaseTool] = {}
    for tool in tools:
        if tool.name in mapped:
            raise ValueError(f"Duplicate MCP tool name: {tool.name}")
        mapped[tool.name] = tool
    return mapped


def _require_all_tools(mapped: dict[str, BaseTool]) -> None:
    missing = sorted(_REQUIRED_TOOL_NAMES - set(mapped))
    if missing:
        raise ValueError(f"missing required MCP tools: {', '.join(missing)}")


async def get_mcp_tool_bundle(client: MultiServerMCPClient | None = None) -> ToolBundle:
    """Load primary MCP tools while preserving in-process fallback tools.

    MCP-03: WHEN um servidor MCP falhar na inicialização, o sistema SHALL logar
    erro e iniciar com tools in-process equivalentes.
    """
    fallback = tool_map(in_process_tools())
    client = client if client is not None else MultiServerMCPClient(MCP_CONNECTIONS)
    try:
        primary = tool_map(await client.get_tools())
        _require_all_tools(primary)
        return ToolBundle(primary=primary, fallback=fallback, source="mcp")
    except Exception as exc:
        logger.warning(
            "MCP client failed to initialize finance-mcp/chroma-mcp (%s); "
            "falling back to in-process tools",
            exc,
            exc_info=True,
        )
        return ToolBundle(primary=fallback, fallback=fallback, source="fallback")


async def get_mcp_tools(client: MultiServerMCPClient | None = None) -> list[BaseTool]:
    """Load finance-mcp/chroma-mcp tools; fall back to in-process tools if the MCP client fails."""
    bundle = await get_mcp_tool_bundle(client=client)
    return list(bundle.primary.values())
