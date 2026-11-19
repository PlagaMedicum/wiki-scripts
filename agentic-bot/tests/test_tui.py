from __future__ import annotations

from agentic_bot.tui import alternate_screen, format_badge, parse_raw_bytes, read_key


def test_format_badge():
    badge = format_badge("p", "Publish", "cyan")
    assert "p" in badge
    assert "Publish" in badge
    assert "black on cyan" in badge


def test_parse_raw_bytes():
    assert parse_raw_bytes(b"\x1b[A") == "up"
    assert parse_raw_bytes(b"\x1bOA") == "up"
    assert parse_raw_bytes(b"\x1b[B") == "down"
    assert parse_raw_bytes(b"\x1bOB") == "down"
    assert parse_raw_bytes(b"\x1b[C") == "right"
    assert parse_raw_bytes(b"\x1b[D") == "left"
    assert parse_raw_bytes(b"\r") == "enter"
    assert parse_raw_bytes(b"\n") == "enter"
    assert parse_raw_bytes(b" ") == "space"
    assert parse_raw_bytes(b"\x1b") == "escape"
    assert parse_raw_bytes(b"\x03") == "ctrl-c"
    assert parse_raw_bytes(b"k") == "k"
    assert parse_raw_bytes(b"j") == "j"
    assert parse_raw_bytes(b"p") == "p"


def test_alternate_screen_non_tty():
    # In pytest/non-tty, alternate_screen should execute without error
    with alternate_screen():
        pass


def test_read_key_non_tty(monkeypatch):
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("q\n"))
    key = read_key()
    assert key == "q"


def test_split_key_chunk_consumes_exactly_one_keystroke():
    from agentic_bot.tui import split_key_chunk

    buf = bytearray(b"jj")
    assert split_key_chunk(buf) == b"j"
    assert bytes(buf) == b"j"
    assert split_key_chunk(buf) == b"j"
    assert bytes(buf) == b""
    assert split_key_chunk(buf) is None

    buf = bytearray(b"\x1b[B\x1b[B")
    assert split_key_chunk(buf) == b"\x1b[B"
    assert split_key_chunk(buf) == b"\x1b[B"
    assert split_key_chunk(buf) is None

    buf = bytearray(b"p\r")
    assert split_key_chunk(buf) == b"p"
    assert split_key_chunk(buf) == b"\r"


def test_split_key_chunk_partial_multibyte_and_escape():
    from agentic_bot.tui import split_key_chunk

    # Incomplete UTF-8 needs more bytes
    buf = bytearray(b"\xd1")
    assert split_key_chunk(buf) is None
    buf += b"\x9e"
    assert split_key_chunk(buf) == b"\xd1\x9e"

    # Lone escape waits for a possible sequence; final flush forces it out
    buf = bytearray(b"\x1b")
    assert split_key_chunk(buf) is None
    assert split_key_chunk(buf, final=True) == b"\x1b"

    # Unknown escape sequence is consumed as one unit, not as stray characters
    buf = bytearray(b"\x1b[1;5Aj")
    assert split_key_chunk(buf) == b"\x1b[1;5A"
    assert split_key_chunk(buf) == b"j"


def test_read_key_never_drops_buffered_keystrokes(monkeypatch):
    from types import SimpleNamespace

    import agentic_bot.tui as tui

    chunks = [b"jj\x1b[B", b"\xd1", b"\x9e"]
    monkeypatch.setattr(
        tui,
        "termios",
        SimpleNamespace(tcgetattr=lambda fd: [], tcsetattr=lambda *a: None, TCSADRAIN=0, TCSANOW=0),
    )
    monkeypatch.setattr(tui, "tty", SimpleNamespace(setraw=lambda fd, when=None: None))
    monkeypatch.setattr(tui, "select", SimpleNamespace(select=lambda *a: ([0], [], [])))
    monkeypatch.setattr(
        tui,
        "os",
        SimpleNamespace(read=lambda fd, n: chunks.pop(0) if chunks else b""),
    )
    monkeypatch.setattr(
        tui,
        "sys",
        SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True, fileno=lambda: 0)),
    )
    tui._pending.clear()
    try:
        assert [read_key() for _ in range(4)] == ["j", "j", "down", "ў"]
    finally:
        tui._pending.clear()


def test_read_key_preserves_keys_queued_during_rendering(monkeypatch):
    """Regression: tty.setraw must not flush input queued before the read.

    Keys typed while a frame renders wait in the kernel tty queue; a PTY
    reproduces this without mocks. The burst also exceeds one 32-byte read,
    so bytes beyond the first batch must survive the next setraw as well.
    """
    import os
    import pty
    from types import SimpleNamespace

    import agentic_bot.tui as tui

    master_fd, slave_fd = pty.openpty()
    try:
        burst = b"j" + b"x" * 39  # queued before read_key runs
        os.write(master_fd, burst)
        monkeypatch.setattr(
            tui,
            "sys",
            SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True, fileno=lambda: slave_fd)),
        )
        tui._pending.clear()
        try:
            keys = [tui.read_key(timeout=1.0) for _ in range(len(burst))]
        finally:
            tui._pending.clear()
    finally:
        os.close(master_fd)
        os.close(slave_fd)

    assert keys == ["j"] + ["x"] * 39
