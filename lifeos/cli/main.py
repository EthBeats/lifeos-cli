import typer
from rich.console import Console

app = typer.Typer(
    name="lifeos",
    help="Local Agentic LifeOS CLI",
    add_completion=False
)
console = Console()


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
