from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from agentic_bot.models import PageSnapshot
from agentic_bot.review import (
    approval_block_reason,
    build_proposal_content_lines,
    extract_test_status,
    interactive_dashboard_loop,
    publication_block_reason,
    render_proposal_view,
    review_proposal_interactive,
)
from agentic_bot.store import ProposalStore
from agentic_bot.validate import ValidationResult
from rich.console import Console


@pytest.fixture(autouse=True)
def _no_wiki_validation(monkeypatch):
    """Keep the suite offline: validation performs real API calls unless a test opts in."""
    monkeypatch.setattr(
        "agentic_bot.validate.validate_proposal",
        lambda client, proposal: ValidationResult(proposal.current_version, proposal.page.revid),
    )
    monkeypatch.setattr("agentic_bot.review.WikiClient", MagicMock())


def test_extract_test_status():
    assert "SEE NOTES" in extract_test_status("Tests passed")
    assert "SEE NOTES" in extract_test_status("Tests failed")
    assert "SEE NOTES" in extract_test_status("Tests not run")
    assert "UNVERIFIED" in extract_test_status("Documentation only")


def test_build_proposal_content_lines():
    snap = PageSnapshot("Test", 1, "2026-01-01T00:00:00Z", "line 1\nline 2\n")
    proposal = MagicMock()
    proposal.page = snap
    proposal.proposed_content = "line 1\nline 2 modified\nline 3 added\n"
    proposal.rationale = "Test rationale line."
    proposal.edit_summary = "Edit summary."

    lines = build_proposal_content_lines(proposal, width=80)
    assert any("Agent Rationale" in line for line in lines)
    assert any("Proposed Changes" in line for line in lines)
    assert any("line 2 modified" in line for line in lines)
    assert any("Proposed Edit Summary" in line for line in lines)

    # Test view_mode="diff" only
    diff_only = build_proposal_content_lines(proposal, view_mode="diff", width=80)
    assert not any("Agent Rationale" in line for line in diff_only)
    assert any("Proposed Changes" in line for line in diff_only)


def test_render_proposal_view_clamping():
    console = Console(record=True)
    snap = PageSnapshot("Test", 1, "2026-01-01T00:00:00Z", "a\nb\n")
    proposal = MagicMock()
    proposal.id = "001"
    proposal.status = "pending"
    proposal.page = snap
    proposal.proposed_content = "a\nc\n"
    proposal.rationale = "Rationale"
    proposal.edit_summary = "Summary"
    proposal.current_version = 1
    proposal.versions = [1]
    proposal.issue = "Issue"
    proposal.mark_as_bot = False

    # Test with scroll_offset beyond max -> should clamp
    clamped, max_s, vp_h = render_proposal_view(
        console, proposal, scroll_offset=9999, sync_status="synced"
    )
    assert clamped <= max_s


def test_proposal_view_does_not_claim_unchecked_live_sync():
    console = Console(record=True)
    proposal = MagicMock()
    proposal.id = "001"
    proposal.status = "pending"
    proposal.page = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal.proposed_content = "Proposed"
    proposal.rationale = "No verification"
    proposal.edit_summary = "Summary"
    proposal.current_version = 1
    proposal.versions = [1]
    proposal.issue = "Issue"
    proposal.mark_as_bot = False

    render_proposal_view(console, proposal)

    assert "LOCAL BASE" in console.export_text()


