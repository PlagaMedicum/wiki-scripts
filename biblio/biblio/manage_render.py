from __future__ import annotations

import json

from biblio.models import (
    SourceArgumentExtractorScaffold,
    SourceScaffold,
    SourceVolumeScaffold,
    TemplateRoleParams,
)


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


def _render_volume_block(volume: SourceVolumeScaffold) -> list[str]:
    lines = [
        "[[volumes]]",
        f"volume = {_toml_string(volume.volume)}",
        f"name = {_toml_string(volume.name)}",
        f"aliases = {_toml_list(volume.aliases)}",
        f"insource_terms = {_toml_list(volume.insource_terms)}",
        f"isbns = {_toml_list(volume.isbns)}",
        f"keywords = {_toml_list(volume.keywords)}",
        f"must_contain_all = {_toml_list(volume.candidate_all)}",
        f"must_contain_any = {_toml_list(volume.candidate_any)}",
    ]
    if volume.short_ref_ref and volume.short_ref_year:
        lines.extend(
            [
                "",
                "[volumes.short_ref]",
                f"ref = {_toml_string(volume.short_ref_ref)}",
                f"year = {_toml_string(volume.short_ref_year)}",
            ]
        )
    lines.extend(
        [
            "",
            "[volumes.macros]",
            '# VOLUME = "..."',
            '# SOURCE_ISBN = "..."',
            '# TOM_PARAM = "..."',
        ]
    )
    return lines


def _role_param_lookup(
    values: tuple[TemplateRoleParams, ...],
) -> dict[str, TemplateRoleParams]:
    return {value.role: value for value in values}


def _render_argument_extractor(extractor: SourceArgumentExtractorScaffold) -> list[str]:
    return [
        f"[argument_extractors.{extractor.name}]",
        f"template_params = {_toml_list(extractor.template_params)}",
        f"normalizer = {_toml_string(extractor.normalizer)}",
    ]


def _render_template_role_hints(scaffold: SourceScaffold) -> list[str]:
    lookup = _role_param_lookup(scaffold.template_role_params)
    lines: list[str] = []
    if scaffold.imported_from_title:
        lines.append(f"# Imported from template page: {scaffold.imported_from_title}")
    if lookup:
        lines.append("# Imported template parameter aliases:")
        for role in ("volume", "entry", "author", "pages", "responsible", "ref"):
            binding = lookup.get(role)
            if not binding or not binding.params:
                continue
            default_note = f" (default: {binding.default})" if binding.default else ""
            lines.append(f"# - {role}: {', '.join(binding.params)}{default_note}")
    if scaffold.import_notes:
        lines.append("# Imported notes:")
        for note in scaffold.import_notes:
            lines.append(f"# - {note}")
    return lines


def render_source_toml(scaffold: SourceScaffold) -> str:
    template_without_pages = scaffold.template_without_pages
    template_with_pages = scaffold.template_with_pages
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
        f"without_pages = {_toml_string(template_without_pages)}",
        f"with_pages = {_toml_string(template_with_pages)}",
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
    ]
    hint_lines = _render_template_role_hints(scaffold)
    if hint_lines:
        lines.extend(hint_lines)
        lines.append("")
    for extractor in scaffold.argument_extractors:
        lines.extend(_render_argument_extractor(extractor))
        lines.append("")
    lines.extend(
        [
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
    )
    for volume in scaffold.volumes:
        lines.extend(_render_volume_block(volume))
        lines.append("")
    return "\n".join(lines)
