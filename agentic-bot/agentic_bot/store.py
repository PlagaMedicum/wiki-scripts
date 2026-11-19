from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from agentic_bot.merge import has_conflict_markers
from agentic_bot.models import (
    DecisionRecord,
    PageSnapshot,
    Proposal,
    ProposalVersion,
    PublishResult,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProposalStore:
    """Filesystem storage manager for edit proposals."""

    def __init__(self, root_dir: Path | None = None) -> None:
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent / "proposals"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _proposal_dir(self, proposal_id: str) -> Path:
        clean_id = proposal_id.strip().lstrip("#")
        return self.root_dir / f"{int(clean_id):03d}"

    def next_id(self) -> str:
        existing_ids = []
        if self.root_dir.exists():
            for item in self.root_dir.iterdir():
                if item.is_dir() and item.name.isdigit():
                    existing_ids.append(int(item.name))
        next_num = max(existing_ids, default=0) + 1
        return f"{next_num:03d}"

    def create(
        self,
        page: PageSnapshot,
        proposed_content: str,
        edit_summary: str,
        rationale: str,
        issue: str,
        mark_as_bot: bool | None = None,
    ) -> Proposal:
        pid = self.next_id()
        p_dir = self._proposal_dir(pid)
        p_dir.mkdir(parents=True, exist_ok=True)

        if mark_as_bot is None:
            # Critical namespaces (MediaWiki, Module, Template) are too sensitive
            # to hide behind a bot flag; human watchlists must see them.
            is_critical = page.title.startswith(("MediaWiki:", "Module:", "Template:"))
            mark_as_bot = not is_critical

        v1 = ProposalVersion(
            version=1,
            proposed_content=proposed_content,
            edit_summary=edit_summary,
            rationale=rationale,
            created_at=now_iso(),
        )

        proposal = Proposal(
            id=pid,
            status="pending",
            issue=issue,
            page=page,
            current_version=1,
            versions=[v1],
            decisions=[],
            created_at=v1.created_at,
            updated_at=v1.created_at,
            mark_as_bot=mark_as_bot,
        )

        # Write text files
        (p_dir / "original.txt").write_text(page.content, encoding="utf-8")
        (p_dir / "proposed.txt").write_text(proposed_content, encoding="utf-8")
        (p_dir / "summary.txt").write_text(edit_summary, encoding="utf-8")
        (p_dir / "rationale.md").write_text(rationale, encoding="utf-8")

        # Archive v1 in versions directory
        v_dir = p_dir / "versions" / "v1"
        v_dir.mkdir(parents=True, exist_ok=True)
        (v_dir / "proposed.txt").write_text(proposed_content, encoding="utf-8")
        (v_dir / "summary.txt").write_text(edit_summary, encoding="utf-8")
        (v_dir / "rationale.md").write_text(rationale, encoding="utf-8")

        self.save_metadata(proposal)
        return proposal

    def save_metadata(self, proposal: Proposal) -> None:
        p_dir = self._proposal_dir(proposal.id)
        p_dir.mkdir(parents=True, exist_ok=True)
        json_path = p_dir / "proposal.json"

        payload = json.dumps(proposal.to_dict(), ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=p_dir,
            prefix=".proposal.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)

        temp_path.replace(json_path)

    def load(self, proposal_id: str) -> Proposal:
        p_dir = self._proposal_dir(proposal_id)
        json_path = p_dir / "proposal.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Proposal {proposal_id} not found at {json_path}")

        data = json.loads(json_path.read_text(encoding="utf-8"))
        proposal = Proposal.from_dict(data)

        # Read latest content from proposed.txt and summary.txt if present
        proposed_path = p_dir / "proposed.txt"
        summary_path = p_dir / "summary.txt"
        rationale_path = p_dir / "rationale.md"

        if proposed_path.exists() and proposal.versions:
            current_v = proposal.versions[-1]
            disk_content = proposed_path.read_text(encoding="utf-8")
            disk_summary = (
                summary_path.read_text(encoding="utf-8").strip()
                if summary_path.exists()
                else current_v.edit_summary
            )
            disk_rationale = (
                rationale_path.read_text(encoding="utf-8")
                if rationale_path.exists()
                else current_v.rationale
            )
            content_changed = disk_content != current_v.proposed_content
            summary_changed = disk_summary != current_v.edit_summary

            proposal.versions[-1] = ProposalVersion(
                version=current_v.version,
                proposed_content=disk_content,
                edit_summary=disk_summary,
                rationale=disk_rationale,
                created_at=current_v.created_at,
            )

            if (content_changed or summary_changed) and proposal.status == "approved":
                proposal.status = "pending"
                proposal.updated_at = now_iso()
                proposal.decisions.append(
                    DecisionRecord(
                        action="invalidate_approval",
                        timestamp=proposal.updated_at,
                        reason="Content or summary changed after approval",
                    )
                )
                self.save_metadata(proposal)

        return proposal

    def list_proposals(self, status: str | None = None) -> list[Proposal]:
        if not self.root_dir.exists():
            return []

        proposals = []
        for item in sorted(self.root_dir.iterdir()):
            if item.is_dir() and item.name.isdigit():
                try:
                    p = self.load(item.name)
                    if status == "active":
                        matches = p.status not in {"declined", "published"}
                    else:
                        matches = status is None or status.lower() == "all" or p.status == status
                    if matches:
                        proposals.append(p)
                except Exception:
                    continue
        return proposals

    def update_content(
        self,
        proposal_id: str,
        new_content: str,
        new_summary: str | None = None,
        new_rationale: str | None = None,
        action: str = "edit_content",
    ) -> Proposal:
        proposal = self.load(proposal_id)
        p_dir = self._proposal_dir(proposal.id)

        summary = new_summary if new_summary is not None else proposal.edit_summary
        rationale = new_rationale if new_rationale is not None else proposal.rationale

        next_version_num = proposal.current_version + 1
        new_v = ProposalVersion(
            version=next_version_num,
            proposed_content=new_content,
            edit_summary=summary,
            rationale=rationale,
            created_at=now_iso(),
        )

        # Archive new version
        v_dir = p_dir / "versions" / f"v{next_version_num}"
        v_dir.mkdir(parents=True, exist_ok=True)
        (v_dir / "proposed.txt").write_text(new_content, encoding="utf-8")
        (v_dir / "summary.txt").write_text(summary, encoding="utf-8")
        (v_dir / "rationale.md").write_text(rationale, encoding="utf-8")

        # Overwrite current text files
        (p_dir / "proposed.txt").write_text(new_content, encoding="utf-8")
        (p_dir / "summary.txt").write_text(summary, encoding="utf-8")
        (p_dir / "rationale.md").write_text(rationale, encoding="utf-8")

        proposal.versions.append(new_v)
        proposal.current_version = next_version_num
        proposal.status = "pending"
        proposal.updated_at = now_iso()
        proposal.decisions.append(
            DecisionRecord(
                action=action,
                timestamp=proposal.updated_at,
                reason=f"Updated to version {next_version_num}",
            )
        )

        self.save_metadata(proposal)
        return proposal

    def update_summary(self, proposal_id: str, new_summary: str) -> Proposal:
        proposal = self.load(proposal_id)
        p_dir = self._proposal_dir(proposal.id)
        summary = new_summary.strip()
        (p_dir / "summary.txt").write_text(summary, encoding="utf-8")

        # Update in-memory latest version
        if proposal.versions:
            current_v = proposal.versions[-1]
            proposal.versions[-1] = ProposalVersion(
                version=current_v.version,
                proposed_content=current_v.proposed_content,
                edit_summary=summary,
                rationale=current_v.rationale,
                created_at=current_v.created_at,
            )

        proposal.status = "pending"
        proposal.updated_at = now_iso()
        proposal.decisions.append(
            DecisionRecord(
                action="edit_summary",
                timestamp=proposal.updated_at,
                reason="Edit summary updated",
            )
        )
        self.save_metadata(proposal)
        return proposal

    def set_status(self, proposal_id: str, status: str, reason: str = "") -> Proposal:
        proposal = self.load(proposal_id)
        proposal.status = status
        proposal.updated_at = now_iso()
        proposal.decisions.append(
            DecisionRecord(
                action=status,
                timestamp=proposal.updated_at,
                reason=reason,
            )
        )
        self.save_metadata(proposal)
        return proposal

    def rebase_base_page(
        self,
        proposal_id: str,
        new_snapshot: PageSnapshot,
        new_proposed_content: str,
    ) -> Proposal:
        proposal = self.load(proposal_id)
        p_dir = self._proposal_dir(proposal.id)

        (p_dir / "original.txt").write_text(new_snapshot.content, encoding="utf-8")
        (p_dir / "proposed.txt").write_text(new_proposed_content, encoding="utf-8")

        next_version_num = proposal.current_version + 1
        new_v = ProposalVersion(
            version=next_version_num,
            proposed_content=new_proposed_content,
            edit_summary=proposal.edit_summary,
            rationale=proposal.rationale,
            created_at=now_iso(),
        )
        v_dir = p_dir / "versions" / f"v{next_version_num}"
        v_dir.mkdir(parents=True, exist_ok=True)
        (v_dir / "proposed.txt").write_text(new_proposed_content, encoding="utf-8")
        (v_dir / "summary.txt").write_text(proposal.edit_summary, encoding="utf-8")
        (v_dir / "rationale.md").write_text(proposal.rationale, encoding="utf-8")

        proposal.page = new_snapshot
        proposal.versions.append(new_v)
        proposal.current_version = next_version_num
        proposal.updated_at = now_iso()
        proposal.status = "pending"
        if has_conflict_markers(new_proposed_content):
            action = "rebase_with_conflicts"
            reason = (
                f"Rebased onto live revision {new_snapshot.revid} with unresolved "
                "conflict markers (approval blocked until resolved)"
            )
        else:
            action = "rebase"
            reason = f"Rebased onto live revision {new_snapshot.revid}"
        proposal.decisions.append(
            DecisionRecord(
                action=action,
                timestamp=proposal.updated_at,
                reason=reason,
            )
        )
        self.save_metadata(proposal)
        return proposal

    def toggle_mark_as_bot(self, proposal_id: str) -> Proposal:
        proposal = self.load(proposal_id)
        proposal.mark_as_bot = not proposal.mark_as_bot
        if proposal.status == "approved":
            proposal.status = "pending"
        proposal.updated_at = now_iso()
        state_label = "bot" if proposal.mark_as_bot else "human/critical"
        proposal.decisions.append(
            DecisionRecord(
                action="toggle_bot_flag",
                timestamp=proposal.updated_at,
                reason=f"Changed publication flag to {state_label}",
            )
        )
        self.save_metadata(proposal)
        return proposal

    def record_publication(self, proposal_id: str, new_revid: int, timestamp: str) -> Proposal:
        proposal = self.load(proposal_id)
        proposal.status = "published"
        proposal.updated_at = now_iso()
        proposal.publish_result = PublishResult(
            new_revid=new_revid,
            timestamp=timestamp,
            published_version=proposal.current_version,
        )
        proposal.decisions.append(
            DecisionRecord(
                action="publish",
                timestamp=proposal.updated_at,
                reason=f"Published to Wikipedia revision {new_revid}",
            )
        )
        self.save_metadata(proposal)
        return proposal
