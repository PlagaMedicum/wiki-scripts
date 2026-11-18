from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentic_bot.models import PageSnapshot
from agentic_bot.review import (
    build_proposal_content_lines,
    extract_test_status,
    interactive_dashboard_loop,
    render_proposal_view,
    sync_proposal_with_wiki,
)
from agentic_bot.store import ProposalStore
from rich.console import Console


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


def test_sync_proposal_with_wiki_synced(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    p = store.create(snap, "Proposed", "Summary", "R", "I")

    wiki = MagicMock()
    wiki.fetch_page.return_value = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")

    status, updated_p = sync_proposal_with_wiki(p, store, wiki)
    assert status == "synced"
    assert updated_p.page.revid == 100


def test_sync_proposal_with_wiki_clean_rebase(tmp_path):
    store = ProposalStore(tmp_path)
    base_text = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", base_text)
    # Proposal modifies line 5
    p = store.create(snap, "line 1\nline 2\nline 3\nline 4\nline 5 proposed\n", "Summary", "R", "I")

    # Live wiki modified line 1 (separated by 3 context lines -> clean 3-way merge)
    live_snap = PageSnapshot(
        "Page", 105, "2026-01-02T00:00:00Z", "line 1 live\nline 2\nline 3\nline 4\nline 5\n"
    )
    wiki = MagicMock()
    wiki.fetch_page.return_value = live_snap

    status, updated_p = sync_proposal_with_wiki(p, store, wiki)
    assert status.startswith("rebased:105")
    assert updated_p.page.revid == 105
    assert "line 1 live" in updated_p.proposed_content
    assert "line 5 proposed" in updated_p.proposed_content


def test_sync_proposal_with_wiki_conflict(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "line1\nline2\n")
    # Both proposal and live edit line 2 differently -> conflict
    p = store.create(snap, "line1\nline2 proposal\n", "Summary", "R", "I")

    live_snap = PageSnapshot("Page", 105, "2026-01-02T00:00:00Z", "line1\nline2 live\n")
    wiki = MagicMock()
    wiki.fetch_page.return_value = live_snap

    status, updated_p = sync_proposal_with_wiki(p, store, wiki)
    assert status.startswith("conflict:105")
    assert updated_p.status == "conflict"


def test_dashboard_does_not_publish_from_piped_input(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("Page", 100, "2026-01-01T00:00:00Z", "Base")
    store.create(snap, "Proposed", "Summary", "R", "I")
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
