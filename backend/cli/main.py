import typer

from cli import accounts_cmd, analyze_cmd, imports_cmd, rates_cmd, snapshots_cmd, status_cmd

app = typer.Typer(help="Worthflow — local-first personal finance CLI")
app.add_typer(accounts_cmd.app, name="accounts")
app.add_typer(snapshots_cmd.app, name="snapshot")
app.command("import")(imports_cmd.import_file)
app.command("rates")(rates_cmd.update_rates)
app.command("status")(status_cmd.status)
app.command("analyze")(analyze_cmd.analyze)


if __name__ == "__main__":
    app()
