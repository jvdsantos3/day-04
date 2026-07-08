"""Especialista Transações — CRUD financeiro e categorização (T22).

Cobre dois intents roteados pelo Orquestrador (T20) para este especialista:

- ``register_transaction`` (CHAT-01/02/03): extrai tipo/valor/descrição da
  mensagem via LLM (saída estruturada) e persiste via
  ``finance-mcp.create_transaction``. Despesas exigem categoria inferida via
  ``categorize``; receitas são sempre persistidas com ``category=None``
  (CHAT-02). Quando valor ou categoria não puderem ser inferidos, retorna uma
  pergunta de clarificação e **não persiste** (CHAT-03).
- ``categorize`` (CONV-02): infere a categoria e explica o raciocínio, mas
  **não registra automaticamente** — retorna ``action="offer_register"`` para
  o usuário confirmar.

Extração e categorização usam LLM com saída estruturada. A categorização
tenta primeiro ``chroma-mcp.find_similar_transactions`` (histórico + exemplos
rotulados); se não houver match, recorre ao LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from financial_assistant.agents.orchestrator import get_orchestrator_llm
from financial_assistant.agents.state import AgentState
from financial_assistant.config import get_settings
from financial_assistant.contracts.agent_response import AgentResponse, Intent
from financial_assistant.contracts.transaction import CategoryExtraction, TransactionExtraction
from financial_assistant.domain.models import BudgetCategory, TransactionType
from mcp_servers.chroma.server import find_similar_transactions as _find_similar_transactions
from mcp_servers.finance.server import create_transaction as _create_transaction

CLARIFICATION_AMOUNT = (
    "Não consegui identificar o valor dessa transação. Pode informar quanto foi?"
)
CLARIFICATION_CATEGORY = (
    "Entendi o valor, mas não consegui categorizar essa despesa. "
    "Pode descrever melhor do que se trata?"
)

_CATEGORY_RATIONALE: dict[BudgetCategory, str] = {
    BudgetCategory.FIXED: "é uma despesa essencial e recorrente",
    BudgetCategory.COMFORT: "eleva a qualidade de vida sem ser essencial",
    BudgetCategory.INVESTMENTS: "é um aporte para o futuro",
    BudgetCategory.KNOWLEDGE: "é um investimento em desenvolvimento pessoal ou uma meta",
    BudgetCategory.PLEASURES: "é um gasto com lazer, alimentação fora de casa ou entretenimento",
}

_EXTRACTION_SYSTEM_PROMPT = (
    "Você extrai dados de transações financeiras a partir de mensagens em "
    "português natural. Identifique:\n"
    '- type: "receita" para entradas (salário, vendas, depósitos) ou '
    '"despesa" para saídas (compras, pagamentos, gastos)\n'
    "- amount: valor numérico em reais, sem símbolo R$\n"
    "- description: descrição curta e útil do que é a transação "
    "(ex.: salário, almoço, mercado — não repita só 'receita' ou 'despesa' "
    "se houver detalhe melhor na mensagem)\n"
    "Exemplos:\n"
    '- "Adicione uma receita de 3000 esse mês" -> receita, 3000, "receita"\n'
    '- "gastei 50 no mercado" -> despesa, 50, "mercado"\n'
    '- "recebi 5000 de salário" -> receita, 5000, "salário"\n'
    '- "lança 120 de delivery" -> despesa, 120, "delivery"\n'
    "Se não houver valor numérico claro, deixe amount como null. "
    "Se o tipo for ambíguo, deixe type como null. "
    "Se não houver descrição útil, deixe description como null."
)

_CATEGORIZATION_SYSTEM_PROMPT = (
    "Você categoriza despesas pessoais em uma das cinco categorias do método "
    "das caixinhas:\n"
    "- custos_fixos: despesas essenciais e recorrentes (aluguel, contas, "
    "transporte fixo, mercado básico)\n"
    "- conforto: qualidade de vida não essencial (roupas, eletrônicos, "
    "assinaturas de streaming)\n"
    "- investimentos: aportes para o futuro (poupança, ações, previdência)\n"
    "- conhecimento_metas: desenvolvimento pessoal e metas (cursos, livros, "
    "certificações)\n"
    "- prazeres: lazer, alimentação fora, delivery, cinema, entretenimento\n"
    "Retorne null se não for possível inferir com confiança."
)


@dataclass(frozen=True)
class ParsedTransaction:
    """Fields extracted from a natural-language transaction message."""

    type: TransactionType
    amount: Decimal
    description: str


def extract_transaction(
    message: str, llm: BaseChatModel
) -> ParsedTransaction | None:
    """Extract type, amount and description from ``message`` via structured LLM output."""
    structured_model = llm.with_structured_output(
        TransactionExtraction, method="function_calling"
    )
    extracted = structured_model.invoke(
        [("system", _EXTRACTION_SYSTEM_PROMPT), ("human", message)]
    )
    if (
        extracted.type is None
        or extracted.amount is None
        or extracted.amount <= 0
        or not (extracted.description or "").strip()
    ):
        return None
    return ParsedTransaction(
        type=extracted.type,
        amount=extracted.amount,
        description=extracted.description.strip(),
    )


def _categorize_with_llm(description: str, llm: BaseChatModel) -> BudgetCategory | None:
    structured_model = llm.with_structured_output(
        CategoryExtraction, method="function_calling"
    )
    result = structured_model.invoke(
        [("system", _CATEGORIZATION_SYSTEM_PROMPT), ("human", description)]
    )
    return result.category


def _extraction_llm() -> BaseChatModel | None:
    if not get_settings().deepseek_api_key:
        return None
    return get_orchestrator_llm()


def categorize(
    description: str,
    user_id: str,
    find_similar: Callable[..., list[dict]] | None = None,
    llm: BaseChatModel | None = None,
) -> BudgetCategory | None:
    """Infer the BudgetCategory for ``description`` via Chroma, then LLM fallback."""
    finder = find_similar if find_similar is not None else _find_similar_transactions
    hits = finder(user_id=user_id, description=description)
    for hit in hits:
        category_value = hit.get("metadata", {}).get("category")
        if category_value:
            return BudgetCategory(category_value)
    if llm is not None:
        return _categorize_with_llm(description, llm)
    return None


def _confirmation_text(created: dict) -> str:
    type_label = "despesa" if created["type"] == TransactionType.EXPENSE.value else "receita"
    category_part = f" na categoria {created['category']}" if created.get("category") else ""
    return f'Registrei uma {type_label} de R$ {created["amount"]}{category_part}: "{created["description"]}".'


def _categorization_explanation(category: BudgetCategory) -> str:
    rationale = _CATEGORY_RATIONALE[category]
    return (
        f"Essa despesa se encaixa na categoria **{category.value}** porque {rationale}. "
        "Quer que eu registre essa despesa?"
    )


def _handle_categorize(
    message: str,
    user_id: str,
    *,
    find_similar: Callable[..., list[dict]] | None = None,
    llm: BaseChatModel | None = None,
) -> AgentResponse:
    model = llm if llm is not None else _extraction_llm()
    if model is None:
        return AgentResponse(text=CLARIFICATION_CATEGORY, action="none")
    category = categorize(message, user_id, find_similar=find_similar, llm=model)
    if category is None:
        return AgentResponse(text=CLARIFICATION_CATEGORY, action="none")
    return AgentResponse(
        text=_categorization_explanation(category),
        suggested_category=category,
        action="offer_register",
    )


def _handle_register(
    message: str,
    user_id: str,
    *,
    find_similar: Callable[..., list[dict]] | None = None,
    create: Callable[..., dict] | None = None,
    llm: BaseChatModel | None = None,
) -> AgentResponse:
    model = llm if llm is not None else _extraction_llm()
    if model is None:
        return AgentResponse(text=CLARIFICATION_AMOUNT, action="none")

    parsed = extract_transaction(message, model)
    if parsed is None:
        return AgentResponse(text=CLARIFICATION_AMOUNT, action="none")

    category: BudgetCategory | None = None
    if parsed.type == TransactionType.EXPENSE:
        category = categorize(
            parsed.description, user_id, find_similar=find_similar, llm=model
        )
        if category is None:
            return AgentResponse(text=CLARIFICATION_CATEGORY, action="none")

    creator = create if create is not None else _create_transaction
    created = creator(
        user_id=user_id,
        date=date.today().isoformat(),
        description=parsed.description,
        type=parsed.type.value,
        amount=str(parsed.amount),
        category=category.value if category else None,
    )
    return AgentResponse(
        text=_confirmation_text(created),
        suggested_category=category,
        action="registered",
        metadata={"transaction": created},
    )


def transacoes_node(
    state: AgentState,
    *,
    find_similar: Callable[..., list[dict]] | None = None,
    create: Callable[..., dict] | None = None,
    llm: BaseChatModel | None = None,
) -> dict:
    """LangGraph node: dispatch to categorize-only or register-and-persist (ORCH-01)."""
    message = state["messages"][-1].content
    user_id = state["user_id"]
    if state.get("intent") == Intent.CATEGORIZE.value:
        response = _handle_categorize(
            message, user_id, find_similar=find_similar, llm=llm
        )
    else:
        response = _handle_register(
            message,
            user_id,
            find_similar=find_similar,
            create=create,
            llm=llm,
        )
    return {"final_response": response}
