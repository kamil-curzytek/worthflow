import typer
from rich.console import Console
from rich.table import Table

from app.database.models import AccountType, AssetClass
from app.domain.accounts.schemas import AccountCreate
from app.services import accounts_service
from app.services.users_service import get_or_create_local_user
from cli._db import session_scope

app = typer.Typer(help="Manage accounts")
console = Console()


@app.command("list")
def list_accounts(include_inactive: bool = False):
    with session_scope() as db:
        accounts = accounts_service.list_accounts(db, include_inactive=include_inactive)
        table = Table(title="Accounts")
        for col in ("Name", "Type", "Asset class", "Currency", "Active"):
            table.add_column(col)
        for a in accounts:
            table.add_row(a.name, a.type, a.asset_class, a.currency, "yes" if a.is_active else "no")
        console.print(table)


@app.command("add")
def add_account(
    name: str,
    type: AccountType = typer.Option(...),
    asset_class: AssetClass = typer.Option(..., "--asset-class"),
    currency: str = typer.Option(...),
    institution: str = typer.Option(None),
):
    with session_scope() as db:
        user = get_or_create_local_user(db)
        payload = AccountCreate(
            name=name,
            type=type,
            asset_class=asset_class,
            currency=currency,
            institution=institution,
        )
        try:
            account = accounts_service.create_account(db, user.id, payload)
        except accounts_service.DuplicateAccountError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        console.print(f"[green]Created account {account.name} ({account.id})[/green]")


@app.command("deactivate")
def deactivate(account_id: str):
    with session_scope() as db:
        try:
            account = accounts_service.deactivate_account(db, account_id)
        except accounts_service.AccountNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        console.print(f"[yellow]Deactivated {account.name}[/yellow]")
