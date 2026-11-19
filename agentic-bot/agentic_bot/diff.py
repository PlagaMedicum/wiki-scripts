from __future__ import annotations

import difflib
import re
from functools import lru_cache
from itertools import zip_longest

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


def _inline_change(original: str, proposed: str) -> str:
    """Preserve shared text once; distinguish removed/added Unicode word tokens."""
    before = re.findall(r"\w+|\s+|[^\w\s]", original)
    after = re.findall(r"\w+|\s+|[^\w\s]", proposed)
    parts = ["  "]
    for tag, i, j, k, end in difflib.SequenceMatcher(
        None, before, after, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            parts.append(escape("".join(before[i:j])))
        else:
            if tag in ("replace", "delete"):
                parts.append(f"[bold red strike]{escape(''.join(before[i:j]))}[/bold red strike]")
            if tag in ("replace", "insert"):
                parts.append(
                    f"[bold green underline]{escape(''.join(after[k:end]))}[/bold green underline]"
                )
    return "".join(parts)


def format_diff_lines(original: str, proposed: str, title: str = "page") -> list[str]:
    """Generate compact preview rows; unified patch output stays unchanged."""
    diff = list(
        difflib.unified_diff(
            original.splitlines(),
            proposed.splitlines(),
            fromfile=f"a/{title}",
            tofile=f"b/{title}",
            lineterm="",
        )
    )
    if not diff:
        return ["[dim italic](No changes between original and proposed content)[/dim italic]"]

    lines = [f"[bold white]{escape(line)}[/bold white]" for line in diff[:2]]
    index = 2
    while index < len(diff):
        line = diff[index]
        if line.startswith(("-", "+")):
            removed: list[str] = []
            added: list[str] = []
            while index < len(diff) and diff[index].startswith("-"):
                removed.append(diff[index][1:])
                index += 1
            while index < len(diff) and diff[index].startswith("+"):
                added.append(diff[index][1:])
                index += 1
            for before, after in zip_longest(removed, added):
                if before is not None and after is not None:
                    lines.append(_inline_change(before, after))
                elif before is not None:
                    lines.append(f"[bold red]-{escape(before)}[/bold red]")
                else:
                    lines.append(f"[bold green]+{escape(after)}[/bold green]")
        else:
            esc = escape(line)
            lines.append(f"[bold cyan]{esc}[/bold cyan]" if line.startswith("@@") else esc)
            index += 1
    return lines
