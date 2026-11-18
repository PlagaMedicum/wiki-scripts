from __future__ import annotations

import os
import select
import sys
import termios
import tty
from collections.abc import Iterator
from contextlib import contextmanager


def format_badge(key: str, label: str, bg_color: str = "cyan") -> str:
    """Format a high-contrast button badge with key and action label."""
    return f"[bold black on {bg_color}] {key} [/bold black on {bg_color}] {label}"


@contextmanager
def alternate_screen() -> Iterator[None]:
    """Context manager for terminal alternate screen buffer (like Vim or htop)."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        yield
        return

    # Enter alternate screen buffer & hide cursor
    sys.stdout.write("\033[?1049h\033[H\033[?25l")
    sys.stdout.flush()
    try:
        yield
    finally:
        # Exit alternate screen buffer & show cursor
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()


def parse_raw_bytes(b: bytes) -> str:
    """Parse raw terminal byte sequence into a recognized key name."""
    if b in (b"\x1b[A", b"\x1bOA"):
        return "up"
    elif b in (b"\x1b[B", b"\x1bOB"):
        return "down"
    elif b in (b"\x1b[C", b"\x1bOC"):
        return "right"
    elif b in (b"\x1b[D", b"\x1bOD"):
        return "left"
    elif b in (b"\x1b[H", b"\x1b[1~"):
        return "home"
    elif b in (b"\x1b[F", b"\x1b[4~"):
        return "end"
    elif b == b"\x1b[5~":
        return "page_up"
    elif b == b"\x1b[6~":
        return "page_down"
    elif b in (b"\r", b"\n"):
        return "enter"
    elif b == b" ":
        return "space"
    elif b == b"\x1b":
        return "escape"
    elif b == b"\x03":
        return "ctrl-c"

    try:
        return b.decode("utf-8")
    except Exception:
        return "unknown"


def read_key(timeout: float | None = None) -> str:
    """Read a single key or escape sequence from terminal stdin in raw mode.

    Returns:
        str: 'up', 'down', 'left', 'right', 'enter', 'escape', 'space',
             'ctrl-c', or a decoded character string.
    """
    if not sys.stdin.isatty():
        # Fallback for non-interactive / piped environments
        line = sys.stdin.readline()
        if not line:
            return "q"
        return line.strip()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        if timeout is not None:
            r, _, _ = select.select([fd], [], [], timeout)
            if not r:
                return "timeout"

        data = os.read(fd, 32)
        if not data:
            return "q"

        # If data is only b'\x1b', check if trailing escape sequence bytes follow immediately
        if data == b"\x1b":
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                data += os.read(fd, 32)

        return parse_raw_bytes(data)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
