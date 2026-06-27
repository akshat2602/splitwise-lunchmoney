from decimal import Decimal

from swlm.money import equal_within_cent, to_cents


def test_to_cents_rounds_half_to_even_at_cent():
    assert to_cents(Decimal("1.005")) == Decimal("1.00")
    assert to_cents(Decimal("1.015")) == Decimal("1.02")


def test_to_cents_accepts_float_and_str():
    assert to_cents(10.1) == Decimal("10.10")
    assert to_cents("3.333") == Decimal("3.33")


def test_equal_within_cent_true_at_or_below_one_cent():
    assert equal_within_cent(Decimal("100.00"), Decimal("100.01"))
    assert equal_within_cent(Decimal("100.00"), Decimal("100.00"))


def test_equal_within_cent_false_above_one_cent():
    assert not equal_within_cent(Decimal("100.00"), Decimal("100.02"))
