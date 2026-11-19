from __future__ import annotations

from agentic_bot.models import PageSnapshot
from agentic_bot.store import ProposalStore


def test_create_and_load_proposal(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    proposed = "function wikify(text) {\n  return text.replace(/---/g, '—');\n}\n"
    summary = "Вікіфікатар: удакладненне працяжнікаў"
    rationale = "Hypothesis 1 verified with tests."
    issue = "Dashes replacement"

    proposal = tmp_store.create(
        page=sample_snapshot,
        proposed_content=proposed,
        edit_summary=summary,
        rationale=rationale,
        issue=issue,
    )

    assert proposal.id == "001"
    assert proposal.status == "pending"
    assert proposal.current_version == 1
    assert proposal.proposed_content == proposed
    assert proposal.edit_summary == summary

    # Verify physical files
    p_dir = tmp_store.root_dir / "001"
    assert (p_dir / "original.txt").read_text(encoding="utf-8") == sample_snapshot.content
    assert (p_dir / "proposed.txt").read_text(encoding="utf-8") == proposed
    assert (p_dir / "summary.txt").read_text(encoding="utf-8") == summary
    assert (p_dir / "versions" / "v1" / "proposed.txt").exists()

    # Load from disk
    loaded = tmp_store.load("001")
    assert loaded.id == "001"
    assert loaded.status == "pending"
    assert loaded.proposed_content == proposed


def test_update_content_creates_version(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Version 1",
        edit_summary="Summary 1",
        rationale="Rationale 1",
        issue="Test",
    )
    tmp_store.set_status("001", "approved")

    # Updating content creates v2 and resets status to pending
    updated = tmp_store.update_content("001", new_content="Version 2")
    assert updated.current_version == 2
    assert updated.status == "pending"
    assert len(updated.versions) == 2
    assert updated.proposed_content == "Version 2"

    # Verify both versions exist on disk
    p_dir = tmp_store.root_dir / "001"
    assert (p_dir / "versions" / "v1" / "proposed.txt").read_text(encoding="utf-8") == "Version 1"
    assert (p_dir / "versions" / "v2" / "proposed.txt").read_text(encoding="utf-8") == "Version 2"


def test_update_summary(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Content",
        edit_summary="Initial summary",
        rationale="R",
        issue="Test",
    )

    updated = tmp_store.update_summary("001", "Updated summary")
    assert updated.edit_summary == "Updated summary"
    assert (tmp_store.root_dir / "001" / "summary.txt").read_text(
        encoding="utf-8"
    ) == "Updated summary"


def test_update_summary_resets_approved_to_pending(
    tmp_store: ProposalStore, sample_snapshot: PageSnapshot
):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Content",
        edit_summary="Initial summary",
        rationale="R",
        issue="Test",
    )
    tmp_store.set_status("001", "approved")
    updated = tmp_store.update_summary("001", "New summary")
    assert updated.status == "pending"
    assert tmp_store.load("001").status == "pending"


def test_toggle_bot_flag_resets_approved_to_pending(
    tmp_store: ProposalStore, sample_snapshot: PageSnapshot
):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Content",
        edit_summary="Summary",
        rationale="R",
        issue="Test",
    )
    tmp_store.set_status("001", "approved")
    toggled = tmp_store.toggle_mark_as_bot("001")
    assert toggled.status == "pending"
    assert tmp_store.load("001").status == "pending"


def test_disk_modification_invalidates_approved_status(
    tmp_store: ProposalStore, sample_snapshot: PageSnapshot
):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Content",
        edit_summary="Summary",
        rationale="R",
        issue="Test",
    )
    tmp_store.set_status("001", "approved")
    assert tmp_store.load("001").status == "approved"

    # Modify proposed.txt on disk
    p_dir = tmp_store.root_dir / "001"
    (p_dir / "proposed.txt").write_text("Modified content on disk", encoding="utf-8")

    loaded = tmp_store.load("001")
    assert loaded.status == "pending"
    assert any(d.action == "invalidate_approval" for d in loaded.decisions)


