"""AI-assisted regressions for measured terminal quality defects."""

from unittest.mock import MagicMock, patch

import pytest
from agentic_bot.editor import edit_text_in_editor
from agentic_bot.models import PageSnapshot
from agentic_bot.review import (
    interactive_dashboard_loop,
    render_dashboard_table,
    render_proposal_view,
    review_proposal_interactive,
)
from agentic_bot.store import ProposalStore
from rich.console import Console


def make_proposal(store, title="Fixture"):
    return store.create(PageSnapshot(title, 100, "", "base\n"), "proposed\n", "S", "R", "I")


@pytest.mark.parametrize("surface", ["dashboard", "proposal"])
def test_controls_use_semantic_colours(tmp_path, surface, monkeypatch):
    """AI-assisted: both surfaces communicate the same action categories."""
    import io

    from rich.text import Text

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    proposal = make_proposal(ProposalStore(tmp_path))
    output = io.StringIO()
    console = Console(file=output, width=140, force_terminal=True, color_system="standard")
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(140, 48)):
        if surface == "dashboard":
            render_dashboard_table(console, [proposal])
        else:
            render_proposal_view(console, proposal)
    rendered = Text.from_ansi(output.getvalue())
    controls = {
        "p": "green",
        "d": "red",
        "e": "yellow",
        "t": "yellow",
        "o": "cyan",
        "f" if surface == "dashboard" else "v": "white",
        "q" if surface == "dashboard" else "b": "white",
    }
    if surface == "proposal":
        controls.update(c="cyan", a="green", r="yellow", m="yellow")
    else:
        controls["Enter"] = "white"
    for key, colour in controls.items():
        position = rendered.plain.rindex(f" {key} ") + 1
        style = rendered.get_style_at_offset(console, position)
        assert style.bgcolor is not None, key
        assert style.bgcolor.number == console.get_style(f"on {colour}").bgcolor.number, key


@pytest.mark.parametrize("width,height", [(80, 24), (120, 40), (140, 48)])
@pytest.mark.parametrize("selected_idx", [35, 39])
def test_dashboard_keeps_selected_proposal_and_controls_visible(
    tmp_path, width, height, selected_idx
):
    store = ProposalStore(tmp_path)
    proposals = [
        store.create(
            PageSnapshot(f"Page {i} " + "Доўгая назва " * 12, 100, "", "base\n"),
            "proposed\n",
            "Summary",
            "AI-assisted rationale " * 15,
            "Long issue description " * 15,
            mark_as_bot=False,
        )
        for i in range(40)
    ]
    console = Console(record=True, width=width, color_system=None)
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(width, height)):
        render_dashboard_table(console, proposals, selected_idx=selected_idx)
    text = console.export_text()
    assert len(text.splitlines()) < height
    assert f"Page {selected_idx}" in text and "Quit" in text
    assert "40" in text  # summary still describes the complete list
    selected_line = next(line for line in text.splitlines() if f"Page {selected_idx}" in line)
    assert "▶" in selected_line and f"#{selected_idx + 1:03}" in selected_line
    assert "PENDING" in selected_line
    if width >= 100:
        assert "CRITICAL" in selected_line and "+1" in selected_line


@pytest.mark.parametrize("width,height", [(40, 12), (80, 10)])
def test_dashboard_small_window_keeps_exit_hint(tmp_path, width, height):
    store = ProposalStore(tmp_path)
    console = Console(record=True, width=width, color_system=None)
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(width, height)):
        render_dashboard_table(console, [make_proposal(store)])
    text = console.export_text()
    assert "Terminal too small" in text and "[q] Quit" in text
    assert len(text.splitlines()) < height


