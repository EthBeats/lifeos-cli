import sys
from datetime import date, datetime
from typing import Optional

import typer
from rich.console import Console, Group
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel

from lifeos.config import settings

app = typer.Typer(
    name="lifeos",
    help="🤖 Local Agentic LifeOS CLI",
    add_completion=False,
)
console = Console()


# -----------------------------------------------------------------------------
# Streaming UI Helper Function (Top Level)
# -----------------------------------------------------------------------------
def render_streaming_response(token_generator) -> str:
    """Parse streamed tokens live, rendering <think> blocks in real-time."""
    full_text = ""

    console.print("[dim cyan]⚡ Streaming agent response...[/dim cyan]\n")

    with Live(console=console, refresh_per_second=10, vertical_overflow="visible") as live:
        for token in token_generator:
            full_text += token

            think_text = ""
            answer_text = ""

            if "<think>" in full_text:
                if "</think>" in full_text:
                    parts = full_text.split("</think>", 1)
                    think_text = parts[0].replace("<think>", "").strip()
                    answer_text = parts[1].lstrip()
                else:
                    parts = full_text.split("<think>", 1)
                    think_text = parts[1].strip()
            else:
                answer_text = full_text

            display_parts = []
            if think_text:
                display_parts.append(
                    Panel(
                        f"[dim italic]{think_text}[/dim italic]",
                        title="💭 Agent Reasoning (Thinking)",
                        border_style="dim white",
                    )
                )
            if answer_text:
                display_parts.append(Markdown(answer_text))

            if display_parts:
                # Group multiple renderables into a single renderable container
                live.update(Group(*display_parts))

    return full_text


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

@app.command()
def daily(
    sync_obsidian: bool = typer.Option(
        True,
        "--sync/--no-sync",
        help="Automatically append the briefing to today's Obsidian Daily Note",
    ),
):
    """Run the Agent to synthesize today's schedule, tasks, and Canvas deliverables."""
    from lifeos.agents.synthesizer import DailySynthesizerAgent

    agent = DailySynthesizerAgent()

    if not agent.ollama.is_available():
        console.print(
            f"[bold red]Ollama Offline:[/bold red] Could not connect to Ollama at `{agent.ollama.base_url}`.\n"
            "Ensure Ollama is running (`ollama serve`)."
        )
        raise typer.Exit(code=1)

    console.print(
        f"[yellow]🤖 Agent synthesizing daily overview using local model ({agent.ollama.model})...[/yellow]\n"
    )

    try:
        token_stream = agent.synthesize_daily_plan_stream()
        plan_markdown = render_streaming_response(token_stream)
    except Exception as e:
        console.print(f"[bold red]Agent Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Clean stripped markdown (removing think block tags) for Obsidian sync
    clean_markdown = plan_markdown
    if "</think>" in clean_markdown:
        clean_markdown = clean_markdown.split("</think>")[-1].strip()

    if sync_obsidian and settings.obsidian_vault_path:
        try:
            from lifeos.integrations.obsidian import ObsidianVaultManager

            obsidian = ObsidianVaultManager(vault_path=settings.obsidian_vault_path)
            note_path = obsidian.append_to_daily_note(
                content=clean_markdown, section_heading="🤖 AI Agent Daily Briefing"
            )
            console.print(
                f"\n[bold green]✓ Synced briefing to Obsidian Daily Note:[/bold green] [cyan]{note_path}[/cyan]"
            )
        except Exception as e:
            console.print(f"\n[bold yellow]Warning (Obsidian Sync):[/bold yellow] {e}")


@app.command()
def plan(
    days: int = typer.Option(
        7, "--days", "-d", help="Planning lookahead horizon in days (e.g. 7 or 14)"
    ),
    sync_obsidian: bool = typer.Option(
        True,
        "--sync/--no-sync",
        help="Write strategy document to Obsidian Vault under Weekly Plans/",
    ),
):
    """Run the Agent to generate a multi-day strategic plan and milestone breakdown."""
    from lifeos.agents.planner import WeeklyPlannerAgent

    planner = WeeklyPlannerAgent()

    if not planner.ollama.is_available():
        console.print(
            f"[bold red]Ollama Offline:[/bold red] Could not connect to Ollama at `{planner.ollama.base_url}`.\n"
            "Ensure Ollama is running (`ollama serve`)."
        )
        raise typer.Exit(code=1)

    console.print(
        f"[yellow]🤖 Agent generating {days}-day strategic plan with model ({planner.ollama.model})...[/yellow]\n"
    )

    try:
        token_stream = planner.generate_weekly_plan_stream(days_ahead=days)
        plan_markdown = render_streaming_response(token_stream)
    except Exception as e:
        console.print(f"[bold red]Planning Agent Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Clean stripped markdown for Obsidian sync
    clean_markdown = plan_markdown
    if "</think>" in clean_markdown:
        clean_markdown = clean_markdown.split("</think>")[-1].strip()

    if sync_obsidian and settings.obsidian_vault_path:
        try:
            from lifeos.integrations.obsidian import ObsidianVaultManager

            obsidian = ObsidianVaultManager(vault_path=settings.obsidian_vault_path)

            now = datetime.now()
            year, week_num, _ = now.isocalendar()
            rel_path = f"Weekly Plans/{year}-W{week_num:02d}.md"
            title = f"Weekly Plan - {year} Week {week_num:02d}"

            saved_path = obsidian.create_or_update_note(
                relative_path=rel_path,
                title=title,
                body=clean_markdown,
                frontmatter={
                    "type": "weekly-plan",
                    "week": f"{year}-W{week_num:02d}",
                    "generated_by": planner.ollama.model,
                },
            )
            console.print(
                f"\n[bold green]✓ Weekly strategy saved to Obsidian:[/bold green] [cyan]{saved_path}[/cyan]"
            )
        except Exception as e:
            console.print(f"\n[bold yellow]Warning (Obsidian Sync):[/bold yellow] {e}")


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

    reminders = bridge.fetch_reminders(calendar_name=list_name)

    if not reminders:
        console.print("[yellow]No pending reminders found![/yellow]")
        return

    sorted_reminders = sorted(
        reminders,
        key=lambda r: r.due_date if r.due_date is not None else datetime.max,
    )

    table = Table(
        title=f"Apple Reminders {'(' + list_name + ')' if list_name else ''}",
        show_header=True,
        header_style="bold magenta",
    )
    # table.add_column("Status", justify="center", style="bold")
    table.add_column("Title", style="cyan", no_wrap=False)
    table.add_column("List", style="blue")
    table.add_column("Due Date", style="green")

    now = datetime.now()
    today = date.today()

    for r in sorted_reminders:
        if r.due_date:
            # Format date string based on whether a specific time was set
            if r.has_time:
                due_str = r.due_date.strftime("%b %d, %Y %I:%M %p")
            else:
                due_str = r.due_date.strftime("%b %d, %Y") + " (End of Day)"

            # Determine urgency styling
            if r.due_date < now:
                status = "[red]🚨 OVERDUE[/red]"
                due_fmt = f"[bold red]{due_str}[/bold red]"
            elif r.due_date.date() == today:
                status = "[yellow]⚠️ TODAY[/yellow]"
                due_fmt = f"[bold yellow]{due_str}[/bold yellow]"
            else:
                status = "[green]📅 UPCOMING[/green]"
                due_fmt = f"[green]{due_str}[/green]"
        else:
            status = "[dim]📌 NO DUE DATE[/dim]"
            due_fmt = "[dim]None[/dim]"

        table.add_row(r.title, r.calendar_name, due_fmt)

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
