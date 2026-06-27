"""Lunch Money is the source of truth for what we've already written: we rebuild the
external_id -> txn_id map from LM on every run, so correctness never depends on local state.
"""

from datetime import date
from types import SimpleNamespace

from swlm.lunchmoney_client import LunchMoneyClient


class FakeLunch:
    def __init__(self, txns):
        self._txns = txns
        self.calls = []

    def get_transactions(self, **kwargs):
        self.calls.append(kwargs)
        return self._txns


def _txn(txn_id, external_id):
    return SimpleNamespace(id=txn_id, external_id=external_id)


def test_external_id_map_keys_by_external_id():
    fake = FakeLunch([_txn(11, "sw:1:clear"), _txn(12, "sw:2:share")])
    client = LunchMoneyClient(fake)

    m = client.get_external_id_map(9001, date(2026, 1, 1), date(2026, 6, 1))

    assert m == {"sw:1:clear": 11, "sw:2:share": 12}
    assert fake.calls[0]["asset_id"] == 9001


def test_external_id_map_ignores_unmanaged_txns():
    fake = FakeLunch([_txn(11, "sw:1:clear"), _txn(99, None), _txn(50, "manual-thing")])
    client = LunchMoneyClient(fake)

    m = client.get_external_id_map(9001, date(2026, 1, 1), date(2026, 6, 1))

    assert m == {"sw:1:clear": 11}  # only our sw: ids
