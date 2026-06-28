"""Thin wrapper around the lunchable SDK. The debit/credit SIGN is defined here, once.

Everywhere else in the codebase, a "signed amount" means: positive = debit (spend / money
out), negative = credit. We always call Lunch Money with ``debit_as_negative=False``, so the
API reads a positive amount as a debit — matching our convention. ``to_lm_amount`` is the
single translation point (identity today, but the place to change if the convention ever does).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TypeVar

from lunchable.models import TransactionInsertObject, TransactionUpdateObject

from swlm.models import PlannedTxn
from swlm.money import to_cents

T = TypeVar("T")


@dataclass(frozen=True)
class ManagedTxn:
    """One of our existing clearing txns as Lunch Money currently holds it."""

    id: int
    amount: Decimal
    category_id: int | None


def to_lm_amount(signed: Decimal) -> Decimal:
    """Map our signed amount to the Lunch Money amount. Positive = debit (see module docstring)."""
    return signed


class LunchMoneyClient:
    """Wraps a ``lunchable.LunchMoney`` (or any object with the same methods).

    Lunch Money rate-limits (429) and lunchable does not retry, so every call goes through
    ``_call`` which backs off exponentially on 429. Inserts are batched into a single request.
    """

    def __init__(
        self,
        lunch,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 6,
    ):
        self.lunch = lunch
        self._sleep = sleep
        self._max_retries = max_retries

    def _call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        delay = 2.0
        for attempt in range(self._max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:  # lunchable wraps the 429 in LunchMoneyHTTPError
                msg = str(e)
                rate_limited = "Too Many Requests" in msg or "429" in msg
                if rate_limited and attempt < self._max_retries:
                    self._sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("unreachable")

    # -- writes -------------------------------------------------------------

    def _insert_obj(self, planned: PlannedTxn) -> TransactionInsertObject:
        signed = Decimal("0.00") if planned.reverse else to_cents(planned.signed_amount)
        return TransactionInsertObject(
            date=planned.date,
            amount=float(to_lm_amount(signed)),  # SDK field is float; sign already centralized
            payee=planned.payee,
            notes=planned.notes,
            category_id=planned.category_id,
            asset_id=planned.asset_id,
            external_id=planned.external_id,
            status=TransactionInsertObject.StatusEnum.cleared,
        )

    # Lunch Money caps inserts at 500/request; stay well under to also limit 429s.
    INSERT_CHUNK = 100

    def insert_many(self, planned: list[PlannedTxn], *, apply_rules: bool = False) -> list[int]:
        """Insert new managed txns in chunked requests (minimizes 429s). Returns their ids.

        ``apply_rules`` runs Lunch Money's auto-categorization rules at insert time (so the
        user's rules categorize the items they owe, instead of a local category map).
        """
        ids: list[int] = []
        for start in range(0, len(planned), self.INSERT_CHUNK):
            chunk = planned[start : start + self.INSERT_CHUNK]
            objs = [self._insert_obj(p) for p in chunk]
            ids.extend(
                self._call(
                    self.lunch.insert_transactions,
                    objs,
                    debit_as_negative=False,
                    skip_duplicates=False,
                    apply_rules=apply_rules,
                )
            )
        return ids

    def update_existing(self, planned: PlannedTxn, existing_txn_id: int) -> int:
        """Update one managed txn's amount in place (edits, or a reversal to 0). Returns its id.

        Deliberately does NOT touch the category — Lunch Money's auto-rules own the category
        after insert, so re-sending ours would fight them and cause churn on every run.
        """
        signed = Decimal("0.00") if planned.reverse else to_cents(planned.signed_amount)
        obj = TransactionUpdateObject(
            amount=float(to_lm_amount(signed)),
            payee=planned.payee,
            notes=planned.notes,
        )
        self._call(self.lunch.update_transaction, existing_txn_id, obj, debit_as_negative=False)
        return existing_txn_id

    def upsert(
        self, planned: PlannedTxn, existing_txn_id: int | None, *, apply_rules: bool = False
    ) -> int:
        """Insert a new managed txn, or update the existing one in place. Returns its id."""
        if existing_txn_id is None:
            return self.insert_many([planned], apply_rules=apply_rules)[0]
        return self.update_existing(planned, existing_txn_id)

    # -- reads --------------------------------------------------------------

    def get_assets(self) -> list:
        return self._call(self.lunch.get_assets)

    def get_categories(self) -> list:
        return self._call(self.lunch.get_categories)

    PAGE_LIMIT = 500

    def _get_transactions(self, asset_id: int, start_date: date, end_date: date) -> list:
        """Fetch ALL transactions in range, paginating fully (Lunch Money pages results).

        Completeness matters: a truncated read would make get_external_id_map miss existing
        txns and re-insert duplicates, and would undercount the drift total.
        """
        out: list = []
        offset = 0
        while True:
            page = self._call(
                self.lunch.get_transactions,
                asset_id=asset_id,
                start_date=start_date,
                end_date=end_date,
                debit_as_negative=False,
                limit=self.PAGE_LIMIT,
                offset=offset,
            )
            out.extend(page)
            if len(page) < self.PAGE_LIMIT:
                break
            offset += self.PAGE_LIMIT
        return out

    def get_managed_index(
        self, asset_id: int, start_date: date, end_date: date
    ) -> dict[str, ManagedTxn]:
        """Rebuild {external_id: ManagedTxn} for OUR ``sw:`` txns straight from Lunch Money.

        The single source of truth for a run: it drives idempotency (resolve existing txns by
        external_id), the skip-unchanged check (compare amounts), and the drift total (sum of
        amounts). A lost/corrupt local cache or a mid-run crash self-heals — we update in place
        instead of duplicating.
        """
        index: dict[str, ManagedTxn] = {}
        for t in self._get_transactions(asset_id, start_date, end_date):
            if t.external_id and t.external_id.startswith("sw:"):
                index[t.external_id] = ManagedTxn(
                    id=t.id, amount=to_cents(Decimal(str(t.amount))), category_id=t.category_id
                )
        return index
