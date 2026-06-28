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
# optional: SETTLEMENT_CATEGORY_NAME (default "Splitwise Settlement"),
#           BASE_CURRENCY (default USD, must match the clearing asset), APPLY_RULES (default true)
set -a; source .env; set +a
```

The env file is not auto-loaded — `source` it (as above) before running, or export the vars.

## 5. Dry run first (mandatory)

```bash
uv run swlm reconcile --dry-run
```

Read the output carefully:

- **Signs**: an expense you fronted shows a **negative** clearing amount; one you owe (or a
  friend paid) shows a **positive** clearing amount.
- **external_id**s look like `sw:<expense_id>:clear` (one per item).
- **Projected drift** is printed at the bottom.

Re-run it — output must be identical every time (dry-run writes nothing). Only proceed when the
signs look right.

> Each run is a full resync over all history, so the first real run may write hundreds of
> transactions (and zero out anything mis-posted). Only `BASE_CURRENCY` expenses are posted.

## 6. First real run

```bash
uv run swlm reconcile
uv run swlm report     # drift should read ~0 [RECONCILED]
```

`actual` is the sum of the offsets the tool has posted; `expected` is `-net` from your
Splitwise friend balances. Once the full history is mirrored they match and drift is ~0. Any
later nonzero drift is a real signal (e.g. an expense you haven't recorded a settlement for).

## 7. Automate

GitHub Actions: add every `.env` key as a repo **Secret**, then the workflow in
`.github/workflows/cron.yml` runs `reconcile` every 6h + Monday `report`. Each run is a full
self-cleaning resync (Lunch Money is the source of truth), so there is no state to persist and
nothing to corrupt — a VPS is optional.
