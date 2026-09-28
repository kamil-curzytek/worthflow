import datetime as dt

import typer
from rich.console import Console

from app.domain.currencies.currency import SUPPORTED_CURRENCIES
from app.services.exchange_rates.factory import build_exchange_rate_service
from app.services.exchange_rates.service import ExchangeRateUnavailableError
from cli._db import session_scope

console = Console()


def update_rates(on_date: dt.datetime = typer.Option(None, formats=["%Y-%m-%d"])):
    """Fetch (and cache) rates between all supported currencies for a date."""
    as_of = on_date.date() if on_date else dt.date.today()
    with session_scope() as db:
        fx = build_exchange_rate_service(db)
        currencies = sorted(SUPPORTED_CURRENCIES)
        for base in currencies:
            for quote in currencies:
                if base == quote:
                    continue
                try:
                    lookup = fx.get_rate_with_metadata(base, quote, as_of)
                    if lookup.is_stale_fallback:
                        console.print(
                            f"  [yellow]{base}->{quote}: live fetch failed, using cached "
                            f"rate from {lookup.rate_date}: {lookup.rate}[/yellow]"
                        )
                    else:
                        console.print(f"  {base}->{quote} on {as_of}: {lookup.rate}")
                except ExchangeRateUnavailableError as exc:
                    console.print(f"  [red]{base}->{quote}: {exc}[/red]")
