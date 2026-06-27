"""Splitwise REST client over httpx — explicit endpoints, plain dict -> dataclass mapping.

Chosen over the official SDK for reviewability: every field we read is visible here. Handles
full pagination of ``get_expenses`` and retries 429s with exponential backoff (respecting
``Retry-After`` when present).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime

import httpx

from swlm.models import Expense, ExpenseUser, Friend, FriendBalance
from swlm.money import to_cents

BASE_URL = "https://secure.splitwise.com/api/v3.0"
PAGE_LIMIT = 100


def _parse_date(raw: str) -> date:
    """Accept '2026-06-01' or full ISO8601 (with trailing Z) and return the date."""
    cleaned = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        return date.fromisoformat(raw[:10])


def _parse_expense(raw: dict) -> Expense:
    category = raw.get("category") or {}
    users = []
    for u in raw.get("users", []):
        user_id = u.get("user_id")
        if user_id is None:
            user_id = u.get("user", {}).get("id")
        users.append(
            ExpenseUser(
                user_id=int(user_id),
                paid_share=to_cents(u.get("paid_share", "0")),
                owed_share=to_cents(u.get("owed_share", "0")),
            )
        )
    return Expense(
        id=int(raw["id"]),
        description=raw.get("description", ""),
        cost=to_cents(raw.get("cost", "0")),
        currency=raw.get("currency_code", "USD"),
        date=_parse_date(raw["date"]),
        updated_at=raw.get("updated_at", ""),
        payment=bool(raw.get("payment", False)),
        deleted_at=raw.get("deleted_at"),
        category_id=category.get("id"),
        category_name=category.get("name"),
        users=users,
    )


class SplitwiseClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
    ):
        self.base_url = base_url
        self._sleep = sleep
        self._max_retries = max_retries
        self._client = client or httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{path}"
        delay = 1.0
        for attempt in range(self._max_retries + 1):
            resp = self._client.get(url, params=params)
            if resp.status_code == 429 and attempt < self._max_retries:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after is not None else delay
                self._sleep(wait)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    # -- endpoints ----------------------------------------------------------

    def get_current_user_id(self) -> int:
        return int(self._get("get_current_user")["user"]["id"])

    def get_expenses(self, updated_after: str | None = None) -> list[Expense]:
        """Fetch all expenses (paginated), optionally only those updated after a cursor."""
        out: list[Expense] = []
        offset = 0
        while True:
            params: dict = {"limit": PAGE_LIMIT, "offset": offset}
            if updated_after:
                params["updated_after"] = updated_after
            page = self._get("get_expenses", params).get("expenses", [])
            out.extend(_parse_expense(e) for e in page)
            if len(page) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT
        return out

    def get_friends(self) -> list[Friend]:
        friends = []
        for f in self._get("get_friends").get("friends", []):
            balances = [
                FriendBalance(currency=b.get("currency_code", "USD"), amount=to_cents(b["amount"]))
                for b in f.get("balance", [])
            ]
            name = f.get("first_name") or f.get("email") or str(f.get("id"))
            friends.append(Friend(id=int(f["id"]), name=name, balances=balances))
        return friends

    def close(self) -> None:
        self._client.close()