def test_dashboard_defaults_to_active_and_can_filter_archived_statuses(tmp_path):
    store = ProposalStore(tmp_path)
    for status in ("pending", "approved", "conflict", "declined", "published"):
        proposal = make_proposal(store, f"Fixture-{status}")
        store.set_status(proposal.id, status)
    console = Console(record=True, width=120, color_system=None)
    frames = []

    def next_key():
        frames.append(console.export_text(clear=True))
        return "f" if len(frames) < 8 else "q"

    wiki = MagicMock()
    with (
        patch("agentic_bot.review.read_key", side_effect=next_key),
        patch("agentic_bot.review.shutil.get_terminal_size", return_value=(120, 40)),
        patch("agentic_bot.review.WikiClient") as connect,
    ):
        interactive_dashboard_loop(console, store, wiki)

    active = {"pending", "approved", "conflict"}
    expected = [active, {"pending"}, {"approved"}, {"conflict"}, {"declined"}, {"published"}]
    expected += [active | {"declined", "published"}, active]
    for frame, statuses in zip(frames, expected, strict=True):
        for status in ("pending", "approved", "conflict", "declined", "published"):
            assert (f"Fixture-{status}" in frame) == (status in statuses)
    connect.assert_not_called()
    assert not wiki.mock_calls


def test_short_preview_shows_recovery_instead_of_overflow(tmp_path):
    proposal = make_proposal(ProposalStore(tmp_path))
    console = Console(record=True, width=80, color_system=None)
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(80, 12)):
        render_proposal_view(console, proposal, notice="Synthetic long notice " * 5)
    text = console.export_text()
    assert len(text.splitlines()) < 12
    assert "Terminal too small" in text and "Back" in text


@pytest.mark.parametrize("command", ["'unterminated", "fixture-missing-editor"])
def test_editor_launch_failures_use_existing_error_contract(monkeypatch, command):
    monkeypatch.setenv("VISUAL", command)
    with patch("subprocess.run", side_effect=FileNotFoundError("Synthetic editor missing")):
        with pytest.raises(ValueError, match="editor"):
            edit_text_in_editor("synthetic article", suffix=".wiki")


@pytest.mark.parametrize("key", ["e", "m"])
def test_editor_failure_returns_to_preview_without_mutation(tmp_path, key):
    store = ProposalStore(tmp_path)
    proposal = make_proposal(store)
    wiki = MagicMock()
    wiki.fetch_page.return_value = proposal.page
    with (
        patch("agentic_bot.review.read_key", side_effect=[key, "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as render,
        patch(
            "agentic_bot.review.edit_text_in_editor",
            side_effect=ValueError("Synthetic editor failure"),
        ),
        patch("rich.prompt.Prompt.ask", return_value="1"),
    ):
        review_proposal_interactive(Console(), proposal, store, wiki)
    assert "Synthetic editor failure" in render.call_args.kwargs["notice"]
    assert store.load(proposal.id) == proposal


@pytest.mark.parametrize("failure", ["fetch", "initialization", "editor"])
def test_dashboard_edit_failure_is_visible_without_mutation(tmp_path, failure):
    store = ProposalStore(tmp_path)
    proposal = make_proposal(store)
    wiki = MagicMock()
    wiki.fetch_page.return_value = proposal.page
    if failure == "fetch":
        wiki.fetch_page.side_effect = RuntimeError("Synthetic fetch failure")
    with (
        patch("agentic_bot.review.read_key", side_effect=["e", "q"]),
        patch("agentic_bot.review.render_dashboard_table") as render,
        patch(
            "agentic_bot.review.WikiClient",
            side_effect=RuntimeError("Synthetic initialization failure"),
        ),
        patch(
            "agentic_bot.review.edit_text_in_editor",
            side_effect=ValueError("Synthetic editor failure"),
        ) as editor,
    ):
        interactive_dashboard_loop(Console(), store, None if failure == "initialization" else wiki)
    assert f"Synthetic {failure} failure" in render.call_args.kwargs["notice"]
    if failure != "editor":
        editor.assert_not_called()
    assert store.load(proposal.id) == proposal
