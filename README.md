# swlm — Splitwise → Lunch Money net-spend reconciler

Keeps your Lunch Money spending reports showing what you **actually** spent by treating
Splitwise as an A/R–A/P ledger and reconciling it into one virtual **Splitwise Clearing**
asset. Built for the case where you front uneven group expenses and settle later in lump-sum
transfers — so reconciliation is **balance-based**, never per-transaction matching.

## The model — a single-offset loan ledger

One manual Lunch Money asset, **`Splitwise Clearing`**, is the only account this tool writes
to. Your Plaid `Credit Cards` / `Checking` are **never** touched. Splitwise Clearing acts as a
loan ledger: it tracks what you're net owed / owe, and walks back to ~0 as people settle.

**Core principle:** every Splitwise item (expense *or* settle-up payment) posts **exactly one**
clearing transaction of `clear_offset = −my_net`. Summed over everything that equals `−net`
(your Splitwise position), so the clearing balance mirrors the loan **by construction** and
drift is ~0. Any nonzero **drift** is the alert signal.

`my_net = my_paid_share − my_owed_share`:

| Item | One clearing txn | Category | Counts as spend? |
|------|------------------|----------|-------------------|
| You fronted (`my_net > 0`) | `−my_net` (credit) | none | yes — claws back the over-charge on your card |
| You owe (`my_net < 0`, no card txn) | `−my_net` (debit) | left for **LM rules** (`APPLY_RULES`) | yes — your real consumption |
| Settle-up **payment** | `−my_net` | excluded `Splitwise Settlement` | no — just moves the loan balance |
| Even split (`my_net == 0`) | — | — | — |

The real Zelle/Venmo lands in Checking and is left alone — a separate account. There is **no**
transfer-scanning, no `KNOWN_PAYEES`: the clearing balance stays correct purely from Splitwise.
When a friend settles, record it in Splitwise (the tool posts the offset) and categorize the
incoming Zelle in Checking to the excluded `Splitwise Settlement` category so it isn't income.

Only expenses in `BASE_CURRENCY` (default USD, must match the clearing asset) are posted;
Splitwise expenses in any other currency are ignored.

### Sign convention (the crux)

Positive = **debit** (spend / money out); negative = **credit**. Defined in exactly one place
(`lunchmoney_client.to_lm_amount`, always called with `debit_as_negative=False`). Because every
item shares this one convention, if the clearing *balance* ever moves the wrong way it's a
single global flip — verify with `reconcile --dry-run` and a first real txn before trusting it.

### Drift check

`net = sum(get_friends balances)`, `expected_clearing = −net`,
`drift = actual_clearing − expected_clearing` (within a 1¢ epsilon). ~0 = reconciled.

## Idempotency, crash-resilience & self-cleaning

**Lunch Money is the source of truth — correctness never depends on local state.** Each run is
a full **resync**: fetch *all* Splitwise expenses, compute the complete set of desired offsets
(deterministic `external_id` = `sw:<id>:clear`, base-currency items only), and reconcile Lunch
Money to match it **exactly**:

- desired offset missing in LM → **insert**
- present with a different amount → **update in place**
- present and already correct → **skip** (steady-state runs write nothing → no rate-limit churn)
- managed txn with no desired offset → **zero it out** (deleted, settled-to-even, wrong
  currency, or anything previously mis-posted)

So a **crash mid-run**, a **lost/corrupt cache**, a **duplicate**, or **orphaned/garbage txns**
all self-heal on the next run. The local SQLite file holds only the last-run timestamp — pure
cosmetics, safe to delete. The **drift check** is the final backstop. Reads are paginated
fully; inserts are batched (≤100/request) and every Lunch Money call retries 429 with backoff.

## Install & run

```bash
uv sync
cp .env.example .env   # fill in, then: set -a; source .env; set +a

uv run swlm reconcile --dry-run   # read everything, write NOTHING — do this first
uv run swlm reconcile             # real run (full resync)
uv run swlm report                # recompute drift -> REPORT_WEBHOOK
uv run swlm status                # last run timestamp
```

`reconcile` takes only `--dry-run`. **Always `--dry-run` first** to eyeball signs, amounts,
external_ids, and projected drift. See [SETUP.md](SETUP.md) for account/category creation and
the first-run flow.

## Running on a schedule

- **GitHub Actions** (`.github/workflows/cron.yml`): `reconcile` every 6h, Monday `report`, plus a
  manual `workflow_dispatch` (defaults to dry-run). Config comes from repo **Secrets** (same
  names as `.env`). No state to persist — every run is a full resync — so the `actions/cache`
  step is purely cosmetic.
- **VPS** (optional): clone, `uv sync`, put the env vars in the environment, and add cron lines:
  ```cron
  0 */6 * * *  cd /opt/swlm && uv run swlm reconcile
  0 9 * * 1    cd /opt/swlm && uv run swlm report
  ```

## Development

```bash
uv run pytest          # unit tests, no live API
uv run ruff check src tests
uv run ty check src
```
