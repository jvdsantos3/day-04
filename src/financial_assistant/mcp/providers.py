"""Typed providers over MCP tools with in-process fallback support."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Generic, Literal, TypeVar

from langchain_core.tools import BaseTool

from financial_assistant.contracts.streaming import StreamEvent
from financial_assistant.mcp.client import ToolBundle

logger = logging.getLogger(__name__)

ToolSource = Literal["mcp", "fallback"]
T = TypeVar("T")
StreamEventEmitter = Callable[[StreamEvent], None]


class ProviderToolError(RuntimeError):
    """Typed error raised when a provider cannot satisfy a tool request."""

    def __init__(self, tool_name: str, message: str, *, recoverable: bool = False):
        super().__init__(f"{tool_name}: {message}")
        self.tool_name = tool_name
        self.recoverable = recoverable


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    """Provider result with safe status metadata for audit/SSE surfaces."""

    data: T
    tool_name: str
    source: ToolSource
    fallback_used: bool = False

    def audit_metadata(self) -> dict:
        return {
            "tool": self.tool_name,
            "source": self.source,
            "fallback_used": self.fallback_used,
            "status": "ok",
        }


class _BaseToolProvider:
    def __init__(
        self,
        bundle: ToolBundle,
        *,
        event_emitter: StreamEventEmitter | None = None,
    ):
        self._bundle = bundle
        self._event_emitter = event_emitter

    def _call(self, tool_name: str, arguments: dict) -> ToolResult:
        self._validate_user_id(tool_name, arguments.get("user_id"))

        primary = self._bundle.primary.get(tool_name)
        fallback = self._bundle.fallback.get(tool_name)
        if primary is None and fallback is None:
            raise ProviderToolError(tool_name, "tool is not available")

        source: ToolSource = self._bundle.source if primary is not None else "fallback"
        self._emit_tool_call(tool_name, source)
        try:
            data = self._invoke_tool(primary or fallback, arguments)
            result = ToolResult(
                data=data,
                tool_name=tool_name,
                source=source,
                fallback_used=False,
            )
            self._emit_tool_result(result.audit_metadata())
            return result
        except Exception as primary_exc:
            if fallback is None or fallback is primary:
                raise ProviderToolError(
                    tool_name,
                    "tool execution failed",
                    recoverable=False,
                ) from primary_exc

            logger.warning(
                "MCP primary tool failed; using fallback",
                exc_info=True,
                extra={
                    "tool": tool_name,
                    "source": source,
                    "fallback_used": True,
                },
            )
            self._emit_tool_result(
                {
                    "tool": tool_name,
                    "source": source,
                    "fallback_used": True,
                    "status": "fallback",
                }
            )
            try:
                data = self._invoke_tool(fallback, arguments)
            except Exception as fallback_exc:
                raise ProviderToolError(
                    tool_name,
                    "fallback execution failed",
                    recoverable=False,
                ) from fallback_exc

            result = ToolResult(
                data=data,
                tool_name=tool_name,
                source="fallback",
                fallback_used=True,
            )
            self._emit_tool_result(result.audit_metadata())
            return result

    @staticmethod
    def _validate_user_id(tool_name: str, user_id: object) -> None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ProviderToolError(tool_name, "user_id is required")

    @staticmethod
    def _invoke_tool(tool: BaseTool, arguments: dict):
        return tool.invoke(arguments)

    def _emit_tool_call(self, tool_name: str, source: ToolSource) -> None:
        self._emit(
            "tool_call",
            {"tool": tool_name, "source": source, "status": "started"},
        )

    def _emit_tool_result(self, metadata: dict) -> None:
        self._emit("tool_result", metadata)

    def _emit(self, event: str, data: dict) -> None:
        if self._event_emitter is not None:
            self._event_emitter(StreamEvent(event=event, data=data))


class FinanceToolProvider(_BaseToolProvider):
    """Typed runtime boundary for finance MCP tools."""

    def create_transaction(
        self,
        *,
        user_id: str,
        date: str,
        description: str,
        type: str,
        amount: str,
        category: str | None = None,
    ) -> ToolResult[dict]:
        return self._call(
            "create_transaction",
            {
                "user_id": user_id,
                "date": date,
                "description": description,
                "type": type,
                "amount": amount,
                "category": category,
            },
        )

    def list_transactions(
        self,
        *,
        user_id: str,
        month: str | None = None,
        category: str | None = None,
        type: str | None = None,
    ) -> ToolResult[list[dict]]:
        return self._call(
            "list_transactions",
            {"user_id": user_id, "month": month, "category": category, "type": type},
        )

    def get_budget_summary(self, *, user_id: str, month: str) -> ToolResult[dict]:
        return self._call(
            "get_budget_summary",
            {"user_id": user_id, "month": month},
        )

    def get_balance(self, *, user_id: str, month: str | None = None) -> ToolResult[dict]:
        return self._call("get_balance", {"user_id": user_id, "month": month})

    def update_transaction(
        self,
        *,
        user_id: str,
        transaction_id: str,
        date: str | None = None,
        description: str | None = None,
        type: str | None = None,
        amount: str | None = None,
        category: str | None = None,
    ) -> ToolResult[dict]:
        return self._call(
            "update_transaction",
            {
                "user_id": user_id,
                "transaction_id": transaction_id,
                "date": date,
                "description": description,
                "type": type,
                "amount": amount,
                "category": category,
            },
        )

    def delete_transaction(self, *, user_id: str, transaction_id: str) -> ToolResult[dict]:
        return self._call(
            "delete_transaction",
            {"user_id": user_id, "transaction_id": transaction_id},
        )


class ChromaToolProvider(_BaseToolProvider):
    """Typed runtime boundary for Chroma MCP tools and memory."""

    def search_transactions(
        self,
        *,
        user_id: str,
        query: str,
        n_results: int = 5,
    ) -> ToolResult[list[dict]]:
        return self._call(
            "search_transactions",
            {"user_id": user_id, "query": query, "n_results": n_results},
        )

    def find_similar_transactions(
        self,
        *,
        user_id: str,
        description: str,
        n_results: int = 3,
    ) -> ToolResult[list[dict]]:
        return self._call(
            "find_similar_transactions",
            {"user_id": user_id, "description": description, "n_results": n_results},
        )

    def query_knowledge(
        self,
        *,
        user_id: str,
        query: str,
        n_results: int = 6,
    ) -> ToolResult[list[dict]]:
        return self._call(
            "query_knowledge",
            {"user_id": user_id, "query": query, "n_results": n_results},
        )

    def get_chat_context(
        self,
        *,
        user_id: str,
        query: str,
        n_results: int = 5,
    ) -> ToolResult[list[dict]]:
        return self._call(
            "get_chat_context",
            {"user_id": user_id, "query": query, "n_results": n_results},
        )

    def save_working_memory(
        self,
        *,
        user_id: str,
        fact: str,
        metadata: dict | None = None,
    ) -> ToolResult[dict]:
        return self._call(
            "save_working_memory",
            {"user_id": user_id, "fact": fact, "metadata": metadata},
        )
