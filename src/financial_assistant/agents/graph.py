"""LangGraph StateGraph — full agent graph (T25, ORCH-01).

Wires every node built in T19-T24 into design.md's "LangGraph Agent Graph"
flow (``orchestrator -> {atendimento, transacoes, orcamento} -> validator ->
[approved: END | rejected: retry <=2, back to orchestrator]``).

Routing:
- ``orchestrator`` -> specialist: picked by ``orchestrator.specialist_for_intent``
  from ``state["intent"]``/``state["intent_confidence"]`` (both set by
  ``orchestrator_node``, T20/fix). Below ``AMBIGUITY_CONFIDENCE_THRESHOLD``,
  the edge routes to Atendimento regardless of the classified intent
  (ORCH-02) — found unreachable at the system level by the feature
  Verifier despite ``specialist_for_intent`` itself being correctly unit
  tested; fixed by threading confidence through ``AgentState``.
- ``validator`` -> ``orchestrator`` | ``END``: ``validator_node`` (T24)
  already signals a rejection that hasn't exhausted
  ``MAX_VALIDATION_ATTEMPTS`` by returning ``final_response=None`` — that's
  the retry signal this edge reads. Once attempts are exhausted,
  ``validator_node`` fills ``final_response`` with a fallback, so the edge
  naturally terminates instead of looping.

``run()`` is the design.md-specified entry point (``run(user_id, session_id,
message) -> AgentResponse``): invokes the compiled graph for one turn, then
persists both sides of the exchange to ``chat_messages`` (SQLite) so any
agent can later reconstruct recent history (spec.md "Camada 2 — SQLite —
histórico durável").

MCP-01/MCP-03 fix: ``build_graph()`` now actually attempts the
finance-mcp/chroma-mcp connection via ``mcp.client.get_mcp_tools()``
(cached — the connect-or-fallback attempt only runs once per process, via
``_load_mcp_tools``). Found by the feature Verifier: this call existed and
was unit-tested in isolation, but nothing in the running app ever invoked
it, so MCP-01 ("o grafo conecta aos servidores MCP e carrega tools
dinamicamente") and MCP-03's fallback were both dead code in production.
SPEC_DEVIATION (still real, narrower scope than the AC's letter): the
loaded tools are not yet consumed by the specialists — Transações/Orçamento
call ``mcp_servers.*.server`` functions directly and deterministically by
design (T21-23, chosen over LLM tool-calling for testability), so this
fix makes the connect/fallback lifecycle genuinely happen at startup
without rearchitecting the specialists into an agentic tool-calling model
(a much larger, separate change).
"""

from __future__ import annotations

import asyncio
import uuid
from functools import lru_cache

from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from financial_assistant.agents.orchestrator import (
    Intent,
    orchestrator_node,
    specialist_for_intent,
)
from financial_assistant.agents.specialists.atendimento import atendimento_node
from financial_assistant.agents.specialists.orcamento import orcamento_node
from financial_assistant.agents.specialists.transacoes import transacoes_node
from financial_assistant.agents.state import AgentState
from financial_assistant.agents.validator import validator_node
from financial_assistant.contracts.agent_response import AgentResponse
from financial_assistant.db.session import SessionLocal
from financial_assistant.domain.models import ChatMessage
from financial_assistant.mcp.client import get_mcp_tools

_SPECIALIST_NODES = ("atendimento", "transacoes", "orcamento")


@lru_cache
def _load_mcp_tools() -> tuple[BaseTool, ...]:
    """Connect to finance-mcp/chroma-mcp once per process (MCP-01), falling back
    to in-process tools on failure (MCP-03, logged by ``get_mcp_tools`` itself)."""
    return tuple(asyncio.run(get_mcp_tools()))


def _route_to_specialist(state: AgentState) -> str:
    """Pick the specialist node for this turn's classified intent (ORCH-01/02)."""
    confidence = state.get("intent_confidence")
    return specialist_for_intent(Intent(state["intent"]), confidence if confidence is not None else 1.0)


def _route_after_validation(state: AgentState) -> str:
    """Retry the Orchestrator on rejection, otherwise end the turn (design.md 'Validator reject | Retry specialist <=2')."""
    return "orchestrator" if state["final_response"] is None else END


def build_graph() -> CompiledStateGraph:
    """Compile the full graph: orchestrator -> specialist -> validator -> END|retry."""
    _load_mcp_tools()  # MCP-01: connect (or fall back) at graph startup, not lazily on first use.
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("atendimento", atendimento_node)
    graph.add_node("transacoes", transacoes_node)
    graph.add_node("orcamento", orcamento_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges(
        "orchestrator", _route_to_specialist, {name: name for name in _SPECIALIST_NODES}
    )
    for name in _SPECIALIST_NODES:
        graph.add_edge(name, "validator")
    graph.add_conditional_edges(
        "validator", _route_after_validation, {"orchestrator": "orchestrator", END: END}
    )
    return graph.compile()


def _persist_turn(user_id: str, session_id: str, message: str, response: AgentResponse) -> None:
    """Append the user's message and the final reply to ``chat_messages`` (spec.md Camada 2)."""
    with SessionLocal() as session:
        session.add_all(
            [
                ChatMessage(
                    user_id=uuid.UUID(user_id), session_id=session_id, role="user", content=message
                ),
                ChatMessage(
                    user_id=uuid.UUID(user_id),
                    session_id=session_id,
                    role="assistant",
                    content=response.text,
                ),
            ]
        )
        session.commit()


def run(
    user_id: str, session_id: str, message: str, *, graph: CompiledStateGraph | None = None
) -> AgentResponse:
    """Run one full turn through the agent graph and persist it (design.md 'run')."""
    compiled = graph if graph is not None else build_graph()
    initial_state: AgentState = {
        "messages": [HumanMessage(message)],
        "user_id": user_id,
        "session_id": session_id,
        "intent": None,
        "intent_confidence": None,
        "retrieved_context": [],
        "pending_action": None,
        "agent_notes": [],
        "last_tool_results": None,
        "validation_attempts": 0,
        "final_response": None,
    }
    result = compiled.invoke(initial_state)
    response = result["final_response"]
    _persist_turn(user_id, session_id, message, response)
    return response