def test_status_transitions_and_decisions(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Content",
        edit_summary="Summary",
        rationale="R",
        issue="Test",
    )

    p = tmp_store.set_status("001", "approved")
    assert p.status == "approved"
    assert len(p.decisions) == 1
    assert p.decisions[0].action == "approved"

    p = tmp_store.set_status("001", "declined", reason="Needs more test cases")
    assert p.status == "declined"
    assert len(p.decisions) == 2
    assert p.decisions[1].reason == "Needs more test cases"

    p = tmp_store.set_status("001", "pending", reason="Reopened")
    assert p.status == "pending"


def test_record_publication(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Content",
        edit_summary="Summary",
        rationale="R",
        issue="Test",
    )

    p = tmp_store.record_publication("001", new_revid=123457, timestamp="2026-02-02T12:00:00Z")
    assert p.status == "published"
    assert p.publish_result is not None
    assert p.publish_result.new_revid == 123457


def test_list_proposals(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    tmp_store.create(sample_snapshot, "C1", "S1", "R1", "Issue 1")
    tmp_store.create(sample_snapshot, "C2", "S2", "R2", "Issue 2")
    tmp_store.set_status("002", "approved")

    pending = tmp_store.list_proposals(status="pending")
    assert len(pending) == 1
    assert pending[0].id == "001"

    approved = tmp_store.list_proposals(status="approved")
    assert len(approved) == 1
    assert approved[0].id == "002"

    all_proposals = tmp_store.list_proposals(status="all")
    assert len(all_proposals) == 2


def test_rebase_base_page(tmp_store: ProposalStore, sample_snapshot: PageSnapshot):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Old proposal",
        edit_summary="Summary",
        rationale="Rationale",
        issue="Issue",
    )
    new_snap = PageSnapshot(
        title=sample_snapshot.title,
        revid=999999,
        timestamp="2026-03-01T00:00:00Z",
        content="New wiki content",
    )
    rebased = tmp_store.rebase_base_page("001", new_snap, "Merged proposal content")
    assert rebased.page.revid == 999999
    assert rebased.current_version == 2
    assert rebased.proposed_content == "Merged proposal content"
    assert rebased.status == "pending"


def test_rebase_base_page_flags_unresolved_conflicts(
    tmp_store: ProposalStore, sample_snapshot: PageSnapshot
):
    tmp_store.create(
        page=sample_snapshot,
        proposed_content="Old proposal",
        edit_summary="Summary",
        rationale="Rationale",
        issue="Issue",
    )
    new_snap = PageSnapshot(
        title=sample_snapshot.title,
        revid=999999,
        timestamp="2026-03-01T00:00:00Z",
        content="New wiki content",
    )
    conflicted = tmp_store.rebase_base_page(
        "001", new_snap, "<<<<<<< ours\nA\n=======\nB\n>>>>>>> theirs\n"
    )
    assert conflicted.status == "pending"
    assert conflicted.decisions[-1].action == "rebase_with_conflicts"
    assert "unresolved" in conflicted.decisions[-1].reason

    resolved = tmp_store.rebase_base_page("001", new_snap, "Merged proposal content")
    assert resolved.decisions[-1].action == "rebase"
    assert "unresolved" not in resolved.decisions[-1].reason


def test_mark_as_bot_autodetection_and_toggle(
    tmp_store: ProposalStore, sample_snapshot: PageSnapshot
):
    # MediaWiki page snapshot -> should default to mark_as_bot=False (critical)
    p_critical = tmp_store.create(
        page=sample_snapshot,  # "MediaWiki:Gadget-wikificator.js"
        proposed_content="Content",
        edit_summary="Summary",
        rationale="Rationale",
        issue="Issue",
    )
    assert p_critical.mark_as_bot is False

    # Mainspace article snapshot -> should default to mark_as_bot=True (routine)
    article_snap = PageSnapshot(
        title="Мінск",
        revid=123,
        timestamp="2026-01-01T00:00:00Z",
        content="Тэкст",
    )
    p_article = tmp_store.create(
        page=article_snap,
        proposed_content="Новы тэкст",
        edit_summary="Summary",
        rationale="Rationale",
        issue="Issue",
    )
    assert p_article.mark_as_bot is True

    # Human can toggle flag
    toggled = tmp_store.toggle_mark_as_bot(p_critical.id)
    assert toggled.mark_as_bot is True
    assert any(d.action == "toggle_bot_flag" for d in toggled.decisions)

    # Toggle back
    toggled_again = tmp_store.toggle_mark_as_bot(p_critical.id)
    assert toggled_again.mark_as_bot is False
