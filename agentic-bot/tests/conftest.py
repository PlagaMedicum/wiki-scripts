from __future__ import annotations

from pathlib import Path

import pytest
from agentic_bot.models import PageSnapshot
from agentic_bot.store import ProposalStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> ProposalStore:
    return ProposalStore(root_dir=tmp_path / "proposals")


@pytest.fixture
def sample_snapshot() -> PageSnapshot:
    return PageSnapshot(
        title="MediaWiki:Gadget-wikificator.js",
        revid=123456,
        timestamp="2026-01-15T12:00:00Z",
        content="function wikify(text) {\n  return text.replace(/--/g, '—');\n}\n",
        wiki="be.wikipedia.org",
        site_lang="be",
        family="wikipedia",
    )
