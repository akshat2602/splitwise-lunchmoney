"""Typer CLI: reconcile (with mandatory --dry-run), report, status."""

from __future__ import annotations

import typer

from swlm.config import Settings
from swlm.report import format_plan, send_report
from swlm.wiring import build_reconciler

app = typer.Typer(add_completion=False, help="Splitwise -> Lunch Money net-spend reconciler.")


@app.command()
def reconcile(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Read everything, write NOTHING. Print planned actions + drift."
    ),
    since: str | None = typer.Option(
        None, "--since", help="Override cursor: ISO8601 updated_after (e.g. 2026-01-01T00:00:00Z)."
    ),
    lookback_days: int | None = typer.Option(
        None, "--lookback-days", help="First-run look-back window when no cursor exists."
    ),
):
    """Reconcile Splitwise into the Lunch Money clearing account."""
    settings = Settings.from_env()
    if lookback_days is not None:
        settings.lookback_days = lookback_days

    reconciler, sw, state = build_reconciler(settings)
    try:
        plan = reconciler.run(dry_run=dry_run, since=since)
    finally:
        sw.close()
        state.close()

    typer.echo(format_plan(plan, dry_run=dry_run))


@app.command()
def report():
    """Recompute drift and send to REPORT_WEBHOOK (no writes)."""
    settings = Settings.from_env()
    reconciler, sw, state = build_reconciler(settings)
    try:
        plan = reconciler.run(dry_run=True)
    finally:
        sw.close()
        state.close()

    text = format_plan(plan, dry_run=True)
    typer.echo(text)
    if settings.report_webhook:
        send_report(settings.report_webhook, text)
        typer.echo("\n(report sent to webhook)")


@app.command()
def status():
    """Print the last run timestamp and the current cursor."""
    settings = Settings.from_env()
    from swlm.state import StateStore

    state = StateStore(settings.db_path)
    try:
        typer.echo(f"last_run: {state.get_last_run()}")
        typer.echo(f"cursor:   {state.get_cursor()}")
    finally:
        state.close()


if __name__ == "__main__":
    app()
