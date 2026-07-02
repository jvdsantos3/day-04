"""Default envelope-budget targets and per-user seeding (T4).

The five categories and their target ranges are the central business rule
(spec: "Framework de Orçamento"). Percentages are of the user's monthly income.

The default ``target_pct`` values sit at the centre of each range and sum to
**90%** on purpose — the remaining 10% is an intentional flexibility buffer,
not a misconfiguration (spec BUD-01 / CONV-01).

Note (spec-precision gap): Prazeres is specified as ``≥ 5%`` with no upper
bound, but ``BudgetTarget.max_pct`` is a non-nullable float. The open-ended
maximum is modelled as ``100.0`` (the largest share of income possible).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from financial_assistant.domain.models import BudgetCategory, BudgetTarget

# Prazeres has no upper bound in the spec (≥ 5%); 100% of income is the
# effective ceiling used to satisfy the non-nullable max_pct column.
_OPEN_MAX_PCT = 100.0


@dataclass(frozen=True)
class BudgetDefault:
    """A default target range for a single budget category."""

    category: BudgetCategory
    min_pct: float
    max_pct: float
    target_pct: float


# Ranges and defaults per spec table (Custos Fixos 30–40%, Conforto 15–20%,
# Investimentos 15–25%, Conhecimento 5–15%, Prazeres ≥ 5%). Defaults sum to 90%.
DEFAULT_BUDGET_TARGETS: tuple[BudgetDefault, ...] = (
    BudgetDefault(BudgetCategory.FIXED, 30.0, 40.0, 35.0),
    BudgetDefault(BudgetCategory.COMFORT, 15.0, 20.0, 17.0),
    BudgetDefault(BudgetCategory.INVESTMENTS, 15.0, 25.0, 20.0),
    BudgetDefault(BudgetCategory.KNOWLEDGE, 5.0, 15.0, 10.0),
    BudgetDefault(BudgetCategory.PLEASURES, 5.0, _OPEN_MAX_PCT, 8.0),
)


def seed_budget_targets(session: Session, user_id: uuid.UUID) -> list[BudgetTarget]:
    """Insert the five default :class:`BudgetTarget` rows for ``user_id``.

    Returns the created rows (flushed, not committed — the caller controls the
    transaction boundary).
    """
    targets = [
        BudgetTarget(
            user_id=user_id,
            category=default.category,
            min_pct=default.min_pct,
            max_pct=default.max_pct,
            target_pct=default.target_pct,
        )
        for default in DEFAULT_BUDGET_TARGETS
    ]
    session.add_all(targets)
    session.flush()
    return targets
