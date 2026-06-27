from datetime import date
from decimal import Decimal

import httpx
import respx

from swlm.splitwise_client import BASE_URL, SplitwiseClient


def make_client(**kw):
    # no real sleeping during retry tests
    return SplitwiseClient(api_key="k", sleep=lambda _s: None, **kw)


@respx.mock
def test_get_current_user_parses_id():
    respx.get(f"{BASE_URL}/get_current_user").mock(
        return_value=httpx.Response(200, json={"user": {"id": 100, "first_name": "Me"}})
    )
    assert make_client().get_current_user_id() == 100


@respx.mock
def test_get_expenses_parses_shares_payment_and_deleted():
    respx.get(f"{BASE_URL}/get_expenses").mock(
        return_value=httpx.Response(
            200,
            json={
                "expenses": [
                    {
                        "id": 7,
                        "description": "Dinner",
                        "cost": "120.00",
                        "currency_code": "USD",
                        "date": "2026-06-01T12:00:00Z",
                        "updated_at": "2026-06-02T00:00:00Z",
                        "deleted_at": None,
                        "payment": False,
                        "category": {"id": 12, "name": "Dining out"},
                        "users": [
                            {
                                "user_id": 100,
                                "paid_share": "120.00",
                                "owed_share": "30.00",
                            },
                            {
                                "user": {"id": 200, "first_name": "Friend"},
                                "paid_share": "0.00",
                                "owed_share": "90.00",
                            },
                        ],
                    }
                ]
            },
        )
    )
    exps = make_client().get_expenses()
    assert len(exps) == 1
    e = exps[0]
    assert e.id == 7
    assert e.cost == Decimal("120.00")
    assert e.date == date(2026, 6, 1)
    assert e.payment is False
    assert e.category_name == "Dining out"
    me = e.share_for(100)
    assert me.paid_share == Decimal("120.00")
    assert e.share_for(200).owed_share == Decimal("90.00")


@respx.mock
def test_get_expenses_paginates_until_short_page():
    page1 = [{"id": i, "description": "x", "cost": "1", "currency_code": "USD",
              "date": "2026-06-01", "updated_at": "u", "deleted_at": None,
              "payment": False, "category": None, "users": []} for i in range(100)]
    page2 = [{"id": 100, "description": "x", "cost": "1", "currency_code": "USD",
              "date": "2026-06-01", "updated_at": "u", "deleted_at": None,
              "payment": False, "category": None, "users": []}]
    route = respx.get(f"{BASE_URL}/get_expenses")
    route.side_effect = [
        httpx.Response(200, json={"expenses": page1}),
        httpx.Response(200, json={"expenses": page2}),
    ]
    exps = make_client().get_expenses()
    assert len(exps) == 101
    assert route.call_count == 2


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(f"{BASE_URL}/get_current_user")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"user": {"id": 5}}),
    ]
    assert make_client().get_current_user_id() == 5
    assert route.call_count == 2


@respx.mock
def test_get_friends_parses_balances():
    respx.get(f"{BASE_URL}/get_friends").mock(
        return_value=httpx.Response(
            200,
            json={
                "friends": [
                    {
                        "id": 200,
                        "first_name": "Friend",
                        "balance": [{"currency_code": "USD", "amount": "140.00"}],
                    }
                ]
            },
        )
    )
    friends = make_client().get_friends()
    assert friends[0].name == "Friend"
    assert friends[0].balances[0].amount == Decimal("140.00")
    assert friends[0].balances[0].currency == "USD"
