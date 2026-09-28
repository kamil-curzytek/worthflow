import datetime as dt
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table

from app.services import accounts_service, snapshots_service
from app.services.users_service import get_or_create_local_user
from cli._db import session_scope

app = typer.Typer(help="Manage snapshots (monthly balance updates)")
console = Console()


@app.command("add")
def add_snapshot(
    account_name: str,
    value: str,
    date: dt.datetime = typer.Option(None, formats=["%Y-%m-%d"]),
    note: str = typer.Option(None),
):
    snapshot_date = date.date() if date else dt.date.today()
    try:
        decimal_value = Decimal(value)
    except Exception as exc:
        console.print(f"[red]{value!r} is not a valid number: {exc}[/red]")
        raise typer.Exit(1) from exc

    with session_scope() as db:
        user = get_or_create_local_user(db)
        account = accounts_service.get_account_by_name(db, user.id, account_name)
        if account is None:
            console.print(
                f"[red]No account named {account_name!r}. Use 'finance accounts add' first.[/red]"
            )
            raise typer.Exit(1)
        snapshot = snapshots_service.add_or_update_monthly_snapshot(
            db, account=account, snapshot_date=snapshot_date, value=decimal_value, note=note
        )
        console.print(
            f"[green]{account.name} @ {snapshot.snapshot_date}: "
            f"{snapshot.value} {snapshot.currency}[/green]"
        )


@app.command("list")
def list_snapshots(account_name: str = typer.Option(None)):
    with session_scope() as db:
        account_id = None
        if account_name:
            user = get_or_create_local_user(db)
            account = accounts_service.get_account_by_name(db, user.id, account_name)
            if account is None:
                console.print(f"[red]No account named {account_name!r}[/red]")
                raise typer.Exit(1)
            account_id = account.id

        rows = snapshots_service.list_snapshots(db, account_id=account_id)
        table = Table(title="Snapshots")
        for col in ("Date", "Account", "Value", "Currency"):
            table.add_column(col)
        for s in rows:
            table.add_row(str(s.snapshot_date), s.account.name, str(s.value), s.currency)
        console.print(table)
