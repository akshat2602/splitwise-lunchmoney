"""Thin wrapper around the lunchable SDK. The debit/credit SIGN is defined here, once.

Everywhere else in the codebase, a "signed amount" means: positive = debit (spend / money
out), negative = credit. We always call Lunch Money with ``debit_as_negative=False``, so the
API reads a positive amount as a debit — matching our convention. ``to_lm_amount`` is the
single translation point (identity today, but the place to change if the convention ever does).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from lunchable.models import TransactionInsertObject, TransactionUpdateObject

from swlm.models import PlannedTxn
from swlm.money import to_cents


def to_lm_amount(signed: Decimal) -> Decimal:
    """Map our signed amount to the Lunch Money amount. Positive = debit (see module docstring)."""
    return signed


class LunchMoneyClient:
    """Wraps a ``lunchable.LunchMoney`` (or any object with the same methods)."""

    def __init__(self, lunch):
        self.lunch = lunch

    # -- writes -------------------------------------------------------------

    def upsert(
        self, planned: PlannedTxn, existing_txn_id: int | None, *, apply_rules: bool = False
    ) -> int:
        """Insert a new managed txn, or update the existing one in place. Returns its id.

        ``apply_rules`` runs Lunch Money's auto-categorization rules at insert time (used so
        the user's rules categorize the items they owe, instead of a local category map).
        """
        signed = Decimal("0.00") if planned.reverse else to_cents(planned.signed_amount)
        amount = float(to_lm_amount(signed))  # SDK field is float; sign already centralized

        if existing_txn_id is None:
            obj = TransactionInsertObject(
                date=planned.date,
                amount=amount,
                payee=planned.payee,
                notes=planned.notes,
                category_id=planned.category_id,
                asset_id=planned.asset_id,
                external_id=planned.external_id,
                status=TransactionInsertObject.StatusEnum.cleared,
            )
            ids = self.lunch.insert_transactions(
                obj, debit_as_negative=False, skip_duplicates=False, apply_rules=apply_rules
            )
            return ids[0]

        obj = TransactionUpdateObject(
            amount=amount,
            payee=planned.payee,
            notes=planned.notes,
            category_id=planned.category_id,
        )
        self.lunch.update_transaction(existing_txn_id, obj, debit_as_negative=False)
        return existing_txn_id

    def tag_transfer(self, txn_id: int, category_id: int, note: str) -> None:
        """The ONLY edit allowed on a Plaid txn: set category + notes (never amount/external_id)."""
        obj = TransactionUpdateObject(category_id=category_id, notes=note)
        self.lunch.update_transaction(txn_id, obj)

    # -- reads --------------------------------------------------------------

    def get_assets(self) -> list:
        return self.lunch.get_assets()

    def get_asset_balance(self, asset_id: int) -> Decimal:
        for asset in self.lunch.get_assets():
            if asset.id == asset_id:
                return to_cents(Decimal(str(asset.balance)))
        raise ValueError(f"asset {asset_id} not found")

    def get_categories(self) -> list:
        return self.lunch.get_categories()

    def get_transactions(
        self, asset_id: int, start_date: date, end_date: date
    ) -> list:
        return self.lunch.get_transactions(
            asset_id=asset_id, start_date=start_date, end_date=end_date, debit_as_negative=False
        )

    def get_external_id_map(
        self, asset_id: int, start_date: date, end_date: date
    ) -> dict[str, int]:
        """Rebuild {external_id: txn_id} for OUR managed txns straight from Lunch Money.

        This is the idempotency backbone: every run reconstructs what we've written from the
        source of truth, so a lost/corrupt local cache or a mid-run crash self-heals — we
        update existing txns in place instead of duplicating.
        """
        txns = self.lunch.get_transactions(
            asset_id=asset_id, start_date=start_date, end_date=end_date, debit_as_negative=False
        )
        return {
            t.external_id: t.id
            for t in txns
            if t.external_id and t.external_id.startswith("sw:")
        }
