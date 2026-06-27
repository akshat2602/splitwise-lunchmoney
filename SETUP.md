# SETUP

One-time setup, then the dry-run-first flow. Do these in order.

## 1. Lunch Money: create the clearing asset

1. Settings → **Assets** → add asset.
2. Type **Cash**, name it exactly **`Splitwise Clearing`**, starting balance **0**, currency
   USD. This is the only account the tool writes into.
3. Note its **asset id** (visible in the URL when editing the asset, or via
   `uv run python -c "from lunchable import LunchMoney; [print(a.id, a.name) for a in LunchMoney(access_token='...').get_assets()]"`).
   → `LM_CLEARING_ASSET_ID`.
4. Make sure this asset is **included** in spending totals (it carries your real net spend).

## 2. Lunch Money: settlement category

Create one category named exactly **`Splitwise Settlement`** and mark it **Exclude from
totals** (and exclude from budget). Settle-up payment offsets are tagged here so repayments
move the loan balance without counting as spend. (Name configurable via
`SETTLEMENT_CATEGORY_NAME`.) Everything you *owe* is left uncategorized and your existing Lunch
Money **rules** categorize it at insert (`APPLY_RULES=true`).

## 3. API tokens

- **Lunch Money**: Settings → Developers → request an access token → `LUNCHMONEY_ACCESS_TOKEN`.
- **Splitwise**: <https://secure.splitwise.com/apps> → register an app → copy the personal
  **API key** → `SPLITWISE_API_KEY`. (The API key alone is enough for this single-user tool.)

## 4. Config

```bash
cp .env.example .env
# required: SPLITWISE_API_KEY, LUNCHMONEY_ACCESS_TOKEN, LM_CLEARING_ASSET_ID
# optional: SETTLEMENT_CATEGORY_NAME (default "Splitwise Settlement"), APPLY_RULES (default true)
set -a; source .env; set +a
```

## 5. Dry run first (mandatory)

```bash
uv run swlm reconcile --dry-run
```

Read the output carefully:

- **Signs**: an expense you fronted shows a **negative** clearing amount; one you owe (or a
  friend paid) shows a **positive** clearing amount.
- **external_id**s look like `sw:<expense_id>:clear` (one per item).
- **Projected drift** is printed at the bottom.

Re-run it — output must be identical every time (dry-run writes nothing: no LM, no SQLite, no
cursor advance). Only proceed when the signs look right.

## 6. First real run + absorb history

```bash
uv run swlm reconcile
```

Then reconcile the opening balance **once**: check `report`/`status` drift, and edit the
`Splitwise Clearing` asset's starting balance by that drift so it reads ~0. This absorbs all
historical settlements that happened before the tool existed. After this, drift should stay
near 0 and any future nonzero drift is a real signal.

> First run with no cursor only looks back `FIRST_RUN_LOOKBACK_DAYS` (default 90), not all
> history — keep that in mind when absorbing the opening balance.

## 7. Automate

GitHub Actions: add every `.env` key as a repo **Secret**, then the workflow in
`.github/workflows/cron.yml` runs `reconcile` every 6h + Monday `report`. State is just a
cursor cache (Lunch Money is the source of truth), so losing it never causes duplicates — a
VPS is optional and only avoids occasional wider re-scans.
