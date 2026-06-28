import pytest

from swlm.config import Settings

BASE_ENV = {
    "SPLITWISE_API_KEY": "swk",
    "LUNCHMONEY_ACCESS_TOKEN": "lmt",
    "LM_CLEARING_ASSET_ID": "9001",
}


def test_from_env_required_and_defaults():
    s = Settings.from_env(BASE_ENV)
    assert s.clearing_asset_id == 9001
    assert s.settlement_category_name == "Splitwise Settlement"
    assert s.base_currency == "USD"
    assert s.apply_rules is True
    assert s.report_webhook is None


def test_empty_optionals_fall_back_to_defaults():
    # GitHub Actions passes unset secrets as empty strings, not missing keys.
    env = dict(BASE_ENV)
    env["BASE_CURRENCY"] = ""
    env["SETTLEMENT_CATEGORY_NAME"] = ""
    env["APPLY_RULES"] = ""
    s = Settings.from_env(env)
    assert s.base_currency == "USD"
    assert s.settlement_category_name == "Splitwise Settlement"
    assert s.apply_rules is True


def test_from_env_missing_required_raises():
    env = dict(BASE_ENV)
    del env["LM_CLEARING_ASSET_ID"]
    with pytest.raises(ValueError, match="LM_CLEARING_ASSET_ID"):
        Settings.from_env(env)


def test_optional_overrides():
    env = dict(BASE_ENV)
    env["SETTLEMENT_CATEGORY_NAME"] = "SW Settle"
    env["APPLY_RULES"] = "false"
    env["REPORT_WEBHOOK"] = "https://hooks.example/x"
    env["MY_SPLITWISE_USER_ID"] = "100"
    env["BASE_CURRENCY"] = "gbp"
    s = Settings.from_env(env)
    assert s.settlement_category_name == "SW Settle"
    assert s.apply_rules is False
    assert s.report_webhook == "https://hooks.example/x"
    assert s.my_splitwise_user_id == 100
    assert s.base_currency == "GBP"
