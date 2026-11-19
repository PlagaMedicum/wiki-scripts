from __future__ import annotations

import pytest
from agentic_bot.diff import (
    compute_diff_stats,
    format_diff_lines,
    generate_unified_diff,
    print_diff,
)
from rich.console import Console
from rich.text import Text


def test_compute_diff_stats():
    orig = "line 1\nline 2\nline 3\n"
    prop = "line 1\nline 2 modified\nline 3\nline 4 added\n"
    added, removed = compute_diff_stats(orig, prop)
    assert added == 2
    assert removed == 1


def test_generate_unified_diff():
    orig = "line 1\nline 2\nline 3\n"
    prop = "line 1\nline 2 modified\nline 3\n"
    diff = generate_unified_diff(orig, prop, title="TestPage")

    assert "--- a/TestPage" in diff
    assert "+++ b/TestPage" in diff
    assert "-line 2" in diff
    assert "+line 2 modified" in diff


def test_empty_diff():
    text = "identical content\n"
    diff = generate_unified_diff(text, text, title="SamePage")
    assert diff == ""


def test_diff_with_belarusian_unicode():
    orig = "Пункт 1: ужыванне літары 'і'.\nПункт 2: ужыванне літары 'ў'.\n"
    prop = "Пункт 1: ужыванне літары 'і'.\nПункт 2: правільнае ўжыванне літары 'ў'.\n"
    diff = generate_unified_diff(orig, prop, title="Беларускі тэкст")

    assert "+Пункт 2: правільнае ўжыванне літары 'ў'." in diff
    assert "-Пункт 2: ужыванне літары 'ў'." in diff


def test_print_diff_does_not_raise():
    console = Console(record=True)
    orig = "a\nb\n"
    prop = "a\nc\n"
    print_diff(console, orig, prop, title="Test")
    output = console.export_text()
    assert "-b" in output
    assert "+c" in output


@pytest.mark.parametrize(
    "before,after,removed,added",
    [
        ("The old word stays.", "The new word stays.", "old", "new"),
        ("Літара і ў тэксце.", "Літара ў ў тэксце.", "і", "ў"),
        ("Caption ends here", "Caption ends here.", "", "."),
        ("A redundant word.", "A word.", "redundant ", ""),
        ("[[Page|old]] {{name}}", "[[Page|new]] {{name}}", "old", "new"),
        ("A  word.", "A word.", "  ", " "),
    ],
)
def test_preview_highlights_only_changed_tokens(before, after, removed, added):
    """AI-assisted: a paragraph is displayed once with neutral shared text."""
    rows = [Text.from_markup(line) for line in format_diff_lines(before, after)]
    body = rows[3:]
    assert len(body) == 1
    row = body[0]
    assert row.plain.startswith("  ")
    console = Console()
    coloured = {"red": "", "green": ""}
    reconstructed = {"before": "", "after": ""}
    for offset, char in enumerate(row.plain):
        style = row.get_style_at_offset(console, offset)
        if style.color and style.color.name in coloured:
            coloured[style.color.name] += char
        if not style.color or style.color.name != "green":
            reconstructed["before"] += char
        if not style.color or style.color.name != "red":
            reconstructed["after"] += char
    for colour, expected in (("red", removed), ("green", added)):
        # Either adjacent space may belong to a deleted word; both reconstruct identically.
        actual = coloured[colour]
        assert (actual.strip() if expected.strip() else actual) == (
            expected.strip() if expected.strip() else expected
        )
    assert reconstructed == {"before": "  " + before, "after": "  " + after}


def test_preview_preserves_unpaired_lines_and_context():
    rows = [
        Text.from_markup(line).plain
        for line in format_diff_lines("context\nold word\n", "context\nnew word\nextra\n")
    ]
    assert rows[3:] == [" context", "  oldnew word", "+extra"]
