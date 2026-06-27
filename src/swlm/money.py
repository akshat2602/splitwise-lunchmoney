"""Money helpers. All amounts are Decimal cents; never compare floats for equality."""

from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")


def to_cents(value: Decimal | float | int | str) -> Decimal:
    """Quantize any numeric-ish value to 2 decimal places (banker's rounding)."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_EVEN)


def equal_within_cent(a: Decimal, b: Decimal) -> bool:
    """True when a and b are within one cent — the drift-check epsilon."""
    return abs(a - b) <= CENT
