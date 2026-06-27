"""Single-offset loan model: each Splitwise item posts exactly ONE clearing txn of
clear_offset = -my_net. Settle-up payments use the excluded settlement category; expenses I
owe are left uncategorized for Lunch Money rules; expenses I fronted are uncategorized credits.
"""

from decimal import Decimal

from swlm.reconcile import plan_expense
from tests.conftest import CLEARING_ASSET_ID, MY_ID, SETTLEMENT_CATEGORY_ID, make_expense


def _plan(expense):
    return plan_expense(
        expense,
        my_user_id=MY_ID,
        clearing_asset_id=CLEARING_ASSET_ID,
        settlement_category_id=SETTLEMENT_CATEGORY_ID,
    )


def test_fronted_posts_single_negative_offset_no_category():
    # I paid 120, share 30 -> my_net +90, clear_offset -90
    exp = make_expense(my_paid="120", my_owed="30", friend_paid="0", friend_owed="90")
    txns = _plan(exp)
    assert len(txns) == 1
    t = txns[0]
    assert t.external_id == "sw:1:clear"
    assert t.signed_amount == Decimal("-90.00")
    assert t.asset_id == CLEARING_ASSET_ID
    assert t.category_id is None  # credit; nothing to categorize


def test_i_owe_posts_single_positive_offset_for_lm_rules():
    # Friend paid 100, my share 40 -> my_net -40, clear_offset +40 (real consumption = spend)
    exp = make_expense(my_paid="0", my_owed="40", friend_paid="100", friend_owed="60")
    txns = _plan(exp)
    assert len(txns) == 1
    t = txns[0]
    assert t.external_id == "sw:1:clear"
    assert t.signed_amount == Decimal("40.00")
    assert t.category_id is None  # left for Lunch Money rules (apply_rules at insert)


def test_even_split_posts_nothing():
    exp = make_expense(my_paid="30", my_owed="30", friend_paid="30", friend_owed="30")
    assert _plan(exp) == []


def test_settleup_payment_posts_offset_with_excluded_category():
    # Friend pays me 140 to settle -> my_net -140, clear_offset +140, excluded category
    exp = make_expense(
        my_paid="0", my_owed="140", friend_paid="140", friend_owed="0", cost="140", payment=True
    )
    txns = _plan(exp)
    assert len(txns) == 1
    t = txns[0]
    assert t.signed_amount == Decimal("140.00")
    assert t.category_id == SETTLEMENT_CATEGORY_ID  # excluded from spend totals


def test_user_not_in_expense_posts_nothing():
    exp = make_expense(my_paid="0", my_owed="0", friend_paid="50", friend_owed="50", cost="50")
    exp.users.pop(0)
    assert _plan(exp) == []
