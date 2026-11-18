from __future__ import annotations

from agentic_bot.diff import (
    compute_diff_stats,
    format_diff_lines,
    generate_unified_diff,
    print_diff,
)
from rich.console import Console


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


def test_format_diff_lines():
    orig = "function test() {\n  return 1;\n}\n"
    prop = "function test() {\n  return 2;\n}\n"
    lines = format_diff_lines(orig, prop, title="Gadget.js")
    assert any("[bold red]" in line and "return 1;" in line for line in lines)
    assert any("[bold green]" in line and "return 2;" in line for line in lines)
    assert any("[bold white]--- a/Gadget.js" in line for line in lines)