def test_dashboard_does_not_publish_from_piped_input(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    store.create(snap, "Proposed", "Summary", "R", "I")
    store.set_status("001", "approved")
    wiki = MagicMock()
    wiki.publish_page.return_value = (101, "2026-01-01T00:01:00Z")

    with (
        patch("sys.stdin.isatty", return_value=False),
        patch("agentic_bot.review.read_key", side_effect=["p", "q"]),
        patch("agentic_bot.review.render_dashboard_table"),
        patch("rich.prompt.Confirm.ask", return_value=True),
        patch("rich.prompt.Prompt.ask", return_value=""),
    ):
        interactive_dashboard_loop(Console(), store, wiki)

    wiki.publish_page.assert_not_called()


def test_dashboard_does_not_publish_pending_proposal(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    store.create(snap, "Proposed", "Summary", "R", "I")
    wiki = MagicMock()
    wiki.publish_page.return_value = (101, "2026-01-01T00:01:00Z")

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["p", "q"]),
        patch("agentic_bot.review.render_dashboard_table"),
        patch("rich.prompt.Confirm.ask", return_value=True) as confirm,
        patch("rich.prompt.Prompt.ask", return_value=""),
    ):
        interactive_dashboard_loop(Console(), store, wiki)

    confirm.assert_not_called()
    wiki.publish_page.assert_not_called()
    assert store.load("001").status == "pending"


def test_confirm_publication_requires_approved():
    from agentic_bot.review import confirm_publication

    snap = PageSnapshot("Test", 1, "2026-01-01T00:00:00Z", "text")
    pending_p = MagicMock(status="pending", id="001", page=snap, mark_as_bot=False)
    console = Console(record=True)

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("rich.prompt.Confirm.ask") as confirm,
    ):
        result = confirm_publication(console, pending_p)
        assert result is None
        confirm.assert_not_called()
        assert "must be approved" in console.export_text()


def test_dashboard_does_not_publish_declined_proposal(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "Summary", "R", "I")
    store.set_status(proposal.id, "declined")
    wiki = MagicMock()

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["p", "q"]),
        patch("agentic_bot.review.render_dashboard_table"),
        patch("rich.prompt.Confirm.ask", return_value=True) as confirm,
    ):
        interactive_dashboard_loop(Console(), store, wiki)

    confirm.assert_not_called()
    wiki.publish_page.assert_not_called()


def test_dashboard_has_no_approve_shortcut(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "Summary", "R", "I")
    assert proposal.status == "pending"

    with (
        patch("agentic_bot.review.read_key", side_effect=["a", "q"]),
        patch("agentic_bot.review.render_dashboard_table"),
    ):
        interactive_dashboard_loop(Console(), store)

    # Status must NOT be approved from dashboard shortcut
    assert store.load(proposal.id).status == "pending"


def test_review_press_a_requires_confirmation(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "Summary", "R", "I")
    assert proposal.status == "pending"

    # Declining confirmation -> remains pending
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["a", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)),
        patch("rich.prompt.Confirm.ask", return_value=False) as mock_confirm,
    ):
        result = review_proposal_interactive(Console(), proposal, store)
        assert result == "back"
        mock_confirm.assert_called_once()

    assert store.load(proposal.id).status == "pending"

    # Accepting confirmation -> approved
    with (
        patch("agentic_bot.review.read_key", side_effect=["a", "b"]),
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)),
        patch("rich.prompt.Confirm.ask", return_value=True) as mock_confirm,
    ):
        result = review_proposal_interactive(Console(), proposal, store)
        assert result == "back"
        mock_confirm.assert_called_once()

    assert store.load(proposal.id).status == "approved"


def test_dashboard_open_declined_has_no_side_effects(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "Summary", "R", "I")
    store.set_status(proposal.id, "declined", reason="Rejection reason")

    wiki = MagicMock()
    # Live page is newer
    wiki.fetch_page.return_value = PageSnapshot("Page", 105, "2026-01-02T00:00:00Z", "Live content")

    with (
        patch("agentic_bot.review.read_key", side_effect=["f", "f", "f", "f", "enter", "q"]),
        patch("agentic_bot.review.render_dashboard_table"),
        patch("agentic_bot.review.review_proposal_interactive", return_value="back") as mock_review,
    ):
        interactive_dashboard_loop(Console(), store, wiki)
        mock_review.assert_called_once()

    loaded = store.load(proposal.id)
    assert loaded.status == "declined"
    assert loaded.current_version == 1
    assert len(loaded.versions) == 1


