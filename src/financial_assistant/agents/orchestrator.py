"""Orchestrator node — intent classification via LLM structured output (T20).

Classifies the latest user message into one of T11's ``Intent`` values
(``contracts/agent_response.py``) and maps it to the specialist that owns it,
per design.md's routing table (Onda 15 / T20):

- "plano de gastos", "como organizar" -> ``explain_budget`` -> Atendimento
- "qual categoria", "se encaixa" -> ``categorize`` -> Transações
- "economizar", "prestar atenção", "orçamento" -> ``budget_advice`` -> Orçamento
- "gastei", "recebi" -> ``register_transaction`` -> Transações

MVP routing rule (ORCH-01): one specialist per turn — this module only
classifies and maps; specialist dispatch nodes and the validator retry loop
land in T21-25. A low-confidence classification routes to Atendimento for
clarification instead of the mapped specialist (ORCH-02).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from financial_assistant.agents.state import AgentState
from financial_assistant.config import get_settings
from financial_assistant.contracts.agent_response import Intent, IntentClassification

SPECIALIST_BY_INTENT: dict[Intent, str] = {
    Intent.EXPLAIN_BUDGET: "atendimento",
    Intent.CATEGORIZE: "transacoes",
    Intent.BUDGET_ADVICE: "orcamento",
    Intent.REGISTER_TRANSACTION: "transacoes",
}

# Below this confidence, the intent is ambiguous and routes to Atendimento
# for clarification instead of its mapped specialist (spec AC "intenção
# ambígua" / ORCH-02).
AMBIGUITY_CONFIDENCE_THRESHOLD = 0.5

SYSTEM_PROMPT = (
    "Você é o orquestrador de um assistente financeiro. Sua única tarefa é "
    "classificar a mensagem do usuário em uma das intenções abaixo, seguindo "
    "estritamente estes padrões:\n"
    '- "plano de gastos", "como organizar" -> explain_budget\n'
    '- "qual categoria", "se encaixa" -> categorize\n'
    '- "economizar", "prestar atenção", "orçamento" -> budget_advice\n'
    '- "gastei", "recebi" -> register_transaction\n'
    "Responda somente com a intenção classificada e o nível de confiança "
    "(0 a 1)."
)


@lru_cache
def get_orchestrator_llm() -> BaseChatModel:
    """Lazily build the DeepSeek chat model used for intent classification."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


def classify_intent(
    message: str, llm: BaseChatModel | None = None
) -> IntentClassification:
    """Classify ``message`` into an :class:`IntentClassification` via structured output."""
    model = llm if llm is not None else get_orchestrator_llm()
    structured_model = model.with_structured_output(IntentClassification)
    return structured_model.invoke([("system", SYSTEM_PROMPT), ("human", message)])


def specialist_for_intent(intent: Intent, confidence: float = 1.0) -> str:
    """Map a classified intent to the specialist that owns it (ORCH-01).

    A confidence below :data:`AMBIGUITY_CONFIDENCE_THRESHOLD` overrides the
    mapped specialist with Atendimento, so an ambiguous intent still gets a
    clarifying reply instead of a wrong specialist (ORCH-02).
    """
    if confidence < AMBIGUITY_CONFIDENCE_THRESHOLD:
        return "atendimento"
    return SPECIALIST_BY_INTENT[intent]


def orchestrator_node(state: AgentState) -> dict:
    """LangGraph node: classify the latest user message's intent (ORCH-01)."""
    last_message = state["messages"][-1]
    classification = classify_intent(last_message.content)
    return {"intent": classification.intent.value}
