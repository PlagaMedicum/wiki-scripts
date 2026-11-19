from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path


def get_preferred_editor() -> str:
    """Resolve user's preferred editor from environment, falling back to vim."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"
    return editor.strip()


def edit_text_in_editor(content: str, suffix: str = ".txt") -> tuple[str, bool]:
    """Open content in the user's preferred editor.

    Returns:
        tuple[str, bool]: (resulting_content, was_modified)
    """
    editor = get_preferred_editor()
    temp_fd, temp_path_str = tempfile.mkstemp(suffix=suffix, prefix="agentic_bot_")
    temp_path = Path(temp_path_str)

    try:
        with open(temp_fd, "w", encoding="utf-8") as handle:
            handle.write(content)

        try:
            proc = subprocess.run([*shlex.split(editor), str(temp_path)], check=False)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not start editor: {exc}") from exc
        if proc.returncode != 0:
            raise ValueError(f"editor exited with status {proc.returncode}")

        new_content = temp_path.read_text(encoding="utf-8")
        was_modified = new_content != content
        return new_content, was_modified
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
