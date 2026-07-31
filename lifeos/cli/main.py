import sys
from datetime import date, datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="lifeos",
    help="🤖 Local Agentic LifeOS CLI",
    add_completion=False,
)
console = Console()


@app.command()
def check_reminders(
    list_name: Optional[str] = typer.Option(
        None, "--list", "-l", help="Filter by specific Reminder list name"
    ),
):
    """View active Apple Reminders sorted by due date with urgency highlights."""
    if sys.platform != "darwin":
        console.print("[red]Error: Apple Reminders integration requires macOS.[/red]")
        raise typer.Exit(code=1)

    from lifeos.integrations.apple_eventkit import EventKitBridge

    bridge = EventKitBridge()

    if not bridge.request_permissions(entity_type="reminder"):
        console.print("[bold red]Access denied by macOS system settings.[/bold red]")
        raise typer.Exit(code=1)

    # 1. Fetch reminders
    reminders = bridge.fetch_reminders(calendar_name=list_name)

    if not reminders:
        console.print("[yellow]No pending reminders found![/yellow]")
        return

    # 2. Sort chronologically (Undated tasks pushed to the bottom using datetime.max)
    sorted_reminders = sorted(
        reminders, key=lambda r: r.due_date if r.due_date is not None else datetime.max
    )

    # 3. Render Rich Table
    table = Table(
        title=f"Apple Reminders {'(' + list_name + ')' if list_name else ''}",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Title", style="cyan", no_wrap=False)
    table.add_column("List", style="blue")
    table.add_column("Due Date", style="black")

    now = datetime.now()
    today = date.today()

    for r in sorted_reminders:
        if r.due_date:
            due_str = r.due_date.strftime("%F %R")

            # Determine urgency styling
            if r.due_date < now:
                due_fmt = f"[bold red]{due_str}[/bold red]"
            elif r.due_date.date() == today:
                due_fmt = f"[bold yellow]{due_str}[/bold yellow]"
            else:
                due_fmt = f"[green]{due_str}[/green]"
        else:
            due_fmt = "[dim]None[/dim]"

        table.add_row(
            r.title,
            r.calendar_name,
            due_fmt,
        )

    console.print(table)


@app.command()
def overview():
    """Display daily overview dashboard."""
    console.print(
        "[bold green]LifeOS Active[/bold green] - Daily overview coming soon!"
    )


@app.command()
def version():
    """Show current version."""
    console.print("[bold blue]LifeOS CLI[/bold blue] v0.1.0")


if __name__ == "__main__":
    app()
