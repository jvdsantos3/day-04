"""Especialista Orçamento — alertas e recomendações priorizadas (T23).

Responde ao terceiro cenário conversacional real do spec.md ("Em quais
categorias devo prestar mais atenção ou economizar?"): invoca
``finance-mcp.get_budget_summary`` (T16, que já embrulha o ``BudgetService``
do T10) e aplica BUD-03/CONV-03/CONV-04:

- BUD-03: resume as 5 categorias (gasto, %, faixa, status ok/alerta) — a
  fonte é o dict já serializado por ``finance-mcp``, sem reimplementar a
  lógica de orçamento aqui.
- CONV-03: categorias acima da faixa máxima (``status == "alerta"``) ou com
  margem restante apertada entram na lista de recomendações priorizadas,
  ordenadas da mais crítica (margem mais negativa/menor) para a menos
  crítica.
- CONV-04: sem receita registrada no mês (``has_income=False``), orienta o
  usuário a registrar receita antes de calcular percentuais, em vez de
  seguir com a análise de categorias.

Segue o padrão de DI do especialista Transações (T22): importa a tool do
finance-mcp diretamente (o MCP client/subprocess só é ligado ao grafo no
T25) e aceita um ``get_summary`` injetável para testes sem banco.

Spec-precision gap (CONV-03): a spec não define um limiar numérico para
"menor margem restante" quando a categoria ainda não excedeu a faixa.
Escolhido: dentro de ``TIGHT_MARGIN_PCT`` pontos percentuais do teto também
entra na lista de atenção.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from financial_assistant.agents.state import AgentState
from financial_assistant.contracts.agent_response import AgentResponse
from mcp_servers.finance.server import get_budget_summary as _get_budget_summary

NO_INCOME_ADVICE = (
    "Ainda não tenho nenhuma receita registrada sua este mês, então não dá "
    'para calcular percentuais de orçamento com segurança. Me conta sua '
    'receita do mês (ex.: "recebi 5000 de salário") que eu já calculo as '
    "faixas por categoria."
)

NO_ATTENTION_TEXT = (
    "Você está dentro da faixa em todas as categorias este mês. Continue assim!"
)

TIGHT_MARGIN_PCT = 5.0


def _needs_attention(category: dict) -> bool:
    return category["status"] == "alerta" or category["remaining_pct"] <= TIGHT_MARGIN_PCT


def _prioritized_categories(categories: list[dict]) -> list[dict]:
    """Categorias acima da faixa ou com margem apertada, da mais crítica p/ menos (CONV-03)."""
    flagged = [c for c in categories if _needs_attention(c)]
    return sorted(flagged, key=lambda c: c["remaining_pct"])


def _format_line(category: dict) -> str:
    if category["status"] == "alerta":
        return (
            f'- {category["category"]}: {category["pct"]:.1f}% (faixa até '
            f'{category["max_pct"]:.0f}%) — R$ {category["over_amount"]} acima do limite'
        )
    return (
        f'- {category["category"]}: {category["pct"]:.1f}% (faixa até '
        f'{category["max_pct"]:.0f}%) — margem de {category["remaining_pct"]:.1f} pontos'
    )


def _format_advice(categories: list[dict]) -> str:
    prioritized = _prioritized_categories(categories)
    if not prioritized:
        return NO_ATTENTION_TEXT
    lines = ["Categorias que merecem atenção este mês:"]
    lines.extend(_format_line(c) for c in prioritized)
    return "\n".join(lines)


def budget_advice(
    user_id: str,
    month: str | None = None,
    *,
    get_summary: Callable[..., dict] | None = None,
) -> AgentResponse:
    """Especialista Orçamento: alertas priorizados por categoria (BUD-03, CONV-03, CONV-04)."""
    fetch = get_summary if get_summary is not None else _get_budget_summary
    summary = fetch(user_id=user_id, month=month or date.today().strftime("%Y-%m"))
    if not summary["has_income"]:
        return AgentResponse(text=NO_INCOME_ADVICE)
    return AgentResponse(text=_format_advice(summary["categories"]))


def orcamento_node(state: AgentState, *, get_summary: Callable[..., dict] | None = None) -> dict:
    """LangGraph node: resposta do especialista Orçamento (BUD-03, CONV-03, CONV-04)."""
    return {"final_response": budget_advice(state["user_id"], get_summary=get_summary)}
