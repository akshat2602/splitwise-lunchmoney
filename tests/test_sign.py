"""The sign convention is the crux of the whole tool, so it gets its own tests.

Convention: positive signed_amount = DEBIT (spend / money out); negative = credit. We send
debit_as_negative=False to Lunch Money, which reads a positive amount as a debit. The wrapper
is the single place this is defined.
"""

from datetime import date
from decimal import Decimal

from swlm.lunchmoney_client import LunchMoneyClient, to_lm_amount
from swlm.models import ClearKind, PlannedTxn


class FakeLunch:
    def __init__(self):
        self.inserts = []
        self.updates = []

    def insert_transactions(self, transactions, **kwargs):
        self.inserts.append((transactions, kwargs))
        return [777]

    def update_transaction(self, transaction_id, transaction=None, **kwargs):
        self.updates.append((transaction_id, transaction, kwargs))
        return {"updated": True}


def _txn(amount: str, reverse: bool = False) -> PlannedTxn:
    return PlannedTxn(
        expense_id=1,
        kind=ClearKind,
        external_id="sw:1:clear",
        signed_amount=Decimal(amount),
        asset_id=9001,
        payee="Dinner",
        notes="Splitwise expense 1",
        date=date(2026, 6, 1),
    )


def test_to_lm_amount_keeps_positive_as_debit():
    assert to_lm_amount(Decimal("90.00")) == Decimal("90.00")
    assert to_lm_amount(Decimal("-90.00")) == Decimal("-90.00")


def test_insert_passes_debit_as_negative_false_and_preserves_sign():
    fake = FakeLunch()
    client = LunchMoneyClient(fake)

    txn_id = client.upsert(_txn("-90.00"), existing_txn_id=None)

    assert txn_id == 777
    (obj, kwargs) = fake.inserts[0]
    assert kwargs["debit_as_negative"] is False
    assert obj.amount == Decimal("-90.00")
    assert obj.external_id == "sw:1:clear"
    assert obj.asset_id == 9001


def test_update_in_place_uses_existing_id_no_insert():
    fake = FakeLunch()
    client = LunchMoneyClient(fake)

    txn_id = client.upsert(_txn("40.00"), existing_txn_id=555)

    assert txn_id == 555
    assert fake.inserts == []
    (tid, obj, kwargs) = fake.updates[0]
    assert tid == 555
    assert kwargs["debit_as_negative"] is False
    assert obj.amount == Decimal("40.00")


def test_reverse_zeroes_amount():
    fake = FakeLunch()
    client = LunchMoneyClient(fake)
    txn = PlannedTxn(
        expense_id=1,
        kind=ClearKind,
        external_id="sw:1:clear",
        signed_amount=Decimal("40.00"),
        asset_id=9001,
        payee="Dinner",
        notes="x",
        date=date(2026, 6, 1),
        reverse=True,
    )
    client.upsert(txn, existing_txn_id=555)
    (_tid, obj, _kwargs) = fake.updates[0]
    assert obj.amount == Decimal("0.00")
