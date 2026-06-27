"""Pure reconcile logic — the single-offset loan model.

Splitwise Clearing is a loan ledger. Every Splitwise item (expense OR settle-up payment) posts
exactly ONE clearing transaction of ``clear_offset = -my_net``. Summed over everything this
equals ``-net`` (my Splitwise position), so the clearing balance tracks the loan and drift is
~0 by construction.

The signed amount IS the spec's sign convention (positive = debit/spend, negative = credit),
passed verbatim to the Lunch Money client (the single place it maps onto the API). No SDK here,
so every case is unit-tested without a network.
"""

from __future__ import annotations

from swlm.models import ClearKind, Expense, PlannedTxn
from swlm.money import to_cents


def external_id(expense_id: int, kind: str = ClearKind) -> str:
    """Deterministic id so re-runs update in place instead of duplicating."""
    return f"sw:{expense_id}:{kind}"


def plan_expense(
    expense: Expense,
    *,
    my_user_id: int,
    clearing_asset_id: int,
    settlement_category_id: int | None,
) -> list[PlannedTxn]:
    """Return the desired clearing txn(s) for one ACTIVE item (deletions handled upstream).

    At most one txn:
      * ``my_net > 0`` (I fronted): a credit that claws back the over-charge on my card.
      * ``my_net < 0`` (I owe / a friend paid): a debit = my real consumption (or, for a
        settle-up payment, a balance move tagged with the excluded settlement category).
      * ``my_net == 0``: nothing.
    """
    if expense.is_deleted:
        return []

    mine = expense.share_for(my_user_id)
    if mine is None:
        return []

    my_net = to_cents(to_cents(mine.paid_share) - to_cents(mine.owed_share))
    if my_net == 0:
        return []

    clear_offset = to_cents(-my_net)
    # Payments are balance-only (excluded from spend); expenses I owe go to LM rules; credits
    # for fronted expenses stay uncategorized.
    category_id = settlement_category_id if expense.payment else None

    return [
        PlannedTxn(
            expense_id=expense.id,
            kind=ClearKind,
            external_id=external_id(expense.id),
            signed_amount=clear_offset,
            asset_id=clearing_asset_id,
            payee=expense.description,
            notes=f"Splitwise {'payment' if expense.payment else 'expense'} {expense.id}",
            date=expense.date,
            category_id=category_id,
        )
    ]
