"""Chat agent contracts — shapes exchanged between the router and specialists (T11, CHAT-02).

``IntentClassification`` is the router's output: which specialist should
handle an incoming chat message, and how confident the classification is.
``AgentResponse`` is the uniform reply every specialist hands back to the chat
layer, so callers don't need a different shape per specialist.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Intents the router classifies an incoming chat message into."""

    REGISTER_TRANSACTION = "registrar_transacao"
    BUDGET_STATUS = "consultar_orcamento"
    GENERAL_QUESTION = "duvida_geral"
    UNKNOWN = "desconhecido"


class IntentClassification(BaseModel):
    """Router output: classified intent plus confidence for one message."""

    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)


class AgentResponse(BaseModel):
    """Uniform reply shape returned by a specialist agent to the chat layer."""

    reply: str = Field(min_length=1)
    intent: Intent
    data: dict | None = None
