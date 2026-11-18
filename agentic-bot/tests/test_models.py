from __future__ import annotations

from agentic_bot.models import (
    DecisionRecord,
    PageSnapshot,
    Proposal,
    ProposalVersion,
    PublishResult,
)


def test_page_snapshot_roundtrip():
    snap = PageSnapshot(
        title="Вікіпедыя:Праект",
        revid=999,
        timestamp="2026-02-01T10:00:00Z",
        content="Тэкст старонкі",
    )
    d = snap.to_dict()
    loaded = PageSnapshot.from_dict(d)
    assert loaded == snap
    assert loaded.title == "Вікіпедыя:Праект"
    assert loaded.revid == 999


def test_proposal_version_roundtrip():
    v = ProposalVersion(
        version=1,
        proposed_content="Новы змест",
        edit_summary="Выпраўленне",
        rationale="Тлумачэнне",
        created_at="2026-02-01T10:05:00Z",
    )
    d = v.to_dict()
    loaded = ProposalVersion.from_dict(d)
    assert loaded == v


def test_proposal_full_roundtrip():
    snap = PageSnapshot(
        title="Test Page",
        revid=100,
        timestamp="2026-01-01T00:00:00Z",
        content="Old",
    )
    v1 = ProposalVersion(1, "New v1", "Summary v1", "Rationale v1", "2026-01-01T01:00:00Z")
    v2 = ProposalVersion(2, "New v2", "Summary v2", "Rationale v2", "2026-01-01T02:00:00Z")
    dec = DecisionRecord("approve", "2026-01-01T03:00:00Z", "Looks good")
    pub = PublishResult(101, "2026-01-01T04:00:00Z", 2)

    proposal = Proposal(
        id="001",
        status="published",
        issue="Test issue",
        page=snap,
        current_version=2,
        versions=[v1, v2],
        decisions=[dec],
        publish_result=pub,
        created_at="2026-01-01T01:00:00Z",
        updated_at="2026-01-01T04:00:00Z",
        mark_as_bot=False,
    )

    d = proposal.to_dict()
    assert d["mark_as_bot"] is False
    loaded = Proposal.from_dict(d)

    assert loaded.id == "001"
    assert loaded.status == "published"
    assert loaded.current_version == 2
    assert loaded.mark_as_bot is False
    assert loaded.latest_version.proposed_content == "New v2"
    assert loaded.publish_result is not None
    assert loaded.publish_result.new_revid == 101
