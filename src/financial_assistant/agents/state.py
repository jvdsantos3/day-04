"""AgentState — shared LangGraph state (T19).

Literal port of design.md's "AgentState (LangGraph)" section — the state
every node (orchestrator, specialists, validator) reads from and writes to
as it flows through the graph (ORCH-01).

SPEC_DEVIATION: ``intent_confidence`` isn't in design.md's field table.
Added to close ORCH-02 (ambiguous intent -> Atendimento): the classifier's
confidence has to reach the graph's routing edge somehow, and design.md's
own table doesn't have a field for it. Reason: without this, ORCH-02's
``specialist_for_intent(intent, confidence)`` override is a correct, tested
pure function that the graph can never actually call with a real
confidence value.
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
    intent_confidence: float | None
    retrieved_context: list[str]
    pending_action: dict | None
    agent_notes: list[str]
    last_tool_results: dict | None
    validation_attempts: int
    final_response: AgentResponse | None