def test_pull_and_merge_for_edit_reports_conflicts(tmp_path):
    from agentic_bot.review import pull_and_merge_for_edit

    store = ProposalStore(tmp_path)
    base = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "original line\n")
    proposal = store.create(base, "proposal line\n", "S", "R", "I")
    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot("Page", 105, "2026-01-02T00:00:00Z", "wiki line\n")

    text, was_rebased, live, has_conflicts = pull_and_merge_for_edit(
        Console(), proposal, store, wiki
    )
    assert was_rebased
    assert has_conflicts
    assert "<<<<<<<" in text
    assert live.revid == 105

    # Clean merge: live and proposal touch different, non-adjacent lines
    store2 = ProposalStore(tmp_path / "s2")
    base2 = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "a\nb\nc\nd\ne\n")
    proposal2 = store2.create(base2, "a\nP\nc\nd\ne\n", "S", "R", "I")
    wiki2 = MagicMock()
    wiki2.fetch_page.return_value = PageSnapshot(
        "Page", 105, "2026-01-02T00:00:00Z", "a\nb\nc\nd\nL\n"
    )

    text2, was_rebased2, live2, has_conflicts2 = pull_and_merge_for_edit(
        Console(), proposal2, store2, wiki2
    )
    assert was_rebased2
    assert not has_conflicts2
    assert text2 == "a\nP\nc\nd\nL\n"


