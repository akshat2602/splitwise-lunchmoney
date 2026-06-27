"""Idempotency is driven by the Lunch Money external_id map (the source of truth), NOT by
local state — so a lost cache or a mid-run crash self-heals on the next run.
"""

from decimal import Decimal

from swlm.runner import plan_operations
from tests.conftest import CLEARING_ASSET_ID, MY_ID, SETTLEMENT_CATEGORY_ID, make_expense


def _plan(expenses, existing_ids):
    return plan_operations(
        expenses,
        existing_ids,
        my_user_id=MY_ID,
        clearing_asset_id=CLEARING_ASSET_ID,
        settlement_category_id=SETTLEMENT_CATEGORY_ID,
    )


def test_new_item_not_in_lm_inserts():
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    ops = _plan([exp], existing_ids={})
    assert len(ops) == 1
    assert ops[0].existing_txn_id is None
    assert ops[0].txn.external_id == "sw:1:clear"


def test_item_already_in_lm_updates_in_place():
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    ops = _plan([exp], existing_ids={"sw:1:clear": 999})
    assert len(ops) == 1
    assert ops[0].existing_txn_id == 999  # found in LM -> update, never duplicate


def test_payment_is_processed_not_skipped():
    exp = make_expense(
        my_paid="0", my_owed="140", friend_paid="140", friend_owed="0", cost="140", payment=True
    )
    ops = _plan([exp], existing_ids={})
    assert len(ops) == 1
    assert ops[0].txn.category_id == SETTLEMENT_CATEGORY_ID


def test_deleted_item_reverses_only_if_in_lm():
    exp = make_expense(
        my_paid="120", my_owed="30", friend_paid="0", friend_owed="90",
        deleted_at="2026-06-10T00:00:00Z",
    )
    ops = _plan([exp], existing_ids={"sw:1:clear": 999})
    assert len(ops) == 1
    assert ops[0].existing_txn_id == 999
    assert ops[0].txn.reverse
    assert ops[0].txn.signed_amount == Decimal("0")


def test_deleted_item_not_in_lm_does_nothing():
    exp = make_expense(
        my_paid="120", my_owed="30", friend_paid="0", friend_owed="90",
        deleted_at="2026-06-10T00:00:00Z",
    )
    assert _plan([exp], existing_ids={}) == []
