"""LangGraph StateGraph — full agent graph (T25, ORCH-01).

Wires every node built in T19-T24 into design.md's "LangGraph Agent Graph"
flow (``orchestrator -> {atendimento, transacoes, orcamento} -> validator ->
[approved: END | rejected: retry <=2, back to orchestrator]``).

Routing:
- ``orchestrator`` -> specialist: picked by ``orchestrator.specialist_for_intent``
  from ``state["intent"]`` (set by ``orchestrator_node``, T20). Scoped to
  ORCH-01 only — the confidence-based ambiguity override (ORCH-02) isn't
  wired at this edge because ``orchestrator_node``'s contract (its returned
  dict, asserted by ``test_orchestrator_node_sets_intent_on_state``) doesn't
  carry the classification's confidence into ``AgentState``; closing that
  gap is a separate task.
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
"""

from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage
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

_SPECIALIST_NODES = ("atendimento", "transacoes", "orcamento")


def _route_to_specialist(state: AgentState) -> str:
    """Pick the specialist node for this turn's classified intent (ORCH-01)."""
    return specialist_for_intent(Intent(state["intent"]))


def _route_after_validation(state: AgentState) -> str:
    """Retry the Orchestrator on rejection, otherwise end the turn (design.md 'Validator reject | Retry specialist <=2')."""
    return "orchestrator" if state["final_response"] is None else END


def build_graph() -> CompiledStateGraph:
    """Compile the full graph: orchestrator -> specialist -> validator -> END|retry."""
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
