"""Chat agent contracts — shapes exchanged between the router and specialists (T11, CHAT-02).

Shapes and intent values follow ``design.md``'s "AgentResponse (contract)"
section and the intent-routing table (Onda 15 / T20): ``explain_budget`` →
Atendimento, ``categorize`` / ``register_transaction`` → Transações,
``budget_advice`` → Orçamento. ``IntentClassification`` is the Orchestrator's
structured-output classification of one incoming message; ``AgentResponse``
is what the Validator checks before a specialist's reply reaches the user
(spec P1 "Orquestração multi-agente", AC2).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from financial_assistant.domain.models import BudgetCategory


class Intent(str, Enum):
    """Intents the Orchestrator classifies an incoming chat message into."""

    EXPLAIN_BUDGET = "explain_budget"
    CATEGORIZE = "categorize"
    BUDGET_ADVICE = "budget_advice"
    REGISTER_TRANSACTION = "register_transaction"


class IntentClassification(BaseModel):
    """Orchestrator output: classified intent plus confidence for one message."""

    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)


class AgentResponse(BaseModel):
    """Uniform reply shape a specialist returns; checked by the Validator."""

    text: str
    suggested_category: BudgetCategory | None = None
    action: Literal["none", "offer_register", "registered"] = "none"
    metadata: dict = {}
