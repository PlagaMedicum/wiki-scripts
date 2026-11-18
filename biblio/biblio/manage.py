from __future__ import annotations

from pathlib import Path

from biblio.manage_questions import collect_scaffold_plain
from biblio.manage_questions import (
    guess_candidate_defaults as _guess_candidate_defaults,
)
from biblio.manage_reports import (
    render_add_source_preview,
    render_add_source_summary,
)
from biblio.manage_reports import (
    validate_sources as _validate_sources,
)
from biblio.manage_write import write_source_files
from biblio.specs import project_root
from biblio.ui import AppUI

guess_candidate_defaults = _guess_candidate_defaults

__all__ = ["add_source", "guess_candidate_defaults", "validate_sources"]


def add_source(ui: AppUI, root: Path | None = None, *, plain: bool = False) -> int:
    actual_root = root or project_root()
    if plain or not ui.console.is_terminal:
        scaffold = collect_scaffold_plain(ui, actual_root)
    else:
        from biblio.manage_tui import collect_scaffold_tui

        scaffold = collect_scaffold_tui(ui, actual_root)

    render_add_source_summary(ui, scaffold)
    render_add_source_preview(ui, scaffold)
    if not ui.confirm("Create these files?", default=True):
        ui.warn("Source creation cancelled.")
        return 1

    source_dir = write_source_files(actual_root, scaffold)
    ui.info(f"[created] {source_dir}")
    return 0


def validate_sources(ui: AppUI, root: Path | None = None) -> int:
    actual_root = root or project_root()
    return _validate_sources(ui, actual_root)
