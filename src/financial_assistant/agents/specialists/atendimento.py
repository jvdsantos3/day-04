"""Atendimento specialist — explains budget categories and answers FAQ (T21, CONV-01).

Grounds every reply in the ``knowledge_base`` ChromaDB collection (T15) via the
``query_knowledge`` tool exposed by ``chroma-mcp`` (design.md, VEC-03), so a
"plano de gastos"-style question is answered from the seeded category docs +
overview — without requiring any pre-existing transaction (spec P1 AC1).

VEC-03 fix: the retrieved docs' ``doc_id``s are cited in
``AgentResponse.metadata["sources"]`` (collection + doc, per spec "citar a
fonte") — structured metadata rather than an LLM-authored footer, since the
AgentResponse contract already reserves ``metadata`` for exactly this kind
of side-channel data (e.g. T22's ``metadata={"transaction": ...}``).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from financial_assistant.agents.state import AgentState
from financial_assistant.config import get_settings
from financial_assistant.contracts.agent_response import AgentResponse
from financial_assistant.vector import knowledge_seed

# knowledge_base currently holds 6 docs (5 category rules + 1 overview, T15);
# retrieving all of them keeps "plano de gastos" answers grounded in both the
# per-category ranges/examples and the 5-category summary.
_KNOWLEDGE_RESULTS = 6

SYSTEM_PROMPT = (
    "Você é o agente de Atendimento do Assistente Financeiro. Responda sempre "
    "em português do Brasil, de forma clara e cordial, explicando as "
    "categorias de orçamento (Custos Fixos, Conforto, Investimentos, "
    "Conhecimento e Metas, Prazeres) e tirando dúvidas gerais (FAQ). "
    "Baseie sua resposta apenas no CONTEXTO fornecido, recuperado da base de "
    "conhecimento — não invente faixas percentuais ou exemplos. Quando o "
    "usuário pedir um plano de gastos, cite as 5 categorias com suas faixas "
    "percentuais e exemplos de gastos."
)


@tool
def query_knowledge(query: str, n_results: int = _KNOWLEDGE_RESULTS) -> list[dict[str, object]]:
    """Busca semântica na base de conhecimento de orçamento (RAG, VEC-03)."""
    return knowledge_seed.query_knowledge(query, n_results=n_results)


@lru_cache
def get_atendimento_llm() -> BaseChatModel:
    """Lazily build the DeepSeek chat model used by the Atendimento specialist."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


_KNOWLEDGE_BASE_COLLECTION = "knowledge_base"


def _build_context(docs: list[dict[str, object]]) -> str:
    return "\n".join(f"- {doc['document']}" for doc in docs)


def _cite_sources(docs: list[dict[str, object]]) -> list[dict[str, str]]:
    """Cite the collection + doc each hit came from (VEC-03, "citar a fonte")."""
    return [{"collection": _KNOWLEDGE_BASE_COLLECTION, "doc_id": doc["doc_id"]} for doc in docs]


def answer(message: str, llm: BaseChatModel | None = None) -> AgentResponse:
    """Answer one Atendimento question, grounded in ``query_knowledge`` (CONV-01)."""
    model = llm if llm is not None else get_atendimento_llm()
    docs = query_knowledge.invoke({"query": message})
    context = _build_context(docs)
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(f"CONTEXTO:\n{context}\n\nPERGUNTA: {message}"),
    ]
    response = model.invoke(messages)
    return AgentResponse(text=response.content, metadata={"sources": _cite_sources(docs)})


def atendimento_node(state: AgentState) -> dict:
    """LangGraph node: answer the latest user message via the Atendimento specialist."""
    last_message = state["messages"][-1]
    return {"final_response": answer(last_message.content)}
