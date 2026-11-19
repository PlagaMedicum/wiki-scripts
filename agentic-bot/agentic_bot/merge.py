from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

_CONFLICT_MARKER_RE = re.compile(r"(?m)^(?:<{7}(?:\s|$)|={7}\s*$|>{7}(?:\s|$))")


def has_conflict_markers(text: str) -> bool:
    """Return True when text carries unresolved merge conflict markers."""
    return bool(_CONFLICT_MARKER_RE.search(text))


def three_way_merge(
    base_text: str,
    proposed_text: str,
    live_text: str,
    base_label: str = "original",
    proposed_label: str = "proposal",
    live_label: str = "wiki-current",
) -> tuple[str, bool]:
    """Perform a standard 3-way merge between base, proposed, and live wiki text.

    Returns:
        tuple[str, bool]: (merged_text, has_conflicts)
    """
    if proposed_text == live_text:
        return proposed_text, False

    if base_text == live_text:
        # Wiki has not changed since proposal was prepared
        return proposed_text, False

    # Create temporary files for git merge-file:
    # Syntax: git merge-file -p <file1: proposed> <orig-file: base> <file2: live>
    with (
        tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f_proposed,
        tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f_base,
        tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f_live,
    ):
        f_proposed.write(proposed_text)
        f_base.write(base_text)
        f_live.write(live_text)

        p_proposed = Path(f_proposed.name)
        p_base = Path(f_base.name)
        p_live = Path(f_live.name)

    try:
        proc = subprocess.run(
            [
                "git",
                "merge-file",
                "-p",
                "-L",
                proposed_label,
                "-L",
                base_label,
                "-L",
                live_label,
                str(p_proposed),
                str(p_base),
                str(p_live),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode < 0 or proc.returncode > 127:
            raise RuntimeError("git merge-file failed; proposal was not rebased.")
        merged_text = proc.stdout
        has_conflicts = proc.returncode != 0
        return merged_text, has_conflicts
    finally:
        for p in (p_proposed, p_base, p_live):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
