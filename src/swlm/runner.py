"""Orchestrator — full self-cleaning resync, with Lunch Money as the source of truth.

Every run fetches ALL Splitwise expenses, computes the complete set of desired clearing
offsets (base-currency items only), and reconciles Lunch Money to match it EXACTLY:

  * desired offset missing in LM      -> insert
  * present with a different amount    -> update in place
  * present and already correct        -> skip (steady-state writes nothing)
  * managed txn with no desired offset -> zero it out (deleted, settled-to-even, wrong
    currency, or anything we shouldn't be holding)

Because correctness never depends on durable local state, a crash mid-run, a lost/corrupt
cache, or anything else self-heals on the next run (no duplicates, no desync, no orphans).
The local SQLite store only records the last-run timestamp. The drift check is the backstop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from swlm.drift import compute_drift, net_position
from swlm.lunchmoney_client import LunchMoneyClient, ManagedTxn
from swlm.models import ActionPlan, ClearKind, Expense, PlannedTxn
from swlm.money import to_cents
from swlm.reconcile import plan_expense
from swlm.splitwise_client import SplitwiseClient
from swlm.state import StateStore


@dataclass(frozen=True)
class PlannedOp:
    """A planned txn paired with the existing Lunch Money id (None = insert)."""

    txn: PlannedTxn
    existing_txn_id: int | None


def _reversal_txn(external_id_: str, asset_id: int) -> PlannedTxn:
    """Zero out a managed txn we should no longer be holding."""
    expense_id = int(external_id_.split(":")[1])
    return PlannedTxn(
        expense_id=expense_id,
        kind=ClearKind,
        external_id=external_id_,
        signed_amount=Decimal("0"),
        asset_id=asset_id,
        payee="Splitwise (reversed)",
        notes=f"Reversed: no longer a tracked Splitwise balance ({external_id_})",
        date=date.today(),
        reverse=True,
    )


def plan_operations(
    expenses: list[Expense],
    index: dict[str, ManagedTxn],
    *,
    my_user_id: int,
    clearing_asset_id: int,
    settlement_category_id: int | None,
    base_currency: str = "USD",
) -> list[PlannedOp]:
    """Reconcile Lunch Money (``index``) to EXACTLY the desired offsets from ``expenses``.

    ``expenses`` MUST be the full set (not a cursor window): orphan zero-out relies on a
    complete desired set, or it would wrongly zero txns for unfetched expenses.
    """
    desired: dict[str, PlannedTxn] = {}
    for exp in expenses:
        for txn in plan_expense(
            exp,
            my_user_id=my_user_id,
            clearing_asset_id=clearing_asset_id,
            settlement_category_id=settlement_category_id,
            base_currency=base_currency,
        ):
            desired[txn.external_id] = txn

    ops: list[PlannedOp] = []

    # Insert / update / skip each desired offset.
    for ext, txn in desired.items():
        existing = index.get(ext)
        if existing is None:
            ops.append(PlannedOp(txn, None))
        elif existing.amount != to_cents(txn.signed_amount):
            ops.append(PlannedOp(txn, existing.id))
        # else: already correct -> skip

    # Zero out anything LM holds that we no longer want (deleted / even / wrong currency).
    for ext, existing in index.items():
        if ext not in desired and existing.amount != 0:
            ops.append(PlannedOp(_reversal_txn(ext, clearing_asset_id), existing.id))

    return ops


@dataclass
class ReconcilerConfig:
    my_user_id: int
    clearing_asset_id: int
    settlement_category_id: int | None
    base_currency: str = "USD"
    apply_rules: bool = True


class Reconciler:
    def __init__(
        self,
        sw: SplitwiseClient,
        lm: LunchMoneyClient,
        state: StateStore,
        config: ReconcilerConfig,
    ):
        self.sw = sw
        self.lm = lm
        self.state = state
        self.cfg = config

    def run(self, *, dry_run: bool) -> ActionPlan:
        # Full resync: fetch EVERY expense so the desired set is complete (needed to safely
        # zero orphans). Steady-state still writes nothing thanks to skip-unchanged.
        expenses = self.sw.get_expenses()

        # ONE paginated read over all history is the source of truth: idempotency,
        # skip-unchanged, orphan detection, AND the drift total. end is exclusive-safe.
        end = date.today() + timedelta(days=1)
        index = self.lm.get_managed_index(self.cfg.clearing_asset_id, date(2000, 1, 1), end)

        ops = plan_operations(
            expenses,
            index,
            my_user_id=self.cfg.my_user_id,
            clearing_asset_id=self.cfg.clearing_asset_id,
            settlement_category_id=self.cfg.settlement_category_id,
            base_currency=self.cfg.base_currency,
        )

        plan = ActionPlan(txns=[op.txn for op in ops])

        # actual = sum of our posted offsets (source of truth), NOT the asset's balance field.
        net = net_position(self.sw.get_friends(), [], currency=self.cfg.base_currency)
        actual = to_cents(sum((m.amount for m in index.values()), Decimal("0")))
        expected, drift = compute_drift(net, actual)
        plan.expected_clearing, plan.actual_clearing, plan.drift = expected, actual, drift

        if dry_run:
            return plan

        new_txns = [op.txn for op in ops if op.existing_txn_id is None]
        self.lm.insert_many(new_txns, apply_rules=self.cfg.apply_rules)
        for op in ops:
            if op.existing_txn_id is not None:
                self.lm.update_existing(op.txn, op.existing_txn_id)

        self.state.set_last_run(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        return plan
