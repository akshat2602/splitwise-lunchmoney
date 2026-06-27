"""Drift check — the safety net.

My net Splitwise position is the sum of friend + group balances. The clearing account
should mirror its negative (``expected = -net``). ``drift = actual - expected``; ~0 (within
one cent) means everything reconciled. Any larger drift is the alert signal.
"""

from __future__ import annotations

from decimal import Decimal

from swlm.models import Friend, GroupBalance
from swlm.money import equal_within_cent, to_cents


def net_position(
    friends: list[Friend],
    group_balances: list[GroupBalance],
    currency: str = "USD",
) -> Decimal:
    """Sum balances in ``currency`` (positive = others owe me)."""
    total = Decimal("0")
    for friend in friends:
        for bal in friend.balances:
            if bal.currency == currency:
                total += bal.amount
    for gb in group_balances:
        if gb.currency == currency:
            total += gb.amount
    return to_cents(total)


def compute_drift(net: Decimal, actual_clearing: Decimal) -> tuple[Decimal, Decimal]:
    """Return ``(expected_clearing, drift)`` where expected = -net, drift = actual - expected."""
    expected = to_cents(-net)
    drift = to_cents(actual_clearing - expected)
    return expected, drift


def is_reconciled(drift: Decimal) -> bool:
    return equal_within_cent(drift, Decimal("0"))
