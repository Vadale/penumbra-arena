"""`psh` — Penumbra shell coach CLI.

Concept taught: how a single CLI binds four pedagogical surfaces
(lessons, explain, suggest, interpret) behind one consistent verb
grammar — turning Unix-fluency practice into a single tool a learner
can `--help` their way through.

Usage
-----
    psh lessons               # list available lessons
    psh lesson <id>           # walk through a lesson interactively
    psh explain <command>...  # break down a command and its flags
    psh suggest <command>     # rule-based "what to try next"
    psh interpret "<stderr>"  # one-line fix hint for an error message
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from penumbra_shell_coach.error_helper import interpret as interpret_error
from penumbra_shell_coach.explain import explain as explain_command
from penumbra_shell_coach.runner import (
    LessonNotFoundError,
    check_step,
    list_lessons,
    load_lesson,
    shell_safe,
)
from penumbra_shell_coach.suggester import suggest as suggest_next

app = typer.Typer(help="Penumbra shell coach — curated macOS/Unix terminal tutor.")
console = Console()


@app.command()
def lessons() -> None:
    """List the bundled lessons."""
    table = Table(title="Penumbra shell-coach lessons")
    table.add_column("id", style="cyan")
    table.add_column("title")
    table.add_column("steps", justify="right")
    for lesson in list_lessons():
        table.add_row(lesson.id, lesson.title, str(len(lesson.steps)))
    console.print(table)


@app.command()
def lesson(lesson_id: str = typer.Argument(..., help="lesson id (e.g. 'filesystem')")) -> None:
    """Walk through a lesson step-by-step. Validates each step in-process."""
    try:
        lesson_obj = load_lesson(lesson_id)
    except LessonNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(Panel(f"[bold]{lesson_obj.title}[/bold]"))
    for i, step in enumerate(lesson_obj.steps, start=1):
        console.print(f"[cyan]Step {i}/{len(lesson_obj.steps)}[/cyan]: {step.instruction}")
        if not shell_safe(step.validate_cmd):
            console.print(f"[red]Refusing to run unsafe lesson step:[/red] {step.validate_cmd}")
            raise typer.Exit(code=2)
        result = check_step(step)
        if result.succeeded:
            console.print(f"  [green]✓[/green] {step.validate_cmd}")
        else:
            console.print(f"  [yellow]?[/yellow] {step.validate_cmd}")
            console.print(f"  [dim]hint:[/dim] {step.hint}")
            if result.error:
                console.print(f"  [dim red]err:[/dim red] {result.error.strip()[:200]}")


@app.command()
def explain(
    command: str = typer.Argument(..., help="the command to explain (quote it if multi-word)"),
) -> None:
    """Print a labelled breakdown of `command` and its flags.

    Quote multi-word commands so the shell does not strip the flags:
        psh explain 'ls -la'
    """
    result = explain_command(command)
    console.print(Panel(f"[bold]{result.binary}[/bold]"))
    for note in result.notes:
        console.print(f"  • {note}")


@app.command()
def suggest(command: str = typer.Argument(..., help="the command you just ran")) -> None:
    """Suggest the next useful commands given `command`."""
    hints = suggest_next(command)
    if not hints:
        console.print("[dim]No curated suggestions for that command yet.[/dim]")
        return
    for hint in hints:
        console.print(f"  → {hint}")


@app.command()
def interpret(stderr: str = typer.Argument(..., help="paste the stderr you got")) -> None:
    """One-line fix hint for a common error."""
    suggestion = interpret_error(stderr)
    style = "green" if suggestion.matched else "yellow"
    console.print(f"[{style}]{suggestion.hint}[/{style}]")


if __name__ == "__main__":
    app()
