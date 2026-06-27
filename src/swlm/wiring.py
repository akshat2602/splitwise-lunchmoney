"""Build a fully wired Reconciler from Settings (the composition root)."""

from __future__ import annotations

from lunchable import LunchMoney

from swlm.config import Settings
from swlm.lunchmoney_client import LunchMoneyClient
from swlm.runner import Reconciler, ReconcilerConfig
from swlm.splitwise_client import SplitwiseClient
from swlm.state import StateStore


def build_reconciler(settings: Settings) -> tuple[Reconciler, SplitwiseClient, StateStore]:
    sw = SplitwiseClient(settings.splitwise_api_key)
    lm = LunchMoneyClient(LunchMoney(access_token=settings.lunchmoney_access_token))
    state = StateStore(settings.db_path)

    name_to_id = {c.name.lower(): c.id for c in lm.get_categories()}
    settlement_category_id = name_to_id.get(settings.settlement_category_name.lower())

    my_user_id = settings.my_splitwise_user_id or sw.get_current_user_id()

    config = ReconcilerConfig(
        my_user_id=my_user_id,
        clearing_asset_id=settings.clearing_asset_id,
        settlement_category_id=settlement_category_id,
        apply_rules=settings.apply_rules,
        lookback_days=settings.lookback_days,
    )
    return Reconciler(sw, lm, state, config), sw, state
