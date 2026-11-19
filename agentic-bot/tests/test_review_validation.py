"""AI-assisted regression tests for on-demand review validation."""

from unittest.mock import MagicMock, patch

import pytest
from agentic_bot.models import PageSnapshot
from agentic_bot.review import (
    interactive_dashboard_loop,
    render_proposal_view,
    review_proposal_interactive,
)
from agentic_bot.store import ProposalStore
from agentic_bot.validate import ValidationResult
from rich.console import Console


@pytest.fixture
def proposal_store(tmp_path):
    store = ProposalStore(tmp_path)
    proposal = store.create(PageSnapshot("Page", 100, "", "base\n"), "proposed\n", "S", "R", "I")
    return proposal, store


@pytest.mark.parametrize("status", ["pending", "approved", "declined", "published", "conflict"])
def test_dashboard_inspection_and_navigation_are_offline(proposal_store, status):
    proposal, store = proposal_store
    store.set_status(proposal.id, status)
    before = store.load(proposal.id)
    with (
        patch("agentic_bot.review.WikiClient") as client,
        patch(
            "agentic_bot.validate.validate_proposal", return_value=ValidationResult(1, 100)
        ) as validation,
        patch("agentic_bot.review.read_key", side_effect=["enter", "j", "v", "b", "q"]),
    ):
        interactive_dashboard_loop(Console(), store)
    client.assert_not_called()
    validation.assert_not_called()
    assert store.load(proposal.id) == before


@pytest.mark.parametrize("action,status", [("a", "pending"), ("p", "approved")])
def test_review_action_runs_fresh_validation_before_confirmation(proposal_store, action, status):
    proposal, store = proposal_store
    if status == "approved":
        proposal = store.set_status(proposal.id, status)
    clean = ValidationResult(1, 100)
    errors = ValidationResult(1, 100, errors=("missing transcluded template Ghost",))
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.validate.validate_proposal", side_effect=[clean, errors]) as validation,
        patch("agentic_bot.review.read_key", side_effect=["c", action, "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as render,
        patch("rich.prompt.Confirm.ask") as confirm,
    ):
        review_proposal_interactive(Console(), proposal, store, wiki=MagicMock())
    assert validation.call_count == 2
    confirm.assert_not_called()
    assert "Ghost" in render.call_args.kwargs["notice"]
    assert store.load(proposal.id).status == status


def test_dashboard_publication_cannot_bypass_validation(proposal_store):
    proposal, store = proposal_store
    store.set_status(proposal.id, "approved")
    errors = ValidationResult(1, 100, errors=("missing transcluded template Ghost",))
    wiki = MagicMock()
    with (
        patch("agentic_bot.validate.validate_proposal", return_value=errors) as validation,
        patch("agentic_bot.review.read_key", side_effect=["p", "q"]),
        patch("rich.prompt.Confirm.ask") as confirm,
    ):
        interactive_dashboard_loop(Console(), store, wiki)
    validation.assert_called_once()
    confirm.assert_not_called()
    wiki.publish_page.assert_not_called()


def test_piped_review_cannot_approve(proposal_store):
    proposal, store = proposal_store
    with (
        patch("sys.stdin.isatty", return_value=False),
        patch("agentic_bot.validate.validate_proposal", return_value=ValidationResult(1, 100)),
        patch("agentic_bot.review.read_key", side_effect=["a", "b"]),
        patch("rich.prompt.Confirm.ask", return_value=True) as confirm,
    ):
        review_proposal_interactive(Console(), proposal, store, wiki=MagicMock())
    confirm.assert_not_called()
    assert store.load(proposal.id).status == "pending"


def test_validation_details_and_stale_state_are_visible(proposal_store):
    proposal, store = proposal_store
    result = ValidationResult(
        1,
        100,
        errors=("missing template Ghost",),
        warnings=("intentional red link",),
        unverified=("TemplateData unavailable",),
    )
    console = Console(record=True, width=120)
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(120, 50)):
        render_proposal_view(console, proposal, validation=result, view_mode="validation")
    text = console.export_text(clear=True)
    assert "error: missing template Ghost" in text
    assert "warning: intentional red link" in text
    assert "unverified: TemplateData unavailable" in text
    proposal = store.update_content(proposal.id, "changed")
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(120, 50)):
        render_proposal_view(console, proposal, validation=ValidationResult(1, 100))
    text = console.export_text()
    assert "STALE" in text
    assert "PASSED" not in text
