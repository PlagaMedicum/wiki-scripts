from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
from agentic_bot.merge import three_way_merge


def test_three_way_merge_clean():
    base = "line 1\nline 2\nline 3\nline 4\n"
    # Proposal modifies line 2
    proposed = "line 1\nline 2 (proposal fix)\nline 3\nline 4\n"
    # Live wiki modified line 4 (earlier published proposal)
    live = "line 1\nline 2\nline 3\nline 4 (wiki update)\n"

    merged, has_conflicts = three_way_merge(base, proposed, live)
    assert not has_conflicts
    assert "line 2 (proposal fix)" in merged
    assert "line 4 (wiki update)" in merged


def test_three_way_merge_with_conflict():
    base = "original line\n"
    proposed = "proposal line\n"
    live = "wiki conflicting line\n"

    merged, has_conflicts = three_way_merge(base, proposed, live)
    assert has_conflicts
    assert "<<<<<<<" in merged
    assert "=======" in merged
    assert ">>>>>>>" in merged


def test_three_way_merge_unchanged():
    base = "same text\n"
    proposed = "modified text\n"
    live = "same text\n"

    merged, has_conflicts = three_way_merge(base, proposed, live)
    assert not has_conflicts
    assert merged == "modified text\n"


def test_three_way_merge_reports_command_failure():
    failed = CompletedProcess(args=["git", "merge-file"], returncode=255, stdout="", stderr="error")
    with patch("agentic_bot.merge.subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match="merge-file failed"):
            three_way_merge("base\n", "proposal\n", "live\n")
