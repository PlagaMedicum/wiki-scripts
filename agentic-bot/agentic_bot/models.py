from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PageSnapshot:
    """Frozen snapshot of a wiki page at proposal time."""

    title: str
    revid: int
    timestamp: str
    content: str
    wiki: str = "be.wikipedia.org"
    site_lang: str = "be"
    family: str = "wikipedia"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageSnapshot:
        return cls(
            title=str(data["title"]),
            revid=int(data["revid"]),
            timestamp=str(data["timestamp"]),
            content=str(data.get("content", "")),
            wiki=str(data.get("wiki", "be.wikipedia.org")),
            site_lang=str(data.get("site_lang", "be")),
            family=str(data.get("family", "wikipedia")),
        )


@dataclass(frozen=True)
class ProposalVersion:
    """One version of proposed page content, summary, and rationale."""

    version: int
    proposed_content: str
    edit_summary: str
    rationale: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposalVersion:
        return cls(
            version=int(data["version"]),
            proposed_content=str(data["proposed_content"]),
            edit_summary=str(data["edit_summary"]),
            rationale=str(data["rationale"]),
            created_at=str(data["created_at"]),
        )


@dataclass(frozen=True)
class DecisionRecord:
    """A record of an operator or system action on the proposal."""

    action: str
    timestamp: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionRecord:
        return cls(
            action=str(data["action"]),
            timestamp=str(data["timestamp"]),
            reason=str(data.get("reason", "")),
        )


@dataclass(frozen=True)
class PublishResult:
    """Result of publishing a proposal to MediaWiki."""

    new_revid: int
    timestamp: str
    published_version: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublishResult:
        return cls(
            new_revid=int(data["new_revid"]),
            timestamp=str(data["timestamp"]),
            published_version=int(data["published_version"]),
        )


@dataclass
class Proposal:
    """An edit proposal with complete history and safety state."""

    id: str
    status: str  # pending | approved | declined | published | conflict
    issue: str
    page: PageSnapshot
    current_version: int
    versions: list[ProposalVersion]
    decisions: list[DecisionRecord]
    created_at: str
    updated_at: str
    mark_as_bot: bool = (
        False  # False = critical edit (visible to watchlists), True = routine bot edit
    )
    publish_result: PublishResult | None = None

    @property
    def latest_version(self) -> ProposalVersion:
        if not self.versions:
            raise ValueError(f"Proposal {self.id} has no versions")
        return self.versions[-1]

    @property
    def proposed_content(self) -> str:
        return self.latest_version.proposed_content

    @property
    def edit_summary(self) -> str:
        return self.latest_version.edit_summary

    @property
    def rationale(self) -> str:
        return self.latest_version.rationale

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "issue": self.issue,
            "page": self.page.to_dict(),
            "current_version": self.current_version,
            "versions": [v.to_dict() for v in self.versions],
            "decisions": [d.to_dict() for d in self.decisions],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "mark_as_bot": self.mark_as_bot,
            "publish_result": self.publish_result.to_dict() if self.publish_result else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Proposal:
        return cls(
            id=str(data["id"]),
            status=str(data["status"]),
            issue=str(data["issue"]),
            page=PageSnapshot.from_dict(data["page"]),
            current_version=int(data["current_version"]),
            versions=[ProposalVersion.from_dict(v) for v in data.get("versions", [])],
            decisions=[DecisionRecord.from_dict(d) for d in data.get("decisions", [])],
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            mark_as_bot=bool(data.get("mark_as_bot", False)),
            publish_result=(
                PublishResult.from_dict(data["publish_result"])
                if data.get("publish_result")
                else None
            ),
        )
