"""Validator — post-specialist quality gate (T24).

Runs after every specialist (design.md "Validator") and before a reply
reaches the user: confirms the ``AgentResponse`` contract (VAL-01), cross
checks any R$/percent figures the text cites against the authoritative
sources (`finance-mcp.get_balance` / `finance-mcp.get_budget_summary`,
MCP-04, VAL-03, CONV-05), confirms a suggested category is a valid
``BudgetCategory`` member, and confirms the text is non-empty and in PT-BR
(VAL-02). A rejection increments ``state["validation_attempts"]``; while the
limit (``MAX_VALIDATION_ATTEMPTS`` = 2, design.md "Validator reject | Retry
specialist ≤2") isn't reached, the node returns ``final_response=None`` —
the signal T25 ("wire full graph") uses for the conditional edge back to the
Orchestrator. Once attempts are exhausted, it returns a fallback response
instead of leaving the user without one.

Spec-precision gap (VAL-03 scope): a just-registered transaction's own
amount (``AgentResponse.metadata["transaction"]["amount"]``, set by the
Transações specialist, T22) is added to the known-amounts set before
checking — it's not an aggregate from get_balance/get_budget_summary, but
it *is* the value the specialist just persisted, so citing it back isn't an
inconsistency to block.

Bug found via live testing against the real DeepSeek API (not caught by any
mocked unit test): the Atendimento specialist's ``explain_budget`` answer
(CONV-01) is explicitly spec'd to work "sem exigir transações
pré-existentes" — it cites the knowledge base's percentage *ranges* and
walks through an illustrative example (e.g. "se sua renda for R$ 5.000,
Custos Fixos em 35% seria R$ 1.750"). Those figures are pedagogical, not a
claim about this user's actual balance, so checking them against
``get_balance``/``get_budget_summary`` rejected every real answer to
"quero montar um plano de gastos". The currency/percent check therefore
is skipped for that one intent (``explain_budget``) — see
``_SKIPS_FINANCIAL_FIGURE_CHECK_FOR``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

from pydantic import ValidationError

from financial_assistant.agents.state import AgentState
from financial_assistant.contracts.agent_response import AgentResponse, Intent
from financial_assistant.domain.models import BudgetCategory
from mcp_servers.finance.server import get_balance as _get_balance
from mcp_servers.finance.server import get_budget_summary as _get_budget_summary

MAX_VALIDATION_ATTEMPTS = 2

# The R$/percent consistency check (VAL-03, CONV-05) is skipped only for this
# intent: Atendimento's ``explain_budget`` answer cites illustrative
# ranges/examples from the knowledge base, not claims about this user's real
# data (spec CONV-01, "sem exigir transações pré-existentes"). Every other
# intent — including an unknown/unset one — still gets checked; this is a
# deny-list, not an allow-list, so the safety check fails closed by default.
_SKIPS_FINANCIAL_FIGURE_CHECK_FOR = {Intent.EXPLAIN_BUDGET.value}

FALLBACK_TEXT = (
    "Não consegui confirmar essa resposta com segurança. Pode reformular a "
    "pergunta ou tentar novamente em instantes?"
)

_CURRENCY_RE = re.compile(r"R\$\s*(\d+(?:[.,]\d+)*)")
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_WORD_RE = re.compile(r"[a-zà-ÿ]+")
_PT_BR_MARKERS = {
    "que", "para", "não", "de", "com", "uma", "um", "você", "está",
    "sua", "seu", "é", "os", "as", "do", "da", "em", "na", "no", "essa",
    "esse", "isso",
}

_AMOUNT_TOLERANCE = Decimal("0.01")
_PERCENT_TOLERANCE = 0.05


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of one ``validate()`` call: approved, or rejected with a reason."""

    approved: bool
    reason: str | None = None


def _parse_amount(raw: str) -> Decimal:
    try:
        return Decimal(str(raw).replace(",", ""))
    except InvalidOperation:
        return Decimal("NaN")


def _extract_currency_values(text: str) -> list[Decimal]:
    return [_parse_amount(match) for match in _CURRENCY_RE.findall(text)]


def _extract_percent_values(text: str) -> list[float]:
    return [float(match.replace(",", ".")) for match in _PERCENT_RE.findall(text)]


def _looks_like_pt_br(text: str) -> bool:
    words = _WORD_RE.findall(text.lower())
    return any(word in _PT_BR_MARKERS for word in words)


def _coerce_response(response: object) -> AgentResponse | None:
    """Check 1 (VAL-01): confirm/rebuild the ``AgentResponse`` contract."""
    if isinstance(response, AgentResponse):
        return response
    if isinstance(response, dict):
        try:
            return AgentResponse.model_validate(response)
        except ValidationError:
            return None
    return None


