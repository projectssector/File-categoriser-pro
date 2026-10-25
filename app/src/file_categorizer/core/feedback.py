"""Flash-card review loop for low-confidence predictions."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from .db import Database
from .hasher import hash_file

console = Console()


def review_queue(
    entries: list[dict],
    db: Database,
    dry_run: bool = False,
) -> None:
    for entry in entries:
        console.rule(f"[bold]{entry['path']}")
        console.print(f"Guessed: [cyan]{entry.get('tag')}[/cyan] "
                      f"({entry.get('confidence', 0):.0%}) via {entry.get('model')}")

        choice = Prompt.ask(
            "Correct?", choices=["y", "n", "s", "q"], default="y"
        )
        if choice == "q":
            break
        if choice == "s":
            continue
        if choice == "y":
            continue
        if choice == "n":
            right = Prompt.ask("Correct tag")
            file_hash = hash_file(entry["path"], fast=True)
            db.add_correction(file_hash, entry.get("tag"), right)
            console.print(f"[green]Saved correction: {entry.get('tag')} → {right}[/green]")