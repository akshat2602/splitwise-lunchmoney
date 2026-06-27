"""Orchestrator — ties Splitwise + Lunch Money together, with Lunch Money as the source of truth.

Correctness does NOT depend on durable local state. Every run rebuilds the
``external_id -> txn_id`` map straight from Lunch Money and upserts against it, so a crash
mid-run, a lost/corrupt cache, or a missed cursor advance all self-heal on the next run
(no duplicates, no desync). The local SQLite store is a pure cursor cache, safe to lose.
The drift check is the final backstop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from swlm.drift import compute_drift, net_position
from swlm.lunchmoney_client import LunchMoneyClient
from swlm.models import ActionPlan, ClearKind, Expense, PlannedTxn
from swlm.reconcile import external_id, plan_expense
from swlm.splitwise_client import SplitwiseClient
from swlm.state import StateStore


@dataclass(frozen=True)
class PlannedOp:
    """A planned txn paired with the existing Lunch Money id (None = insert)."""

    txn: PlannedTxn
    existing_txn_id: int | None


def _reversal_txn(expense_id: int, asset_id: int) -> PlannedTxn:
    return PlannedTxn(
        expense_id=expense_id,
        kind=ClearKind,
        external_id=external_id(expense_id),
        signed_amount=Decimal("0"),
        asset_id=asset_id,
        payee="Splitwise (reversed)",
        notes=f"Reversed: Splitwise item {expense_id} deleted",
        date=date.today(),
        reverse=True,
    )


def plan_operations(
    expenses: list[Expense],
    existing_ids: dict[str, int],
    *,
    my_user_id: int,
    clearing_asset_id: int,
    settlement_category_id: int | None,
) -> list[PlannedOp]:
    """Diff fresh items against what Lunch Money already holds (``existing_ids``).

    An op's ``existing_txn_id`` comes solely from the LM map: present -> update in place,
    absent -> insert. Deletions reverse the clearing txn only if LM actually has it. No local
    state is consulted, so the result is identical whether or not a cache exists.
    """
    ops: list[PlannedOp] = []

    for exp in expenses:
        if exp.is_deleted:
            tid = existing_ids.get(external_id(exp.id))
            if tid is not None:
                ops.append(PlannedOp(_reversal_txn(exp.id, clearing_asset_id), tid))
            continue

        for txn in plan_expense(
            exp,
            my_user_id=my_user_id,
            clearing_asset_id=clearing_asset_id,
            settlement_category_id=settlement_category_id,
        ):
            ops.append(PlannedOp(txn, existing_ids.get(txn.external_id)))

    return ops


@dataclass
class ReconcilerConfig:
    my_user_id: int
    clearing_asset_id: int
    settlement_category_id: int | None
    apply_rules: bool = True
    lookback_days: int = 90


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

    def _updated_after(self, since: str | None) -> str:
        if since:
            return since
        cursor = self.state.get_cursor()
        if cursor:
            return cursor
        start = datetime.now(UTC) - timedelta(days=self.cfg.lookback_days)
        return start.strftime("%Y-%m-%dT%H:%M:%SZ")

    def run(self, *, dry_run: bool, since: str | None = None) -> ActionPlan:
        updated_after = self._updated_after(since)
        expenses = self.sw.get_expenses(updated_after=updated_after)

        # Rebuild the source-of-truth map over a window wide enough to cover every txn we
        # might touch: from the OLDEST affected item's date through today. This guarantees
        # edits to old items resolve to their existing txn (never a duplicate insert).
        scan_start = min((e.date for e in expenses), default=date.today())
        existing_ids = self.lm.get_external_id_map(
            self.cfg.clearing_asset_id, scan_start, date.today()
        )

        ops = plan_operations(
            expenses,
            existing_ids,
            my_user_id=self.cfg.my_user_id,
            clearing_asset_id=self.cfg.clearing_asset_id,
            settlement_category_id=self.cfg.settlement_category_id,
        )

        plan = ActionPlan(txns=[op.txn for op in ops])

        net = net_position(self.sw.get_friends(), [])
        actual = self.lm.get_asset_balance(self.cfg.clearing_asset_id)
        expected, drift = compute_drift(net, actual)
        plan.expected_clearing, plan.actual_clearing, plan.drift = expected, actual, drift

        if dry_run:
            return plan

        for op in ops:
            self.lm.upsert(op.txn, op.existing_txn_id, apply_rules=self.cfg.apply_rules)

        # Advance the cursor only AFTER a successful apply. If we crash before this, the
        # cursor stays put and the next run reprocesses idempotently.
        if expenses:
            newest = max((e.updated_at for e in expenses if e.updated_at), default="")
            if newest:
                self.state.set_cursor(newest)
        self.state.set_last_run(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        return plan
