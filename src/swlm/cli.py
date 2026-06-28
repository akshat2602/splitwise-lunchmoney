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
):
    """Reconcile Splitwise into the Lunch Money clearing account (full self-cleaning resync)."""
    settings = Settings.from_env()
    reconciler, sw, state = build_reconciler(settings)
    try:
        plan = reconciler.run(dry_run=dry_run)
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
    """Print the last run timestamp."""
    settings = Settings.from_env()
    from swlm.state import StateStore

    state = StateStore(settings.db_path)
    try:
        typer.echo(f"last_run: {state.get_last_run()}")
    finally:
        state.close()


if __name__ == "__main__":
    app()
