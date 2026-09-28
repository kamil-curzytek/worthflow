import datetime as dt

from rich.console import Console

from app.config import get_settings
from app.services import accounts_service
from app.services.calculations import portfolio as calc
from app.services.exchange_rates.factory import build_exchange_rate_service
from app.services.exchange_rates.service import ExchangeRateUnavailableError
from cli._db import session_scope

console = Console()


def status():
    """A quick snapshot of where things stand."""
    settings = get_settings()
    with session_scope() as db:
        accounts = accounts_service.list_accounts(db, include_inactive=False)
        fx = build_exchange_rate_service(db)
        as_of = dt.date.today()
        currency = settings.default_display_currency
        try:
            total = calc.portfolio_value_as_of(db, fx, currency, as_of)
            total_str = f"{total} {currency}"
        except ExchangeRateUnavailableError as exc:
            total_str = f"unavailable ({exc})"

        latest = calc.latest_snapshot_date(db)

        console.print("[bold]Worthflow status[/bold]")
        console.print(f"  Active accounts: {len(accounts)}")
        console.print(f"  Latest snapshot date: {latest or 'none yet'}")
        console.print(f"  Portfolio value (as of {as_of}): {total_str}")
