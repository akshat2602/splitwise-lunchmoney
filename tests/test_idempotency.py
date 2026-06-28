"""Idempotency + skip-unchanged are driven by the Lunch Money index (the source of truth),
NOT by local state — so a lost cache or a mid-run crash self-heals, and steady-state runs
write nothing.
"""

from dataclasses import replace
from decimal import Decimal

from swlm.lunchmoney_client import ManagedTxn
from swlm.runner import plan_operations
from tests.conftest import CLEARING_ASSET_ID, MY_ID, SETTLEMENT_CATEGORY_ID, make_expense


def _plan(expenses, index):
    return plan_operations(
        expenses,
        index,
        my_user_id=MY_ID,
        clearing_asset_id=CLEARING_ASSET_ID,
        settlement_category_id=SETTLEMENT_CATEGORY_ID,
    )


def _managed(txn_id, amount):
    return ManagedTxn(id=txn_id, amount=Decimal(amount), category_id=None)


def test_new_item_not_in_lm_inserts():
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    ops = _plan([exp], index={})
    assert len(ops) == 1
    assert ops[0].existing_txn_id is None
    assert ops[0].txn.external_id == "sw:1:clear"


def test_unchanged_item_is_skipped():
    # Already in LM with the exact amount we'd post (clear_offset = -90) -> no op.
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    ops = _plan([exp], index={"sw:1:clear": _managed(999, "-90.00")})
    assert ops == []


def test_changed_amount_updates_in_place():
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    ops = _plan([exp], index={"sw:1:clear": _managed(999, "-50.00")})  # stale amount
    assert len(ops) == 1
    assert ops[0].existing_txn_id == 999


def test_deleted_item_reverses_only_if_nonzero_in_lm():
    exp = make_expense(
        my_paid="120", my_owed="30", friend_paid="0", friend_owed="90",
        deleted_at="2026-06-10T00:00:00Z",
    )
    ops = _plan([exp], index={"sw:1:clear": _managed(999, "-90.00")})
    assert len(ops) == 1
    assert ops[0].existing_txn_id == 999
    assert ops[0].txn.reverse
    assert ops[0].txn.signed_amount == Decimal("0")


def test_deleted_item_already_zero_does_nothing():
    exp = make_expense(
        my_paid="120", my_owed="30", friend_paid="0", friend_owed="90",
        deleted_at="2026-06-10T00:00:00Z",
    )
    ops = _plan([exp], index={"sw:1:clear": _managed(999, "0.00")})
    assert ops == []


def test_deleted_item_not_in_lm_does_nothing():
    exp = make_expense(
        my_paid="120", my_owed="30", friend_paid="0", friend_owed="90",
        deleted_at="2026-06-10T00:00:00Z",
    )
    assert _plan([exp], index={}) == []


def test_orphan_in_lm_is_zeroed():
    # LM holds a txn for an expense Splitwise no longer reports (or that became even/settled).
    ops = _plan([], index={"sw:42:clear": _managed(777, "25.00")})
    assert len(ops) == 1
    assert ops[0].existing_txn_id == 777
    assert ops[0].txn.reverse
    assert ops[0].txn.external_id == "sw:42:clear"


def test_orphan_already_zero_is_left_alone():
    ops = _plan([], index={"sw:42:clear": _managed(777, "0.00")})
    assert ops == []


def test_non_base_currency_expense_is_skipped_and_its_orphan_zeroed():
    # An INR expense must never be posted; if one was wrongly posted before, zero it.
    inr = replace(
        make_expense(my_paid="0", my_owed="500", friend_paid="500", friend_owed="0"),
        currency="INR",
    )
    ops = _plan([inr], index={"sw:1:clear": _managed(777, "500.00")})
    assert len(ops) == 1
    assert ops[0].txn.reverse  # the stale INR txn gets zeroed, not kept
