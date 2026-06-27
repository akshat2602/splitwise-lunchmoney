"""The dry-run guarantee is mandatory: it must read everything and write NOTHING."""

from decimal import Decimal

from swlm.runner import Reconciler, ReconcilerConfig
from swlm.state import StateStore
from tests.conftest import CLEARING_ASSET_ID, MY_ID, SETTLEMENT_CATEGORY_ID, make_expense


class FakeSW:
    def __init__(self, expenses):
        self._expenses = expenses

    def get_expenses(self, updated_after=None):
        return self._expenses

    def get_friends(self):
        return []


class FakeLM:
    def __init__(self):
        self.upserts = []

    def upsert(self, planned, existing_txn_id, *, apply_rules=False):
        self.upserts.append((planned, existing_txn_id, apply_rules))
        return 4242

    def get_managed_total(self, asset_id, start_date, end_date):
        return Decimal("0.00")  # nothing posted yet

    def get_external_id_map(self, asset_id, start_date, end_date):
        return {}  # nothing in LM yet -> inserts


def _reconciler(tmp_path):
    state = StateStore(tmp_path / "s.db")
    cfg = ReconcilerConfig(
        my_user_id=MY_ID,
        clearing_asset_id=CLEARING_ASSET_ID,
        settlement_category_id=SETTLEMENT_CATEGORY_ID,
        apply_rules=True,
    )
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    lm = FakeLM()
    return Reconciler(FakeSW([exp]), lm, state, cfg), lm, state


def test_dry_run_writes_nothing(tmp_path):
    rec, lm, state = _reconciler(tmp_path)

    plan = rec.run(dry_run=True)

    assert len(plan.txns) == 1
    assert plan.drift == Decimal("0.00")
    assert lm.upserts == []  # NO Lunch Money writes
    assert state.get_cursor() is None  # NO cursor advance
    assert state.get_last_run() is None  # NO state mutation


def test_real_run_writes_with_apply_rules_and_advances_cursor(tmp_path):
    rec, lm, state = _reconciler(tmp_path)

    rec.run(dry_run=False)

    assert len(lm.upserts) == 1
    assert lm.upserts[0][1] is None  # not in LM map -> insert
    assert lm.upserts[0][2] is True  # apply_rules forwarded
    assert state.get_cursor() == "2026-06-01T00:00:00Z"
    assert state.get_last_run() is not None
