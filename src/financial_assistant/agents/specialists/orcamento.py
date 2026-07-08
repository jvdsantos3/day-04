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

BUD-03 AC3 fix: "como está meu orçamento?" pede um resumo **incondicional**
das 5 categorias (gasto, %, faixa, status) — distinto de CONV-03's lista
*priorizada* só das categorias que precisam de atenção. Como as duas
perguntas roteiam para o mesmo intent (`budget_advice`, design.md's tabela
de roteamento só tem um padrão para "orçamento"), a distinção é feita aqui
dentro do especialista via ``_wants_full_summary`` (mesmo padrão de
desambiguação por palavra-chave do especialista Transações, T22).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

from financial_assistant.agents.state import AgentState
from financial_assistant.contracts.agent_response import AgentResponse
from mcp_servers.finance.server import get_balance as _get_balance
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

_FULL_SUMMARY_MARKERS = re.compile(r"como (está|anda)|resumo", re.IGNORECASE)
_TOTALS_MARKERS = re.compile(
    r"quanto\s+(gastei|gastei\s+esse|gastei\s+este|foi|de|eu\s+foi)|"
    r"total\s+(de\s+)?(gasto|gastos|despesa|despesas)|"
    r"valor\s+total\s+(de\s+)?(despesa|despesas|gasto|gastos)|"
    r"quero\s+saber.*(despesa|gasto)|"
    r"informa[çc][õo]es.*(despesa|gasto)|"
    r"qual\s+(foi\s+)?(meu\s+)?(total|valor).*(despesa|gasto)|"
    r"qual\s+(meu\s+)?saldo|"
    r"balan[cç]o\s+do\s+m[eê]s",
    re.IGNORECASE,
)


def _wants_full_summary(message: str) -> bool:
    """"Como está meu orçamento?" (BUD-03 AC3) vs. "em quais categorias devo
    economizar?" (CONV-03) — both route to ``budget_advice``; this decides
    which of the two answers the message is actually asking for."""
    return bool(_FULL_SUMMARY_MARKERS.search(message))

def _wants_totals(message: str) -> bool:
    """Perguntas de total do mês: "Quanto gastei este mês?", "qual meu saldo?", etc."""
    return bool(_TOTALS_MARKERS.search(message))


def _format_month_label(month: str) -> str:
    """Display ``YYYY-MM`` as ``MM/YYYY`` for user-facing replies."""
    year, month_num = month.split("-", 1)
    return f"{month_num}/{year}"


def _format_totals(balance: dict) -> str:
    month = balance.get("month") or date.today().strftime("%Y-%m")
    return (
        f"Totais de **{_format_month_label(month)}**:\n"
        f'- Receita: R$ {balance["total_income"]}\n'
        f'- Despesas: R$ {balance["total_expense"]}\n'
        f'- Saldo: R$ {balance["balance"]}'
    )


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


def _format_faixa(category: dict) -> str:
    if category["max_pct"] >= 100:
        return f'≥{category["min_pct"]:.0f}%'
    return f'{category["min_pct"]:.0f}-{category["max_pct"]:.0f}%'


def _format_summary_line(category: dict) -> str:
    return (
        f'- {category["category"]}: gasto R$ {category["spent"]} '
        f'({category["pct"]:.1f}%), faixa {_format_faixa(category)}, status {category["status"]}'
    )


def _format_full_summary(categories: list[dict]) -> str:
    """Resumo incondicional das 5 categorias — gasto, %, faixa, status (BUD-03 AC3)."""
    lines = ["Resumo do seu orçamento este mês:"]
    lines.extend(_format_summary_line(c) for c in categories)
    return "\n".join(lines)


def budget_advice(
    user_id: str,
    month: str | None = None,
    *,
    get_summary: Callable[..., dict] | None = None,
    get_balance: Callable[..., dict] | None = None,
    message: str = "",
) -> AgentResponse:
    """Especialista Orçamento: resumo (BUD-03 AC3) ou alertas priorizados (CONV-03, CONV-04)."""
    resolved_month = month or date.today().strftime("%Y-%m")
    if message and _wants_totals(message):
        fetch_balance = get_balance if get_balance is not None else _get_balance
        return AgentResponse(text=_format_totals(fetch_balance(user_id=user_id, month=resolved_month)))

    fetch = get_summary if get_summary is not None else _get_budget_summary
    summary = fetch(user_id=user_id, month=resolved_month)
    if not summary["has_income"]:
        return AgentResponse(text=NO_INCOME_ADVICE)
    if _wants_full_summary(message):
        return AgentResponse(text=_format_full_summary(summary["categories"]))
    return AgentResponse(text=_format_advice(summary["categories"]))


def orcamento_node(
    state: AgentState,
    *,
    get_summary: Callable[..., dict] | None = None,
    get_balance: Callable[..., dict] | None = None,
) -> dict:
    """LangGraph node: resposta do especialista Orçamento (BUD-03, CONV-03, CONV-04)."""
    message = state["messages"][-1].content
    return {
        "final_response": budget_advice(
            state["user_id"], get_summary=get_summary, get_balance=get_balance, message=message
        )
    }
