"""AI-assisted tests for explicit approval followed by publication from preview."""

from unittest.mock import MagicMock, patch

import pytest
from agentic_bot.models import PageSnapshot
from agentic_bot.review import render_proposal_view, review_proposal_interactive
from agentic_bot.store import ProposalStore
from agentic_bot.validate import ValidationResult
from rich.console import Console


@pytest.mark.parametrize(
    "answers,status",
    [([False], "pending"), ([True, False], "approved"), ([True, True], "published")],
)
def test_preview_p_approves_then_publishes_only_after_both_confirmations(tmp_path, answers, status):
    store = ProposalStore(tmp_path)
    proposal = store.create(PageSnapshot("Page", 100, "", "base"), "proposed", "S", "R", "I")
    wiki = MagicMock()
    validated_statuses = []

    def validate(client, current):
        validated_statuses.append(current.status)
        return ValidationResult(current.current_version, current.page.revid)

    def publish(**kwargs):
        assert store.load(proposal.id).status == "approved"
        assert kwargs["text"] == proposal.proposed_content
        assert kwargs["expected_revid"] == 100
        return 101, "2026-01-01T00:00:00Z"

    wiki.publish_page.side_effect = publish
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["p", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as render,
        patch("agentic_bot.validate.validate_proposal", side_effect=validate),
        patch("rich.prompt.Confirm.ask", side_effect=answers) as confirm,
        patch("rich.prompt.Prompt.ask", return_value=""),
    ):
        review_proposal_interactive(Console(), proposal, store, wiki)
    assert confirm.call_count == len(answers)
    assert store.load(proposal.id).status == status
    assert validated_statuses == (["pending", "approved"] if answers[0] else ["pending"])
    assert wiki.publish_page.call_count == (status == "published")
    if status == "approved":
        assert "Publication cancelled" in render.call_args.kwargs["notice"]


@pytest.mark.parametrize("stage", ["approval", "publication"])
def test_preview_p_validation_errors_never_publish(tmp_path, stage):
    store = ProposalStore(tmp_path)
    proposal = store.create(PageSnapshot("Page", 100, "", "base"), "proposed", "S", "R", "I")
    clean = ValidationResult(1, 100)
    error = ValidationResult(1, 100, errors=("missing template Ghost",))
    wiki = MagicMock()
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["p", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)),
        patch(
            "agentic_bot.validate.validate_proposal",
            side_effect=[error] if stage == "approval" else [clean, error],
        ),
        patch("rich.prompt.Confirm.ask", return_value=True) as confirm,
    ):
        review_proposal_interactive(Console(), proposal, store, wiki)
    wiki.publish_page.assert_not_called()
    assert confirm.call_count == (stage == "publication")
    assert store.load(proposal.id).status == ("approved" if stage == "publication" else "pending")


@pytest.mark.parametrize("status", ["pending", "approved"])
def test_preview_p_requires_interactive_terminal_before_remote_work(tmp_path, status):
    store = ProposalStore(tmp_path)
    proposal = store.create(PageSnapshot("Page", 100, "", "base"), "proposed", "S", "R", "I")
    proposal = store.set_status(proposal.id, status)
    wiki = MagicMock()
    with (
        patch("sys.stdin.isatty", return_value=False),
        patch("agentic_bot.review.read_key", side_effect=["p", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)),
        patch("agentic_bot.validate.validate_proposal") as validate,
        patch("rich.prompt.Confirm.ask") as confirm,
    ):
        review_proposal_interactive(Console(), proposal, store, wiki)
    validate.assert_not_called()
    confirm.assert_not_called()
    wiki.publish_page.assert_not_called()


@pytest.mark.parametrize("width,height", [(80, 24), (120, 40)])
def test_preview_frame_fits_terminal_with_wrapped_controls(tmp_path, width, height):
    store = ProposalStore(tmp_path)
    proposal = store.create(PageSnapshot("Page", 100, "", "base"), "proposed", "S", "R", "I")
    console = Console(record=True, width=width, color_system=None)
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(width, height)):
        render_proposal_view(console, proposal)
    output = console.export_text()
    assert len(output.splitlines()) < height
    assert "Back" in output and "Actions" in output
