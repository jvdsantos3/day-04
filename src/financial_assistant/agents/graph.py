"""LangGraph StateGraph skeleton (T19).

Wires the ``orchestrator`` and ``validator`` nodes per design.md's "LangGraph
Agent Graph" flow (``[*] --> orchestrator --> ... --> validator --> [*]``),
satisfying ORCH-01's "o sistema SHALL conectar aos servidores ... e carregar
tools dinamicamente" prerequisite of a compilable graph. Both nodes are
stubs: intent classification (T20), the specialist branches (T21-23) and the
validator's reject-and-retry edge back to orchestrator (T25 "Wire full
graph") are not implemented yet — this task only establishes the skeleton
compiles.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from financial_assistant.agents.state import AgentState


def orchestrator_node(state: AgentState) -> dict:
    """Stub — intent classification lands in T20."""
    return {}


def validator_node(state: AgentState) -> dict:
    """Stub — quality gate checks land in T24."""
    return {}


def build_graph() -> CompiledStateGraph:
    """Compile the skeleton graph: ``START -> orchestrator -> validator -> END``."""
    graph = StateGraph(AgentState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("validator", validator_node)
    graph.add_edge(START, "orchestrator")
    graph.add_edge("orchestrator", "validator")
    graph.add_edge("validator", END)
    return graph.compile()
