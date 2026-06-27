from datetime import date
from decimal import Decimal

from swlm.models import Expense, ExpenseUser

MY_ID = 100
FRIEND_ID = 200

CLEARING_ASSET_ID = 9001
SETTLEMENT_CATEGORY_ID = 77


def make_expense(
    *,
    expense_id: int = 1,
    my_paid: str,
    my_owed: str,
    friend_paid: str,
    friend_owed: str,
    cost: str | None = None,
    payment: bool = False,
    deleted_at: str | None = None,
    updated_at: str = "2026-06-01T00:00:00Z",
    description: str = "Dinner",
    category_name: str = "Dining out",
) -> Expense:
    total = cost or str(Decimal(my_paid) + Decimal(friend_paid))
    return Expense(
        id=expense_id,
        description=description,
        cost=Decimal(total),
        currency="USD",
        date=date(2026, 6, 1),
        updated_at=updated_at,
        payment=payment,
        deleted_at=deleted_at,
        category_id=12,
        category_name=category_name,
        users=[
            ExpenseUser(user_id=MY_ID, paid_share=Decimal(my_paid), owed_share=Decimal(my_owed)),
            ExpenseUser(
                user_id=FRIEND_ID, paid_share=Decimal(friend_paid), owed_share=Decimal(friend_owed)
            ),
        ],
    )
