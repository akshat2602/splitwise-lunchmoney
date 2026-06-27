"""Plain dataclasses — Splitwise domain objects and the Lunch Money action plan.

Kept SDK-free so the reconcile logic is a pure function over these and trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# ---------------------------------------------------------------------------
# Splitwise domain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpenseUser:
    """One participant's share in a Splitwise expense."""

    user_id: int
    paid_share: Decimal
    owed_share: Decimal


@dataclass(frozen=True)
class Expense:
    """A Splitwise expense (or settle-up payment when ``payment`` is True)."""

    id: int
    description: str
    cost: Decimal
    currency: str
    date: date
    updated_at: str  # ISO8601 string as returned by the API (used for the cursor)
    payment: bool
    deleted_at: str | None
    category_id: int | None
    category_name: str | None
    users: list[ExpenseUser]

    def share_for(self, user_id: int) -> ExpenseUser | None:
        for u in self.users:
            if u.user_id == user_id:
                return u
        return None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@dataclass(frozen=True)
class FriendBalance:
    """Net balance with one friend, per currency (positive = friend owes me)."""

    currency: str
    amount: Decimal


@dataclass(frozen=True)
class Friend:
    id: int
    name: str
    balances: list[FriendBalance] = field(default_factory=list)


@dataclass(frozen=True)
class GroupBalance:
    """My net balance within a group, per currency (positive = I am owed)."""

    currency: str
    amount: Decimal


# ---------------------------------------------------------------------------
# Lunch Money action plan
# ---------------------------------------------------------------------------

# kind identifies the deterministic external_id suffix: sw:<expense_id>:<kind>.
# Single-offset model uses exactly one kind per item.
ClearKind = "clear"


@dataclass(frozen=True)
class PlannedTxn:
    """Desired end-state of one Lunch Money transaction we manage.

    ``signed_amount`` follows the centralized sign convention: positive = debit (spend),
    negative = credit. The applier turns this into an insert or an in-place update keyed
    by ``external_id``; ``reverse`` marks a txn to zero out (deleted/changed expense).
    """

    expense_id: int
    kind: str  # ClearKind
    external_id: str
    signed_amount: Decimal
    asset_id: int
    payee: str
    notes: str
    date: date
    category_id: int | None = None
    reverse: bool = False


@dataclass
class ActionPlan:
    """All planned Lunch Money writes plus the projected drift, for dry-run printing."""

    txns: list[PlannedTxn] = field(default_factory=list)
    expected_clearing: Decimal | None = None
    actual_clearing: Decimal | None = None
    drift: Decimal | None = None
