"""Especialista Transações — CRUD financeiro e categorização (T22).

Cobre dois intents roteados pelo Orquestrador (T20) para este especialista:

- ``register_transaction`` (CHAT-01/02/03): extrai tipo/valor/descrição da
  mensagem e persiste via ``finance-mcp.create_transaction``. Despesas exigem
  categoria inferida via ``categorize``; receitas são sempre persistidas com
  ``category=None`` (CHAT-02). Quando valor ou categoria não puderem ser
  inferidos, retorna uma pergunta de clarificação e **não persiste**
  (CHAT-03).
- ``categorize`` (CONV-02): infere a categoria e explica o raciocínio, mas
  **não registra automaticamente** — retorna ``action="offer_register"`` para
  o usuário confirmar.

Categorização (ambos os fluxos) usa ``chroma-mcp.find_similar_transactions``
(T17), que já combina o histórico do usuário (``transactions``) com os
exemplos rotulados globais (``category_examples``, T15 — inclui
``"pedido de delivery" -> prazeres``), ordenados por score.

Spec-precision gap: a extração de tipo/valor/descrição da mensagem em
linguagem natural não é definida no design — implementada via regex
determinístico (marcadores "gastei/paguei/comprei" -> despesa,
"recebi/ganhei" -> receita; valor via padrão ``R$ N`` ou ``N reais``) em vez
de LLM, mantendo os testes unitários rápidos e sem mock de chat model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from financial_assistant.agents.state import AgentState
from financial_assistant.contracts.agent_response import AgentResponse, Intent
from financial_assistant.domain.models import BudgetCategory, TransactionType
from mcp_servers.chroma.server import find_similar_transactions as _find_similar_transactions
from mcp_servers.finance.server import create_transaction as _create_transaction

CLARIFICATION_TEXT = (
    "Não consegui identificar o valor ou a categoria dessa transação. Pode "
    "confirmar quanto foi e do que se trata?"
)

_CATEGORY_RATIONALE: dict[BudgetCategory, str] = {
    BudgetCategory.FIXED: "é uma despesa essencial e recorrente",
    BudgetCategory.COMFORT: "eleva a qualidade de vida sem ser essencial",
    BudgetCategory.INVESTMENTS: "é um aporte para o futuro",
    BudgetCategory.KNOWLEDGE: "é um investimento em desenvolvimento pessoal ou uma meta",
    BudgetCategory.PLEASURES: "é um gasto com lazer, alimentação fora de casa ou entretenimento",
}

_EXPENSE_MARKERS = ("gastei", "paguei", "comprei")
_INCOME_MARKERS = ("recebi", "ganhei")

_AMOUNT_PATTERN = re.compile(
    r"r\$\s*(?P<amt1>\d+(?:[.,]\d{1,2})?)|(?P<amt2>\d+(?:[.,]\d{1,2})?)\s*reais",
    re.IGNORECASE,
)
_VERB_PREFIX = re.compile(r"^(gastei|paguei|comprei|recebi|ganhei)\b\s*", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedTransaction:
    """Best-effort extraction of a transaction's fields from a chat message."""

    type: TransactionType
    amount: Decimal
    description: str


def _infer_type(message: str) -> TransactionType | None:
    lowered = message.lower()
    if any(marker in lowered for marker in _INCOME_MARKERS):
        return TransactionType.INCOME
    if any(marker in lowered for marker in _EXPENSE_MARKERS):
        return TransactionType.EXPENSE
    return None


def _extract_amount(message: str) -> tuple[Decimal, tuple[int, int]] | None:
    match = _AMOUNT_PATTERN.search(message)
    if match is None:
        return None
    raw = match.group("amt1") or match.group("amt2")
    return Decimal(raw.replace(",", ".")), match.span()


def _clean_description(message: str, span: tuple[int, int]) -> str:
    start, end = span
    remainder = re.sub(r"\s+", " ", message[:start] + message[end:]).strip()
    remainder = _VERB_PREFIX.sub("", remainder).strip(" ,.")
    return remainder or message.strip()


def parse_transaction_message(message: str) -> ParsedTransaction | None:
    """Extract type/amount/description from ``message``.

    Returns ``None`` when the type or the amount can't be inferred — callers
    must ask for clarification instead of persisting (CHAT-03).
    """
    type_ = _infer_type(message)
    extracted = _extract_amount(message)
    if type_ is None or extracted is None:
        return None
    amount, span = extracted
    if amount <= 0:
        return None
    return ParsedTransaction(type=type_, amount=amount, description=_clean_description(message, span))


def categorize(
    description: str,
    user_id: str,
    find_similar: Callable[..., list[dict]] | None = None,
) -> BudgetCategory | None:
    """Infer the BudgetCategory for ``description`` via chroma-mcp's find_similar_transactions.

    Picks the top-scored hit that carries a ``category`` (results already come
    sorted by score, T17). Returns ``None`` when nothing matches — callers
    must ask for clarification instead of persisting an uncategorized expense
    (CHAT-03).
    """
    finder = find_similar if find_similar is not None else _find_similar_transactions
    hits = finder(user_id=user_id, description=description)
    for hit in hits:
        category_value = hit.get("metadata", {}).get("category")
        if category_value:
            return BudgetCategory(category_value)
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
    message: str, user_id: str, *, find_similar: Callable[..., list[dict]] | None = None
) -> AgentResponse:
    category = categorize(message, user_id, find_similar=find_similar)
    if category is None:
        return AgentResponse(text=CLARIFICATION_TEXT, action="none")
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
) -> AgentResponse:
    parsed = parse_transaction_message(message)
    if parsed is None:
        return AgentResponse(text=CLARIFICATION_TEXT, action="none")

    category: BudgetCategory | None = None
    if parsed.type == TransactionType.EXPENSE:
        category = categorize(parsed.description, user_id, find_similar=find_similar)
        if category is None:
            return AgentResponse(text=CLARIFICATION_TEXT, action="none")

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
) -> dict:
    """LangGraph node: dispatch to categorize-only or register-and-persist (ORCH-01)."""
    message = state["messages"][-1].content
    user_id = state["user_id"]
    if state.get("intent") == Intent.CATEGORIZE.value:
        response = _handle_categorize(message, user_id, find_similar=find_similar)
    else:
        response = _handle_register(message, user_id, find_similar=find_similar, create=create)
    return {"final_response": response}
