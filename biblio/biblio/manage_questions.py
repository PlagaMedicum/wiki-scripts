from __future__ import annotations

from pathlib import Path

from biblio.models import SourceScaffold, SourceVolumeScaffold
from biblio.specs import (
    DEFAULT_PAGE_PATTERNS,
    DEFAULT_REJECT_PATTERNS,
    source_root,
    validate_source_id,
)
from biblio.ui import AppUI


def _csv_default(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _required_text(ui: AppUI, label: str, *, default: str | None = None) -> str:
    while True:
        value = ui.prompt_text(label, default=default)
        if value.strip():
            return value.strip()
        ui.warn(f"{label} is required.")


def _label_with_prefix(prefix: str, label: str) -> str:
    return f"{prefix}{label}" if prefix else label


def _prompt_search_terms(
    ui: AppUI,
    *,
    label_prefix: str = "",
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    while True:
        insource_terms = ui.prompt_csv(
            _label_with_prefix(label_prefix, "Insource terms (comma-separated)")
        )
        isbns = ui.prompt_csv(_label_with_prefix(label_prefix, "ISBNs (comma-separated)"))
        keywords = ui.prompt_csv(_label_with_prefix(label_prefix, "Keywords (comma-separated)"))
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
        term for term in _dedupe_terms(insource_terms, keywords) if term not in candidate_all
    )
    candidate_any = _dedupe_terms(isbns, remaining_text_terms)
    return candidate_all, candidate_any


def _prompt_candidate_terms(
    ui: AppUI,
    *,
    insource_terms: tuple[str, ...],
    isbns: tuple[str, ...],
    keywords: tuple[str, ...],
    label_prefix: str = "",
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    default_all, default_any = guess_candidate_defaults(
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
    )
    ui.info(
        "Candidate defaults are guessed from your search terms. Press Enter to accept or edit them."
    )
    ui.info(f"Guessed must_contain_all: {_csv_default(default_all) or 'none'}")
    ui.info(f"Guessed must_contain_any: {_csv_default(default_any) or 'none'}")

    while True:
        candidate_all = ui.prompt_csv(
            _label_with_prefix(label_prefix, "Candidate must contain all (comma-separated)"),
            default=default_all or None,
        )
        candidate_any = ui.prompt_csv(
            _label_with_prefix(label_prefix, "Candidate must contain any (comma-separated)"),
            default=default_any or None,
        )
        if candidate_all or candidate_any:
            return candidate_all, candidate_any
        ui.warn("Add at least one candidate term in must_contain_all or must_contain_any.")


def _prompt_volume_scaffolds(ui: AppUI) -> tuple[SourceVolumeScaffold, ...]:
    count = ui.prompt_int("How many volume entries?", default=2, minimum=1)
    volumes: list[SourceVolumeScaffold] = []
    for index in range(1, count + 1):
        prefix = f"Volume {index} "
        ui.info(f"Configure volume {index}/{count}.")
        name = _required_text(ui, _label_with_prefix(prefix, "name"))
        volume = _required_text(
            ui,
            _label_with_prefix(prefix, "template parameter"),
            default=str(index),
        )
        aliases = ui.prompt_csv(
            _label_with_prefix(prefix, "aliases (comma-separated)"),
        )
        insource_terms, isbns, keywords = _prompt_search_terms(ui, label_prefix=prefix)
        candidate_all, candidate_any = _prompt_candidate_terms(
            ui,
            insource_terms=insource_terms,
            isbns=isbns,
            keywords=keywords,
            label_prefix=prefix,
        )
        short_ref_ref = ui.prompt_optional_text(
            _label_with_prefix(prefix, "short ref target (blank = none)")
        )
        short_ref_year = None
        if short_ref_ref:
            short_ref_year = _required_text(ui, _label_with_prefix(prefix, "short ref year"))
        volumes.append(
            SourceVolumeScaffold(
                volume=volume,
                name=name,
                aliases=aliases,
                insource_terms=insource_terms,
                isbns=isbns,
                keywords=keywords,
                candidate_all=candidate_all,
                candidate_any=candidate_any,
                short_ref_ref=short_ref_ref,
                short_ref_year=short_ref_year,
            )
        )
    return tuple(volumes)


def collect_scaffold_plain(ui: AppUI, root: Path) -> SourceScaffold:
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
    single_volume = ui.confirm("Single-volume source?", default=True)
    template_name = _required_text(ui, "Template name")

    default_without_pages = f"{{{{{template_name}}}}}"
    default_with_pages = f"{{{{{template_name}|{{pages}}}}}}"
    if not single_volume:
        default_without_pages = "{{" + template_name + "|{volume}}}"
        default_with_pages = "{{" + template_name + "|{volume}|{pages}}}"

    without_pages = _required_text(
        ui,
        "Template without pages",
        default=default_without_pages,
    )
    with_pages = _required_text(
        ui,
        "Template with pages ({pages} placeholder required)",
        default=default_with_pages,
    )
    while "{pages}" not in with_pages:
        ui.warn("Template with pages must include {pages}.")
        with_pages = _required_text(
            ui,
            "Template with pages ({pages} placeholder required)",
            default=with_pages,
        )
    if not single_volume:
        while "{volume}" not in without_pages or "{volume}" not in with_pages:
            ui.warn("Merged multi-volume templates must include {volume}.")
            without_pages = _required_text(
                ui,
                "Template without pages",
                default=without_pages,
            )
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

    search_label_prefix = "" if single_volume else "Shared "
    insource_terms, isbns, keywords = _prompt_search_terms(ui, label_prefix=search_label_prefix)
    candidate_all, candidate_any = _prompt_candidate_terms(
        ui,
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
        label_prefix=search_label_prefix,
    )
    volumes = () if single_volume else _prompt_volume_scaffolds(ui)

    description = ui.prompt_text(
        "README summary line",
        default=(
            f"This source targets {name} bibliography references on be.wikipedia.org."
            if single_volume
            else f"This source targets merged multi-volume bibliography references for {name} on be.wikipedia.org."
        ),
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
        volumes=volumes,
    )


collect_scaffold = collect_scaffold_plain
