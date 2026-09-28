import typer
from rich.console import Console

from app.services.import_excel.importer import commit_import, preview_import
from app.services.users_service import get_or_create_local_user
from cli._db import session_scope

console = Console()


def import_file(
    file_path: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
    overwrite: bool = typer.Option(
        False, help="Overwrite existing snapshots for the same account/date"
    ),
):
    """Preview an Excel file's snapshots, then commit them after confirmation."""
    with session_scope() as db:
        user = get_or_create_local_user(db)
        preview = preview_import(db, user.id, file_path)

        console.print(f"[bold]Import preview for {file_path}[/bold]")
        console.print(f"  New snapshots: {preview.new_snapshot_count}")
        console.print(
            f"  Duplicates (skipped unless --overwrite): {preview.duplicate_count}"
        )
        if preview.new_account_names:
            console.print(f"  New accounts to create: {', '.join(preview.new_account_names)}")
        for warning in preview.warnings:
            console.print(f"  [yellow]Warning:[/yellow] {warning}")

        if preview.new_snapshot_count == 0 and not overwrite:
            console.print("[yellow]Nothing to import.[/yellow]")
            raise typer.Exit(0)

        if not yes and not typer.confirm("Proceed with import?"):
            console.print("Aborted.")
            raise typer.Exit(0)

        batch = commit_import(db, user.id, file_path, overwrite_duplicates=overwrite)
        console.print(f"[green]Imported {batch.row_count} snapshots (batch {batch.id}).[/green]")
