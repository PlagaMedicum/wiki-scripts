from __future__ import annotations

import os
from unittest.mock import patch

from agentic_bot.editor import edit_text_in_editor, get_preferred_editor


def test_get_preferred_editor_fallback():
    with patch.dict(os.environ, {}, clear=True):
        assert get_preferred_editor() == "vim"


def test_get_preferred_editor_visual():
    with patch.dict(os.environ, {"VISUAL": "nano", "EDITOR": "emacs"}):
        assert get_preferred_editor() == "nano"


def test_edit_text_in_editor_no_change(tmp_path):
    # Simulate editor that does not modify the file (e.g. `true` command)
    with patch("agentic_bot.editor.get_preferred_editor", return_value="true"):
        content, modified = edit_text_in_editor("Original text")
        assert content == "Original text"
        assert modified is False


def test_edit_text_in_editor_with_modification(tmp_path):
    import subprocess
    from pathlib import Path

    def fake_run(cmd, **kwargs):
        # cmd is [editor, path_str]
        path = Path(cmd[1])
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing + "\nДадатковы радок.", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode=0)

    with patch("agentic_bot.editor.get_preferred_editor", return_value="mock_vim"):
        with patch("subprocess.run", side_effect=fake_run):
            content, modified = edit_text_in_editor("Пачатковы тэкст.")
            assert modified is True
            assert "Дадатковы радок." in content
