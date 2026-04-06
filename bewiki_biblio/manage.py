from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from bewiki_biblio.models import SourceScaffold
from bewiki_biblio.specs import (
    DEFAULT_PAGE_PATTERNS,
    DEFAULT_REJECT_PATTERNS,
    PERSISTENT_SOURCE_FILENAMES,
    RUNTIME_STATE_FILENAMES,
    project_root,
    source_root,
    validate_source_id,
    validate_source_layouts,
)
from bewiki_biblio.ui import AppUI


def _csv_default(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_list(values: tuple[str, ...]) -> str:
    if not values:
        return "[]"
    lines = ["["]
    for value in values:
        lines.append(f"  {_toml_string(value)},")
    lines.append("]")
    return "\n".join(lines)


def render_source_toml(scaffold: SourceScaffold) -> str:
    lines = [
        "[source]",
        f"id = {_toml_string(scaffold.source_id)}",
        f"name = {_toml_string(scaffold.name)}",
        f"site_lang = {_toml_string(scaffold.site_lang)}",
        f"family = {_toml_string(scaffold.family)}",
        "",
        "[search]",
        f"insource_terms = {_toml_list(scaffold.insource_terms)}",
        f"isbns = {_toml_list(scaffold.isbns)}",
        f"keywords = {_toml_list(scaffold.keywords)}",
        "",
        "[candidate]",
        f"must_contain_all = {_toml_list(scaffold.candidate_all)}",
        f"must_contain_any = {_toml_list(scaffold.candidate_any)}",
        "",
        "[replacement]",
        f"template_name = {_toml_string(scaffold.template_name)}",
        f"without_pages = {_toml_string(scaffold.template_without_pages)}",
        f"with_pages = {_toml_string(scaffold.template_with_pages)}",
        "",
        "[summary]",
        f"default_format = {_toml_string(scaffold.default_summary_format)}",
        "",
        "[pages]",
        f"patterns = {_toml_list(scaffold.page_patterns)}",
        f"reject_patterns = {_toml_list(scaffold.reject_patterns)}",
        "",
        "[normalization]",
        "strip_nowiki = true",
        "resolve_wikilinks = true",
        "strip_formatting = true",
        "normalize_nbsp = true",
        "normalize_dashes = true",
        "collapse_whitespace = true",
        "",
        "[macros]",
        '# Add bibliography-specific fragments here, e.g. TITLE = "..."',
        "",
        "# Example broad regex rule skeleton:",
        "# [[regex_rules]]",
        '# name = "example_rule"',
        '# pattern = "(?m)^(?P<prefix>{{LIST_PREFIX}})...$"',
        '# replacement = "{prefix}{template}"',
        '# flags = "VERBOSE|UNICODE|MULTILINE"',
        "# enabled = true",
        "",
    ]
    return "\n".join(lines)


def render_source_readme(scaffold: SourceScaffold) -> str:
    description = scaffold.description or (
        f"This source scaffolds bibliography replacement rules for {scaffold.name} on be.wikipedia.org."
    )
    return "\n".join(
        [
            f"# `{scaffold.source_id}`",
            "",
            description,
            "",
            "## Search Terms",
            "",
            f"- Insource terms: {_csv_default(scaffold.insource_terms) or 'none'}",
            f"- ISBNs: {_csv_default(scaffold.isbns) or 'none'}",
            f"- Keywords: {_csv_default(scaffold.keywords) or 'none'}",
            "",
            "## Replacement Forms",
            "",
            f"- Without pages: `{scaffold.template_without_pages}`",
            f"- With pages: `{scaffold.template_with_pages}`",
            "",
            "## Candidate Detection",
            "",
            f"- Must contain all: {_csv_default(scaffold.candidate_all) or 'none'}",
            f"- Must contain any: {_csv_default(scaffold.candidate_any) or 'none'}",
            "",
            "## Default Edit Summary",
            "",
            f"- `{scaffold.default_summary_format.replace('{template_name}', scaffold.template_name)}`",
            "",
            "## Notes",
            "",
            "- Add bibliography-specific macros in `source.toml` under `[macros]`.",
            "- Add broad regex rules in `[[regex_rules]]`.",
            "- `rules.json`, `review_variants.json`, and `ignored_variants.json` are local runtime state managed by the workflow.",
            "- The runtime JSON files are gitignored and do not need to be committed.",
            "",
        ]
    )


def _required_text(ui: AppUI, label: str, *, default: str | None = None) -> str:
    while True:
        value = ui.prompt_text(label, default=default)
        if value.strip():
            return value.strip()
        ui.warn(f"{label} is required.")


def _prompt_search_terms(ui: AppUI) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    while True:
        insource_terms = ui.prompt_csv("Insource terms (comma-separated)")
        isbns = ui.prompt_csv("ISBNs (comma-separated)")
        keywords = ui.prompt_csv("Keywords (comma-separated)")
        if insource_terms or isbns or keywords:
            return insource_terms, isbns, keywords
        ui.warn("Add at least one insource term, ISBN, or keyword.")


def _dedupe_terms(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for group in groups:
        for term in group:
            cleaned = term.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                values.append(cleaned)
    return tuple(values)


def guess_candidate_defaults(
    *,
    insource_terms: tuple[str, ...],
    isbns: tuple[str, ...],
    keywords: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    candidate_all = (keywords[0],) if keywords else ((insource_terms[0],) if insource_terms else ())
    remaining_text_terms = tuple(
        term
        for term in _dedupe_terms(insource_terms, keywords)
        if term not in candidate_all
    )
    candidate_any = _dedupe_terms(isbns, remaining_text_terms)
    return candidate_all, candidate_any


def _prompt_candidate_terms(
    ui: AppUI,
    *,
    insource_terms: tuple[str, ...],
    isbns: tuple[str, ...],
    keywords: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    default_all, default_any = guess_candidate_defaults(
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
    )
    ui.info("Candidate defaults are guessed from your search terms. Press Enter to accept or edit them.")
    ui.info(f"Guessed must_contain_all: {_csv_default(default_all) or 'none'}")
    ui.info(f"Guessed must_contain_any: {_csv_default(default_any) or 'none'}")

    while True:
        candidate_all = ui.prompt_csv(
            "Candidate must contain all (comma-separated)",
            default=default_all or None,
        )
        candidate_any = ui.prompt_csv(
            "Candidate must contain any (comma-separated)",
            default=default_any or None,
        )
        if candidate_all or candidate_any:
            return candidate_all, candidate_any
        ui.warn("Add at least one candidate term in must_contain_all or must_contain_any.")


def _collect_scaffold(ui: AppUI, root: Path) -> SourceScaffold:
    name = _required_text(ui, "Source name")

    while True:
        source_id = _required_text(ui, "Source ID (folder name, e.g. source-id)")
        try:
            validate_source_id(source_id)
        except ValueError as exc:
            ui.warn(str(exc))
            continue
        if (source_root(root) / source_id).exists():
            ui.warn(f"sources/{source_id} already exists.")
            continue
        break

    site_lang = _required_text(ui, "Site language", default="be")
    family = _required_text(ui, "Family", default="wikipedia")
    template_name = _required_text(ui, "Template name")

    without_pages = _required_text(
        ui,
        "Template without pages",
        default=f"{{{{{template_name}}}}}",
    )
    with_pages = _required_text(
        ui,
        "Template with pages ({pages} placeholder required)",
        default=f"{{{{{template_name}|{{pages}}}}}}",
    )
    while "{pages}" not in with_pages:
        ui.warn("Template with pages must include {pages}.")
        with_pages = _required_text(
            ui,
            "Template with pages ({pages} placeholder required)",
            default=with_pages,
        )

    default_summary = _required_text(
        ui,
        "Default edit summary ({template_name} placeholder required)",
        default="Замена бібліяграфічнай спасылкі шаблонам {{{template_name}}}",
    )
    while "{template_name}" not in default_summary:
        ui.warn("Default edit summary must include {template_name}.")
        default_summary = _required_text(
            ui,
            "Default edit summary ({template_name} placeholder required)",
            default=default_summary,
        )

    insource_terms, isbns, keywords = _prompt_search_terms(ui)
    candidate_all, candidate_any = _prompt_candidate_terms(
        ui,
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
    )

    description = ui.prompt_text(
        "README summary line",
        default=f"This source targets {name} bibliography references on be.wikipedia.org.",
    )

    return SourceScaffold(
        source_id=source_id,
        name=name,
        site_lang=site_lang,
        family=family,
        template_name=template_name,
        template_without_pages=without_pages,
        template_with_pages=with_pages,
        default_summary_format=default_summary,
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
        candidate_all=candidate_all,
        candidate_any=candidate_any,
        page_patterns=DEFAULT_PAGE_PATTERNS,
        reject_patterns=DEFAULT_REJECT_PATTERNS,
        description=description,
    )


def _write_source_files(root: Path, scaffold: SourceScaffold) -> Path:
    source_dir = source_root(root) / scaffold.source_id
    source_dir.mkdir(parents=True, exist_ok=False)

    (source_dir / "source.toml").write_text(render_source_toml(scaffold), encoding="utf-8")
    (source_dir / "rules.json").write_text("[]\n", encoding="utf-8")
    (source_dir / "review_variants.json").write_text("[]\n", encoding="utf-8")
    (source_dir / "ignored_variants.json").write_text("[]\n", encoding="utf-8")
    (source_dir / "README.md").write_text(render_source_readme(scaffold), encoding="utf-8")
    return source_dir


def add_source(ui: AppUI, root: Path | None = None) -> int:
    actual_root = root or project_root()
    scaffold = _collect_scaffold(ui, actual_root)

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

    if not ui.confirm("Create these files?", default=True):
        ui.warn("Source creation cancelled.")
        return 1

    source_dir = _write_source_files(actual_root, scaffold)
    ui.info(f"[created] {source_dir}")
    return 0


def validate_sources(ui: AppUI, root: Path | None = None) -> int:
    actual_root = root or source_root().parent
    issues = validate_source_layouts(root=actual_root)
    if not issues:
        table = Table(title="Validated source layouts")
        table.add_column("Source", style="" if ui.no_color else "bold cyan")
        table.add_column("Files")
        for source_dir in sorted(source_root(actual_root).iterdir()):
            if source_dir.is_dir():
                table.add_row(
                    source_dir.name,
                    f"{', '.join(PERSISTENT_SOURCE_FILENAMES)} "
                    f"(runtime state: {', '.join(RUNTIME_STATE_FILENAMES)})",
                )
        ui.print(table)
        ui.info("[ok] Source layouts and filenames are valid.")
        return 0

    table = Table(title="Source validation issues")
    table.add_column("Source", style="" if ui.no_color else "bold cyan")
    table.add_column("Path")
    table.add_column("Issue")
    table.add_column("Suggestion")
    for issue in issues:
        table.add_row(
            issue.source_name,
            str(issue.path.relative_to(actual_root)),
            issue.message,
            issue.suggestion or "",
        )
    ui.print(table)
    return 1
