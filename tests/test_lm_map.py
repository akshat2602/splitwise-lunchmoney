"""Lunch Money is the source of truth: we rebuild the managed-txn index from LM on every run,
so correctness never depends on local state. The index drives idempotency, skip-unchanged, and
the drift total.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from swlm.lunchmoney_client import LunchMoneyClient


class FakeLunch:
    """Paginates like Lunch Money: returns PAGE_LIMIT-sized slices by offset."""

    def __init__(self, txns):
        self._txns = txns
        self.calls = []

    def get_transactions(self, *, limit=None, offset=0, **kwargs):
        self.calls.append({"limit": limit, "offset": offset, **kwargs})
        if limit is None:
            return self._txns
        return self._txns[offset : offset + limit]


def _txn(txn_id, external_id, amount=0, category_id=None):
    return SimpleNamespace(
        id=txn_id, external_id=external_id, amount=amount, category_id=category_id
    )


def test_index_keys_managed_txns_with_amount_and_category():
    fake = FakeLunch([_txn(11, "sw:1:clear", -90, 5), _txn(12, "sw:2:clear", 40, None)])
    client = LunchMoneyClient(fake)

    idx = client.get_managed_index(9001, date(2026, 1, 1), date(2026, 6, 1))

    assert set(idx) == {"sw:1:clear", "sw:2:clear"}
    assert idx["sw:1:clear"].id == 11
    assert idx["sw:1:clear"].amount == Decimal("-90.00")
    assert idx["sw:1:clear"].category_id == 5


def test_index_ignores_unmanaged_txns():
    fake = FakeLunch([_txn(11, "sw:1:clear", -90), _txn(99, None, 1000), _txn(50, "manual", 500)])
    client = LunchMoneyClient(fake)

    idx = client.get_managed_index(9001, date(2026, 1, 1), date(2026, 6, 1))

    assert set(idx) == {"sw:1:clear"}


def test_get_transactions_paginates_fully():
    # 1200 txns -> 3 pages of 500 (last short). All must be indexed.
    txns = [_txn(i, f"sw:{i}:clear", 1) for i in range(1200)]
    fake = FakeLunch(txns)
    client = LunchMoneyClient(fake)

    idx = client.get_managed_index(9001, date(2000, 1, 1), date(2026, 6, 1))

    assert len(idx) == 1200
    assert len(fake.calls) == 3  # 500 + 500 + 200
