from __future__ import annotations

import os
import sys
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
PROMPT = "[a]pprove / [s]kip / [q]uit: "


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
        out: TextIO | None = None,
    ) -> None:
        self._input = input_fn
        self._out = out if out is not None else sys.stdout
        self._color = _supports_color(self._out)

    def _write(self, line: str = "") -> None:
        print(line, file=self._out)

    def __call__(self, proposal: Proposal) -> str:
        self._write()
        self._write(f"--- {proposal.kind}: {proposal.title}")
        if proposal.url:
            self._write(f"    {proposal.url}")
        for line in proposal.context:
            self._write(f"    {line}")
        self._write(f"    files: {proposal.raster} -> {proposal.svg}")
        self._write(colorize_diff(proposal.diff, enabled=self._color))
        self._write(f"    edit summary: {proposal.edit_summary}")
        while True:
            self._write(PROMPT.rstrip())
            raw = self._input("").strip().lower()
            decision = DECISIONS.get(raw)
            if decision is not None:
                return decision
            self._write("Please answer a (approve), s (skip) or q (quit).")


def confirm(question: str, *, input_fn: Callable[[str], str] = input) -> bool:
    """Yes/no gate that defaults to no on empty or unrecognized answers."""
    for _ in range(5):
        raw = input_fn(f"{question} [y/N] ").strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"", "n", "no"}:
            return False
        print("Please answer y or n.")
    return False
