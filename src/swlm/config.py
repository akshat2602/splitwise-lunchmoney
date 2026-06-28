"""Configuration from environment variables (see README for the full list)."""

from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED = (
    "SPLITWISE_API_KEY",
    "LUNCHMONEY_ACCESS_TOKEN",
    "LM_CLEARING_ASSET_ID",
)

_TRUE = {"1", "true", "yes", "on"}


@dataclass
class Settings:
    splitwise_api_key: str
    lunchmoney_access_token: str
    clearing_asset_id: int
    settlement_category_name: str = "Splitwise Settlement"
    base_currency: str = "USD"
    apply_rules: bool = True
    report_webhook: str | None = None
    my_splitwise_user_id: int | None = None
    db_path: str = "swlm_state.db"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)

        missing = [k for k in _REQUIRED if not env.get(k)]
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        my_id = env.get("MY_SPLITWISE_USER_ID")
        return cls(
            splitwise_api_key=env["SPLITWISE_API_KEY"],
            lunchmoney_access_token=env["LUNCHMONEY_ACCESS_TOKEN"],
            clearing_asset_id=int(env["LM_CLEARING_ASSET_ID"]),
            settlement_category_name=env.get("SETTLEMENT_CATEGORY_NAME", "Splitwise Settlement"),
            base_currency=env.get("BASE_CURRENCY", "USD").upper(),
            apply_rules=env.get("APPLY_RULES", "true").lower() in _TRUE,
            report_webhook=env.get("REPORT_WEBHOOK") or None,
            my_splitwise_user_id=int(my_id) if my_id else None,
            db_path=env.get("SWLM_DB_PATH", "swlm_state.db"),
        )
