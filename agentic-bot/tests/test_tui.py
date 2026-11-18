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
