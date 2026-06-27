"""Render an ActionPlan to text and (optionally) POST it to a Slack/Discord webhook."""

from __future__ import annotations

import httpx

from swlm.drift import is_reconciled
from swlm.models import ActionPlan


def format_plan(plan: ActionPlan, *, dry_run: bool = False) -> str:
    lines: list[str] = []
    header = "DRY RUN — no writes performed" if dry_run else "Reconcile run"
    lines.append(f"=== {header} ===")

    if plan.txns:
        lines.append(f"\nLunch Money transactions ({len(plan.txns)}):")
        for t in plan.txns:
            verb = "REVERSE" if t.reverse else "upsert"
            cat = f" cat={t.category_id}" if t.category_id is not None else ""
            lines.append(
                f"  [{verb}] {t.external_id:<16} {t.signed_amount:>10} "
                f"asset={t.asset_id}{cat} :: {t.payee}"
            )
    else:
        lines.append("\nNo transactions to write.")

    if plan.drift is not None:
        status = "RECONCILED" if is_reconciled(plan.drift) else "DRIFT!"
        lines.append(
            f"\nClearing: expected={plan.expected_clearing} actual={plan.actual_clearing} "
            f"drift={plan.drift} [{status}]"
        )

    return "\n".join(lines)


def send_report(webhook: str, text: str) -> None:
    """POST to a webhook. Includes both Slack ('text') and Discord ('content') keys."""
    httpx.post(webhook, json={"text": text, "content": text}, timeout=15.0).raise_for_status()
