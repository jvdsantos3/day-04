"""AgentState — shared LangGraph state (T19).

Literal port of design.md's "AgentState (LangGraph)" section — the state
every node (orchestrator, specialists, validator) reads from and writes to
as it flows through the graph (ORCH-01).
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from financial_assistant.contracts.agent_response import AgentResponse


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str | None
    retrieved_context: list[str]
    pending_action: dict | None
    agent_notes: list[str]
    last_tool_results: dict | None
    validation_attempts: int
    final_response: AgentResponse | None
