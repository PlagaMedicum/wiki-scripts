from __future__ import annotations

import difflib
from functools import lru_cache

from rich.console import Console
from rich.markup import escape
from rich.syntax import Syntax


def generate_unified_diff(original: str, proposed: str, title: str = "page") -> str:
    """Generate standard unified diff between original and proposed content."""
    original_lines = original.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        proposed_lines,
        fromfile=f"a/{title}",
        tofile=f"b/{title}",
    )
    return "".join(diff)


@lru_cache(maxsize=64)
def compute_diff_stats(original: str, proposed: str) -> tuple[int, int]:
    """Calculate the number of added and removed lines in the diff.

    Cached by content: TUI frames recompute badges from unchanged texts.

    Returns:
        tuple[int, int]: (added_lines, removed_lines)
    """
    diff_text = generate_unified_diff(original, proposed)
    added = 0
    removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def print_diff(console: Console, original: str, proposed: str, title: str = "page") -> None:
    """Print colorized unified diff to the Rich console."""
    diff_text = generate_unified_diff(original, proposed, title)
    if not diff_text.strip():
        console.print("[dim italic](No changes between original and proposed content)[/dim italic]")
        return

    syntax = Syntax(diff_text, "diff", background_color="default", word_wrap=True)
    console.print(syntax)


def format_diff_lines(original: str, proposed: str, title: str = "page") -> list[str]:
    """Generate unified diff formatted as a list of styled Rich markup lines."""
    diff_text = generate_unified_diff(original, proposed, title)
    if not diff_text.strip():
        return ["[dim italic](No changes between original and proposed content)[/dim italic]"]

    lines: list[str] = []
    for line in diff_text.splitlines():
        esc = escape(line)
        if line.startswith("---") or line.startswith("+++"):
            lines.append(f"[bold white]{esc}[/bold white]")
        elif line.startswith("@@"):
            lines.append(f"[bold cyan]{esc}[/bold cyan]")
        elif line.startswith("+"):
            lines.append(f"[bold green]{esc}[/bold green]")
        elif line.startswith("-"):
            lines.append(f"[bold red]{esc}[/bold red]")
        else:
            lines.append(esc)
    return lines