def _known_amounts(balance: dict, summary: dict, response: AgentResponse) -> set[Decimal]:
    values = {
        _parse_amount(balance["total_income"]),
        _parse_amount(balance["total_expense"]),
        _parse_amount(balance["balance"]),
        _parse_amount(summary["total_income"]),
    }
    for category in summary["categories"]:
        values.add(_parse_amount(category["spent"]))
        values.add(_parse_amount(category["over_amount"]))
    transaction = response.metadata.get("transaction") if isinstance(response.metadata, dict) else None
    if isinstance(transaction, dict) and "amount" in transaction:
        values.add(_parse_amount(transaction["amount"]))
    return values


def _is_registered_transaction_confirmation(response: AgentResponse) -> bool:
    transaction = response.metadata.get("transaction") if isinstance(response.metadata, dict) else None
    return response.action == "registered" and isinstance(transaction, dict) and "amount" in transaction


def _known_percents(summary: dict) -> set[float]:
    values: set[float] = set()
    for category in summary["categories"]:
        values.update(
            round(category[field], 1)
            for field in ("pct", "min_pct", "max_pct", "target_pct", "remaining_pct")
        )
    return values


def _matches(value: Decimal, known: set[Decimal]) -> bool:
    return any(abs(value - candidate) <= _AMOUNT_TOLERANCE for candidate in known)


def _matches_percent(value: float, known: set[float]) -> bool:
    return any(abs(value - candidate) <= _PERCENT_TOLERANCE for candidate in known)


def validate(
    response: object,
    *,
    user_id: str,
    intent: str | None = None,
    month: str | None = None,
    get_balance: Callable[..., dict] | None = None,
    get_budget_summary: Callable[..., dict] | None = None,
) -> ValidationResult:
    """Run the Validator's four checks (design.md) against one specialist response."""
    checked = _coerce_response(response)
    if checked is None:
        return ValidationResult(False, "AgentResponse inválido ou ausente")
    if not checked.text.strip():
        return ValidationResult(False, "resposta vazia")
    if not _looks_like_pt_br(checked.text):
        return ValidationResult(False, "resposta não parece estar em PT-BR")
    if checked.suggested_category is not None:
        try:
            BudgetCategory(checked.suggested_category)
        except ValueError:
            return ValidationResult(False, f"categoria inválida: {checked.suggested_category!r}")

    if _is_registered_transaction_confirmation(checked):
        return ValidationResult(True, None)

    if intent in _SKIPS_FINANCIAL_FIGURE_CHECK_FOR:
        return ValidationResult(True, None)

    amounts = _extract_currency_values(checked.text)
    percents = _extract_percent_values(checked.text)
    if amounts or percents:
        fetch_balance = get_balance if get_balance is not None else _get_balance
        fetch_summary = get_budget_summary if get_budget_summary is not None else _get_budget_summary
        target_month = month or date.today().strftime("%Y-%m")
        balance = fetch_balance(user_id=user_id, month=target_month)
        summary = fetch_summary(user_id=user_id, month=target_month)

        known_amounts = _known_amounts(balance, summary, checked)
        for amount in amounts:
            if not _matches(amount, known_amounts):
                return ValidationResult(False, f"valor R$ {amount} não confere com o banco (VAL-03)")

        known_percents = _known_percents(summary)
        for percent in percents:
            if not _matches_percent(percent, known_percents):
                return ValidationResult(
                    False, f"percentual {percent}% não confere com o orçamento (CONV-05)"
                )

    return ValidationResult(True, None)


def validator_node(
    state: AgentState,
    *,
    get_balance: Callable[..., dict] | None = None,
    get_budget_summary: Callable[..., dict] | None = None,
) -> dict:
    """LangGraph node: gate ``state["final_response"]`` (VAL-01/02/03, CONV-05)."""
    attempts = state["validation_attempts"] + 1
    result = validate(
        state["final_response"],
        user_id=state["user_id"],
        intent=state.get("intent"),
        get_balance=get_balance,
        get_budget_summary=get_budget_summary,
    )
    if result.approved:
        return {"validation_attempts": attempts}

    note = f"validator: rejeitado (tentativa {attempts}/{MAX_VALIDATION_ATTEMPTS}) — {result.reason}"
    agent_notes = [*state["agent_notes"], note]
    if attempts >= MAX_VALIDATION_ATTEMPTS:
        return {
            "validation_attempts": attempts,
            "final_response": AgentResponse(text=FALLBACK_TEXT),
            "agent_notes": agent_notes,
        }
    return {
        "validation_attempts": attempts,
        "final_response": None,
        "agent_notes": agent_notes,
    }
