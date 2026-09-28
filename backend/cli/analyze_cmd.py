import datetime as dt

import typer
from rich.console import Console

from app.config import get_settings
from app.services.calculations import portfolio as calc
from app.services.calculations.trends import (
    average_monthly_change,
    cumulative_growth,
    historical_high_low,
)
from app.services.exchange_rates.factory import build_exchange_rate_service
from cli._db import session_scope

console = Console()


def analyze(
    currency: str = typer.Option(None),
    months: int = typer.Option(12, help="How many months back to analyze"),
):
    """Deterministic trend summary. Not AI narrative analysis (see AI_ANALYSIS_ENABLED)."""
    settings = get_settings()
    display_currency = currency or settings.default_display_currency
    with session_scope() as db:
        fx = build_exchange_rate_service(db)
        end = calc.latest_snapshot_date(db)
        if end is None:
            console.print("[yellow]No snapshots yet — nothing to analyze.[/yellow]")
            raise typer.Exit(0)
        start = end - dt.timedelta(days=30 * months)

        series = calc.portfolio_trend(db, fx, display_currency, start=start, end=end)
        if len(series) < 2:
            console.print(
                "[yellow]Not enough history yet for a trend (need at least 2 months).[/yellow]"
            )
            raise typer.Exit(0)

        growth = cumulative_growth(series)
        avg = average_monthly_change(series)
        high_low = historical_high_low(series)
        assert high_low is not None  # series has >=2 points, checked above
        high, low = high_low

        console.print(
            f"[bold]Portfolio analysis ({display_currency}, "
            f"{series[0].date} -> {series[-1].date})[/bold]"
        )
        console.print(f"  Current: {series[-1].value}")
        if growth and growth.percentage is not None:
            console.print(f"  Change over period: {growth.absolute} ({growth.percentage:.2f}%)")
        elif growth:
            console.print(f"  Change over period: {growth.absolute}")
        if avg is not None:
            console.print(f"  Average monthly change: {avg:.2f}")
        else:
            console.print("  Average monthly change: n/a")
        console.print(f"  High: {high.value} on {high.date}")
        console.print(f"  Low: {low.value} on {low.date}")
        console.print(
            "\n[dim]Deterministic calculation output. AI narrative analysis is not yet "
            "enabled (see AI_ANALYSIS_ENABLED in .env).[/dim]"
        )
