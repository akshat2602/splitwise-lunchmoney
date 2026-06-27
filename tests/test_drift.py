from decimal import Decimal

from swlm.drift import compute_drift, is_reconciled, net_position
from swlm.models import Friend, FriendBalance, GroupBalance


def test_net_position_sums_friend_and_group_balances_in_currency():
    friends = [
        Friend(id=1, name="A", balances=[FriendBalance("USD", Decimal("140.00"))]),
        Friend(id=2, name="B", balances=[FriendBalance("USD", Decimal("-20.00"))]),
    ]
    groups = [GroupBalance("USD", Decimal("10.00"))]
    assert net_position(friends, groups) == Decimal("130.00")


def test_net_position_ignores_other_currencies():
    friends = [
        Friend(id=1, name="A", balances=[FriendBalance("EUR", Decimal("999.00"))]),
    ]
    assert net_position(friends, [], currency="USD") == Decimal("0.00")


def test_compute_drift_expected_is_negative_net():
    # I'm owed +130 -> clearing should sit at -130. Actual is -130.50 -> drift -0.50
    expected, drift = compute_drift(net=Decimal("130.00"), actual_clearing=Decimal("-130.50"))
    assert expected == Decimal("-130.00")
    assert drift == Decimal("-0.50")


def test_is_reconciled_within_one_cent():
    assert is_reconciled(Decimal("0.01"))
    assert is_reconciled(Decimal("-0.01"))
    assert not is_reconciled(Decimal("0.02"))
