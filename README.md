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

### Sign convention (the crux)

Positive = **debit** (spend / money out); negative = **credit**. Defined in exactly one place
(`lunchmoney_client.to_lm_amount`, always called with `debit_as_negative=False`). Because every
item shares this one convention, if the clearing *balance* ever moves the wrong way it's a
single global flip — verify with `reconcile --dry-run` and a first real txn before trusting it.

### Drift check

`net = sum(get_friends balances)`, `expected_clearing = −net`,
`drift = actual_clearing − expected_clearing` (within a 1¢ epsilon). ~0 = reconciled.

## Idempotency & crash-resilience

**Lunch Money is the source of truth — correctness never depends on local state.** Every
tool-created txn has a deterministic `external_id` (`sw:<id>:clear`). On each run the tool
rebuilds the `external_id → txn_id` map *directly from Lunch Money* (over a window covering
every affected item's date) and upserts against it: present → update in place, absent →
insert. So:

- A **crash mid-run**, a **lost/corrupt cache**, or a **missed cursor advance** all self-heal on
  the next run — no duplicates, no desync.
- The cursor advances **only after** a successful apply.
- Edits (`updated_at` moved) and deletions (`deleted_at` → reverse the existing txn to 0) are
  caught via Splitwise's `updated_after`. Settle-up payments post their own offset.
- The local SQLite file holds **only the cursor + last-run timestamp** — a pure optimization.
  Delete it and the next run just re-scans a wider window.
- The **drift check** is the final backstop for anything slipping past the cursor.

## Install & run

```bash
uv sync
cp .env.example .env   # fill in, then: set -a; source .env; set +a

uv run swlm reconcile --dry-run   # read everything, write NOTHING — do this first
uv run swlm reconcile             # real run
uv run swlm report                # recompute drift -> REPORT_WEBHOOK
uv run swlm status                # last run + cursor
```

`reconcile` flags: `--dry-run`, `--since <ISO8601>`, `--lookback-days <N>`.

**Always `--dry-run` first** to eyeball signs, amounts, external_ids, and projected drift.
See [SETUP.md](SETUP.md) for the exact account/category creation and first-run flow.

## Running on a schedule

- **GitHub Actions** (`.github/workflows/cron.yml`): `reconcile` every 6h, Monday `report`, plus a
  manual `workflow_dispatch` (defaults to dry-run). Config comes from repo **Secrets** (same
  names as `.env`). The cursor cache rides `actions/cache` purely as a speed optimization — if
  it's ever evicted, correctness is unaffected (the next run just re-scans `--lookback-days`).
- **VPS** (optional, only to avoid re-scans): clone, `uv sync`, put the env vars in the
  environment, point `SWLM_DB_PATH` at a persistent path, and add cron lines:
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
