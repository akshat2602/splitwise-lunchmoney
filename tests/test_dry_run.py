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
        self.inserted = []
        self.updated = []
        self.apply_rules_seen = None

    def insert_many(self, planned, *, apply_rules=False):
        self.inserted.extend(planned)
        self.apply_rules_seen = apply_rules
        return [4242] * len(planned)

    def update_existing(self, planned, existing_txn_id):
        self.updated.append((planned, existing_txn_id))
        return existing_txn_id

    def get_managed_index(self, asset_id, start_date, end_date):
        return {}  # nothing in LM yet -> inserts, drift total 0


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
    assert lm.inserted == []  # NO Lunch Money writes
    assert lm.updated == []
    assert state.get_last_run() is None  # NO state mutation


def test_real_run_writes_with_apply_rules(tmp_path):
    rec, lm, state = _reconciler(tmp_path)

    rec.run(dry_run=False)

    assert len(lm.inserted) == 1  # not in LM index -> insert
    assert lm.updated == []
    assert lm.apply_rules_seen is True  # apply_rules forwarded
    assert state.get_last_run() is not None