def test_review_edit_conflicted_merge_is_flagged_not_silent(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "original line\n")
    proposal = store.create(snap, "proposal line\n", "S", "R", "I")

    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot("Page", 105, "2026-01-02T00:00:00Z", "wiki line\n")

    with (
        patch("agentic_bot.review.read_key", side_effect=["e", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
        patch(
            "agentic_bot.review.edit_text_in_editor",
            side_effect=lambda content, suffix: (content, False),
        ),
    ):
        assert review_proposal_interactive(Console(), proposal, store, wiki=wiki) == "back"

    loaded = store.load(proposal.id)
    assert loaded.status == "pending"
    assert loaded.decisions[-1].action == "rebase_with_conflicts"
    assert "<<<<<<<" in loaded.proposed_content
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert any("conflict" in n.lower() for n in notices)


def test_review_edit_resolved_conflict_records_clean_rebase(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "original line\n")
    proposal = store.create(snap, "proposal line\n", "S", "R", "I")

    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot("Page", 105, "2026-01-02T00:00:00Z", "wiki line\n")

    resolved = "combined line\n"
    with (
        patch("agentic_bot.review.read_key", side_effect=["e", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)),
        patch(
            "agentic_bot.review.edit_text_in_editor",
            side_effect=lambda content, suffix: (resolved, True),
        ),
    ):
        assert review_proposal_interactive(Console(), proposal, store, wiki=wiki) == "back"

    loaded = store.load(proposal.id)
    assert loaded.proposed_content == resolved
    assert loaded.decisions[-1].action == "rebase"
    assert loaded.status == "pending"


def test_review_blocked_approve_and_publish_explain_persistently(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "<<<<<<< ours\nA\n=======\nB\n>>>>>>> theirs\n", "S", "R", "I")

    # [a] on conflicted content: blocked with explanation, no confirmation offered
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["a", "down", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
        patch("rich.prompt.Confirm.ask") as mock_confirm,
    ):
        assert review_proposal_interactive(Console(), proposal, store) == "back"

    mock_confirm.assert_not_called()
    assert store.load(proposal.id).status == "pending"
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    # The explanation persists across frames until replaced
    assert sum("conflict markers" in n.lower() for n in notices) >= 2

    # [p] also attempts approval, but unresolved conflict markers block it.
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["p", "down", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
        patch("rich.prompt.Confirm.ask") as mock_confirm,
    ):
        assert review_proposal_interactive(Console(), proposal, store) == "back"

    mock_confirm.assert_not_called()
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert sum("conflict markers" in n.lower() for n in notices) >= 2


def test_publication_block_reason_statuses(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    from agentic_bot.review import publication_block_reason

    proposal = tmp_store.create(sample_snapshot, "Proposed", "S", "R", "I")
    assert "approved" in publication_block_reason(proposal)

    tmp_store.set_status(proposal.id, "declined")
    assert "Reopen" in publication_block_reason(tmp_store.load(proposal.id))

    tmp_store.set_status(proposal.id, "approved")
    assert "validation" in publication_block_reason(tmp_store.load(proposal.id)).lower()

    conflicted = tmp_store.create(
        sample_snapshot, "<<<<<<< ours\nA\n=======\nB\n>>>>>>> theirs\n", "S", "R", "I"
    )
    tmp_store.set_status(conflicted.id, "approved")
    reason = publication_block_reason(tmp_store.load(conflicted.id))
    assert reason is not None
    assert "conflict markers" in reason.lower()


def test_dashboard_blocked_publish_explains_persistently(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    store.create(snap, "Proposed", "S", "R", "I")
    wiki = MagicMock()

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.review.read_key", side_effect=["p", "down", "q"]),
        patch("agentic_bot.review.render_dashboard_table") as mock_render,
        patch("rich.prompt.Confirm.ask") as mock_confirm,
    ):
        interactive_dashboard_loop(Console(), store, wiki)

    mock_confirm.assert_not_called()
    wiki.publish_page.assert_not_called()
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert sum("must be approved" in n.lower() for n in notices) >= 2


def test_review_r_rebases_stale_proposal_exactly(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "a\nb\nc\nd\ne\n")
    proposal = store.create(snap, "a\nP\nc\nd\ne\n", "S", "R", "I")
    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot(
        "Page", 105, "2026-01-02T00:00:00Z", "a\nb\nc\nd\nL\n"
    )

    with (
        patch("agentic_bot.review.read_key", side_effect=["r", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
    ):
        assert review_proposal_interactive(Console(), proposal, store, wiki=wiki) == "back"

    loaded = store.load(proposal.id)
    assert loaded.page.revid == 105
    assert loaded.proposed_content == "a\nP\nc\nd\nL\n"
    assert loaded.status == "pending"  # renewed human approval required
    assert loaded.decisions[-1].action == "rebase"
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert any("105" in n for n in notices)


def test_review_r_on_current_revision_changes_nothing(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "base\n")
    proposal = store.create(snap, "proposed\n", "S", "R", "I")
    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "base\n")

    with (
        patch("agentic_bot.review.read_key", side_effect=["r", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
    ):
        assert review_proposal_interactive(Console(), proposal, store, wiki=wiki) == "back"

    loaded = store.load(proposal.id)
    assert loaded.current_version == 1
    assert loaded.decisions == []
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert any("nothing to rebase" in n.lower() for n in notices)


# ---------------------------------------------------------------------------
# Validation gates: block on confirmed newly introduced errors, handle stale
# results explicitly, never block on warnings/unverified checks.
# ---------------------------------------------------------------------------


def test_block_reasons_validation_gates(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "S", "R", "I")

    clean = ValidationResult(version=proposal.current_version, base_revid=proposal.page.revid)
    assert approval_block_reason(proposal, clean) is None
    assert "validation" in approval_block_reason(proposal, None).lower()

    errors = ValidationResult(
        version=proposal.current_version,
        base_revid=proposal.page.revid,
        errors=("newly introduced link target 'X' does not exist",),
    )
    reason = approval_block_reason(proposal, errors)
    assert reason is not None and "X" in reason

    stale = ValidationResult(version=0, base_revid=0)
    reason = approval_block_reason(proposal, stale)
    assert reason is not None and "stale" in reason.lower()

    # Warnings and unverified checks never block
    noisy = ValidationResult(
        version=proposal.current_version,
        base_revid=proposal.page.revid,
        warnings=("w",),
        unverified=("u",),
    )
    assert approval_block_reason(proposal, noisy) is None

    approved = store.set_status(proposal.id, "approved", reason="t")
    assert publication_block_reason(approved, clean) is None
    assert "validation" in publication_block_reason(approved, None).lower()
    reason = publication_block_reason(approved, errors)
    assert reason is not None and "X" in reason
    reason = publication_block_reason(approved, stale)
    assert reason is not None and "stale" in reason.lower()
    assert publication_block_reason(approved, noisy) is None


def test_review_explicit_validation_becomes_stale_after_edit(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "original line\n")
    proposal = store.create(snap, "proposal line\n", "S", "R", "I")

    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot(
        "Page", 100, "2026-01-01T00:00:00Z", "original line\n"
    )

    def record(client, prop):
        return ValidationResult(version=prop.current_version, base_revid=prop.page.revid)

    with (
        patch("agentic_bot.validate.validate_proposal", side_effect=record) as mock_validate,
        patch("agentic_bot.review.read_key", side_effect=["c", "e", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as render,
        patch(
            "agentic_bot.review.edit_text_in_editor",
            side_effect=lambda content, suffix: ("edited line\n", True),
        ),
    ):
        assert review_proposal_interactive(Console(), proposal, store, wiki=wiki) == "back"

    assert mock_validate.call_count == 1
    edited = store.load(proposal.id)
    assert edited.current_version == 2
    last_result = render.call_args.kwargs["validation"]
    assert not last_result.is_fresh(edited.current_version, edited.page.revid)


def test_review_publish_blocked_by_validation_errors(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "S", "R", "I")
    proposal = store.set_status(proposal.id, "approved", reason="t")

    errors = ValidationResult(
        version=proposal.current_version,
        base_revid=proposal.page.revid,
        errors=("newly introduced template 'Ghost' does not exist",),
    )
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.validate.validate_proposal", return_value=errors),
        patch("agentic_bot.review.read_key", side_effect=["p", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
        patch("agentic_bot.review.confirm_publication") as mock_confirm,
        patch("agentic_bot.review.attempt_publish") as mock_publish,
    ):
        assert review_proposal_interactive(Console(), proposal, store) == "back"

    mock_confirm.assert_not_called()
    mock_publish.assert_not_called()
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert any("Ghost" in n for n in notices)


def test_review_approve_blocked_by_validation_errors(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "S", "R", "I")

    errors = ValidationResult(
        version=proposal.current_version,
        base_revid=proposal.page.revid,
        errors=("newly introduced link target 'X' does not exist",),
    )
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("agentic_bot.validate.validate_proposal", return_value=errors),
        patch("agentic_bot.review.read_key", side_effect=["a", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as mock_render,
        patch("rich.prompt.Confirm.ask") as mock_confirm,
    ):
        assert review_proposal_interactive(Console(), proposal, store) == "back"

    mock_confirm.assert_not_called()
    assert store.load(proposal.id).status == "pending"
    notices = [c.kwargs.get("notice", "") for c in mock_render.call_args_list]
    assert any("'X'" in n for n in notices)


def test_render_proposal_view_shows_validation_summary(tmp_path, capsys):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    proposal = store.create(snap, "Proposed", "S", "R", "I")

    errors = ValidationResult(
        version=1, base_revid=100, errors=("newly introduced link target 'X' does not exist",)
    )
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(100, 30)):
        render_proposal_view(Console(), proposal, validation=errors)
    assert "VALIDATION FAILED" in capsys.readouterr().out

    incomplete = ValidationResult(version=1, base_revid=100, unverified=("u",))
    with patch("agentic_bot.review.shutil.get_terminal_size", return_value=(100, 30)):
        render_proposal_view(Console(), proposal, validation=incomplete)
    out = capsys.readouterr().out
    assert "VALIDATION INCOMPLETE" in out
    assert "PASSED" not in out
