from __future__ import annotations

import os
import re
import select
import sys
import termios
import tty
from collections.abc import Iterator
from contextlib import contextmanager


def format_badge(key: str, label: str, bg_color: str = "white") -> str:
    """Neutral navigation; cyan inspection, yellow edits, green acceptance, red rejection."""
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
    if b.startswith(b"\x1b[<"):
        report = re.fullmatch(rb"\x1b\[<(\d+);\d+;\d+M", b)
        button = int(report[1]) if report else -1
        return {64: "up", 65: "down"}.get(button & ~28, "unknown")
    if b.startswith(b"\x1b[M"):
        button = b[3] - 32 if len(b) == 6 else -1
        return {64: "up", 65: "down"}.get(button & ~28, "unknown")
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


# Keystrokes read from the terminal but not yet consumed by read_key.
_pending = bytearray()

_KNOWN_ESCAPE_SEQUENCES = tuple(
    sorted(
        (
            b"\x1b[A",
            b"\x1b[B",
            b"\x1b[C",
            b"\x1b[D",
            b"\x1b[F",
            b"\x1b[H",
            b"\x1b[1~",
            b"\x1b[4~",
            b"\x1b[5~",
            b"\x1b[6~",
            b"\x1bOA",
            b"\x1bOB",
            b"\x1bOC",
            b"\x1bOD",
        ),
        key=len,
        reverse=True,
    )
)


def split_key_chunk(buf: bytearray, final: bool = False) -> bytes | None:
    """Pop exactly one keystroke's raw bytes from the front of buf.

    Returns None when buf holds only an incomplete sequence that may still
    grow; with final=True the remainder is flushed as a single chunk.
    """
    if not buf:
        return None

    b0 = buf[0]

    if b0 == 0x1B:
        data = bytes(buf)
        if data.startswith(b"\x1b[M"):
            # Legacy mouse reports carry three bytes after M, not keyboard input.
            if len(buf) < 6 and not final:
                return None
            chunk = bytes(buf[:6])
            del buf[:6]
            return chunk
        for seq in _KNOWN_ESCAPE_SEQUENCES:
            if data.startswith(seq):
                del buf[: len(seq)]
                return seq
        if not final and any(seq.startswith(data) for seq in _KNOWN_ESCAPE_SEQUENCES):
            return None
        if len(buf) == 1:
            chunk = bytes(buf)
            del buf[:]
            return chunk
        if buf[1] in (ord("["), ord("O")):
            # CSI/SS3 run: parameter bytes then a final byte in 0x40-0x7E
            for i in range(2, len(buf)):
                if 0x40 <= buf[i] <= 0x7E:
                    chunk = bytes(buf[: i + 1])
                    del buf[: i + 1]
                    return chunk
            if not final:
                return None
            chunk = bytes(buf)
            del buf[:]
            return chunk
        chunk = bytes(buf[:2])
        del buf[:2]
        return chunk

    if b0 < 0x80:
        chunk = bytes(buf[:1])
        del buf[:1]
        return chunk

    if 0xC0 <= b0 <= 0xDF:
        need = 2
    elif 0xE0 <= b0 <= 0xEF:
        need = 3
    elif 0xF0 <= b0 <= 0xF7:
        need = 4
    else:
        # Stray continuation byte
        chunk = bytes(buf[:1])
        del buf[:1]
        return chunk

    if len(buf) < need:
        if not final:
            return None
        need = len(buf)
    chunk = bytes(buf[:need])
    del buf[:need]
    return chunk


def read_key(timeout: float | None = None) -> str:
    """Read one keyboard or mouse-wheel event from terminal stdin in raw mode.

    Buffered keystrokes are consumed one per call, so keys queued during a
    slow frame are delivered individually instead of being merged and lost.

    Mouse reporting is enabled only while waiting for raw input, never while
    a caller runs a prompt or editor. Wheel events use the existing up/down keys.

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

    mouse = sys.stdout.isatty()
    while True:
        chunk = split_key_chunk(_pending)
        if chunk is not None:
            return parse_raw_bytes(chunk)

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            # TCSANOW: never flush input queued while frames rendered
            tty.setraw(fd, when=termios.TCSANOW)
            if mouse:
                sys.stdout.write("\033[?1000h\033[?1006h")
                sys.stdout.flush()
            if not _pending and timeout is not None:
                r, _, _ = select.select([fd], [], [], timeout)
                if not r:
                    return "timeout"
            if _pending:
                # Incomplete sequence: give trailing bytes a short grace period
                r, _, _ = select.select([fd], [], [], 0.05)
                if not r:
                    return parse_raw_bytes(split_key_chunk(_pending, final=True))
            data = os.read(fd, 32)
            if not data:
                if _pending:
                    return parse_raw_bytes(split_key_chunk(_pending, final=True))
                return "q"
            _pending.extend(data)
        finally:
            try:
                if mouse:
                    sys.stdout.write("\033[?1006l\033[?1000l")
                    sys.stdout.flush()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
