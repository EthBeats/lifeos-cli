import sys
from datetime import date, datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from lifeos.config import settings

app = typer.Typer(
    name="lifeos",
    help="🤖 Local Agentic LifeOS CLI",
    add_completion=False,
)
console = Console()

@app.command()
def log_daily(
    entry: str = typer.Argument(..., help="Text entry to append to today's daily note"),
    heading: Optional[str] = typer.Option(
        "Agent Sync Log", "--heading", "-h", help="Optional Markdown H2 section heading"
    ),
):
    """Append a quick log or note entry to today's Obsidian Daily Note."""
    from lifeos.integrations.obsidian import ObsidianVaultManager

    if not settings.obsidian_vault_path:
        console.print(
            "[bold red]Error:[/bold red] No Obsidian Vault path set.\n"
            "Please configure `OBSIDIAN_VAULT_PATH=/path/to/vault` in your `.env` file."
        )
        raise typer.Exit(code=1)

    try:
        obsidian = ObsidianVaultManager(vault_path=settings.obsidian_vault_path)
        note_path = obsidian.append_to_daily_note(
            content=entry, section_heading=heading
        )
        console.print(
            f"[bold green]✓ Updated Daily Note:[/bold green] [cyan]{note_path}[/cyan]"
        )
    except Exception as e:
        console.print(f"[bold red]Failed to write to Obsidian Vault:[/bold red] {e}")
        raise typer.Exit(code=1)

@app.command()
def check_canvas(
    days: int = typer.Option(14, "--days", "-d", help="Lookahead window in days"),
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="Canvas iCal URL override"
    ),
):
    """Fetch and render upcoming Canvas LMS assignments."""
    from lifeos.integrations.canvas import CanvasICalParser

    target_url = url or settings.canvas_ical_url
    if not target_url:
        console.print(
            "[bold red]Error:[/bold red] No Canvas iCal URL found.\n"
            "Please add `CANVAS_ICAL_URL=...` to your `.env` file or pass `--url`."
        )
        raise typer.Exit(code=1)

    console.print(f"[yellow]Fetching Canvas feed (next {days} days)...[/yellow]")
    parser = CanvasICalParser(ical_url=target_url)

    try:
        assignments = parser.get_upcoming_assignments(days_ahead=days)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch or parse Canvas feed:[/bold red] {e}")
        raise typer.Exit(code=1)

    if not assignments:
        console.print("[green]No upcoming assignments found in this window! 🎉[/green]")
        return

    table = Table(
        title=f"Canvas Assignments (Next {days} Days)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Course", style="magenta")
    table.add_column("Assignment", style="bold white")
    table.add_column("Due Date", style="green")

    for item in assignments:
        due_str = item.due_date.strftime("%b %d, %Y %I:%M %p")
        table.add_row(item.course_name, item.title, due_str)

    console.print(table)


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
