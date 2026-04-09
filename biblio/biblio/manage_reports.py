from __future__ import annotations

from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from biblio.models import SourceScaffold, SourceValidationIssue
from biblio.specs import (
    PERSISTENT_SOURCE_FILENAMES,
    RUNTIME_STATE_FILENAMES,
    source_root,
    validate_source_layouts,
)
from biblio.ui import AppUI


def _csv_default(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def render_add_source_summary(ui: AppUI, scaffold: SourceScaffold) -> None:
    summary = Table.grid(padding=(0, 1))
    summary.add_column(style="" if ui.no_color else "bold cyan")
    summary.add_column()
    summary.add_row("Source ID", scaffold.source_id)
    summary.add_row("Name", scaffold.name)
    summary.add_row("Tracked files", ", ".join(PERSISTENT_SOURCE_FILENAMES))
    summary.add_row("Local runtime files", ", ".join(RUNTIME_STATE_FILENAMES))
    summary.add_row("Template", scaffold.template_name)
    summary.add_row("Insource terms", _csv_default(scaffold.insource_terms) or "none")
    summary.add_row("Candidate all", _csv_default(scaffold.candidate_all) or "none")
    summary.add_row("Candidate any", _csv_default(scaffold.candidate_any) or "none")
    ui.print(Panel(summary, title="New source scaffold", border_style="blue"))


def render_validation_success(ui: AppUI, root: Path) -> None:
    table = Table(title="Validated source layouts")
    table.add_column("Source", style="" if ui.no_color else "bold cyan")
    table.add_column("Files")
    for source_dir in sorted(source_root(root).iterdir()):
        if source_dir.is_dir():
            table.add_row(
                source_dir.name,
                f"{', '.join(PERSISTENT_SOURCE_FILENAMES)} "
                f"(runtime state: {', '.join(RUNTIME_STATE_FILENAMES)})",
            )
    ui.print(table)
    ui.info("[ok] Source layouts and filenames are valid.")


def render_validation_issues(
    ui: AppUI,
    root: Path,
    issues: list[SourceValidationIssue],
) -> None:
    table = Table(title="Source validation issues")
    table.add_column("Source", style="" if ui.no_color else "bold cyan")
    table.add_column("Path")
    table.add_column("Issue")
    table.add_column("Suggestion")
    for issue in issues:
        table.add_row(
            issue.source_name,
            str(issue.path.relative_to(root)),
            issue.message,
            issue.suggestion or "",
        )
    ui.print(table)


def validate_sources(ui: AppUI, root: Path) -> int:
    issues = validate_source_layouts(root=root)
    if not issues:
        render_validation_success(ui, root)
        return 0

    render_validation_issues(ui, root, issues)
    return 1
