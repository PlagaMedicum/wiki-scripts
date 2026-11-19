from __future__ import annotations

import builtins
import os
import sys
import unicodedata
from collections.abc import Callable
from typing import TextIO

from svg_replacer.workflow import Proposal

DECISIONS = {
    "a": "approve",
    "approve": "approve",
    "s": "skip",
    "skip": "skip",
    "q": "stop",
    "quit": "stop",
    "stop": "stop",
}


def safe_text(text: str) -> str:
    """Render untrusted controls visibly, without changing stored wikitext."""
    return "".join(
        char
        if char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf"}
        else ascii(char)[1:-1]
        for char in text
    )


def safe_print(*values: object, file: TextIO | None = None, color: str | None = None) -> None:
    stream = file if file is not None else sys.stdout
    text = " ".join(safe_text(str(value)) for value in values)
    builtins.print(
        colorize(text, color or "", enabled=bool(color) and _supports_color(stream)),
        file=stream,
    )


def colorize(text: str, code: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _supports_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def colorize_diff(diff: str, *, enabled: bool) -> str:
    if not enabled:
        return diff
    colored: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            code = "36"
        elif line.startswith("+"):
            code = "32"
        elif line.startswith("-"):
            code = "31"
        else:
            code = ""
        colored.append(colorize(line, code, enabled=True) if code else line)
    return "\n".join(colored)


class Decider:
    """Renders a proposal and collects exactly one approve/skip/stop decision."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] = input,
        apply: bool = False,
        out: TextIO | None = None,
    ) -> None:
        self._input = input_fn
        self._out = out if out is not None else sys.stdout
        self._color = _supports_color(self._out)
        self._apply = apply

    def _write(self, line: str = "", *, color: str | None = None) -> None:
        safe_print(line, file=self._out, color=color)

    def __call__(self, proposal: Proposal) -> str:
        self._write()
        heading = "Commons notice" if proposal.kind == "commons" else proposal.title
        self._write(heading, color="36")
        if proposal.url:
            self._write(proposal.url)
        print(colorize_diff(safe_text(proposal.diff), enabled=self._color), file=self._out)
        self._write(f"Edit summary: {proposal.edit_summary}")
        action = "Publish" if self._apply else "Preview (not saved)"
        while True:
            self._write(f"[a] {action}  [s] Skip  [q] Quit", color="33")
            raw = self._input("").strip().lower()
            decision = DECISIONS.get(raw)
            if decision is not None:
                return decision
            self._write("Choose a, s or q.", color="33")


def confirm(question: str, *, input_fn: Callable[[str], str] = input) -> bool:
    """Yes/no gate that defaults to no on empty or unrecognized answers."""
    for _ in range(5):
        raw = input_fn(f"{safe_text(question)} [y/N] ").strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"", "n", "no"}:
            return False
        print("Please answer y or n.")
    return False
