from __future__ import annotations

import json

from biblio.models import SourceScaffold


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
        "This source scaffolds bibliography replacement rules for "
        f"{scaffold.name} on be.wikipedia.org."
    )
    default_summary = scaffold.default_summary_format.replace(
        "{template_name}",
        scaffold.template_name,
    )
    return "\n".join(
        [
            f"# `{scaffold.source_id}`",
            "",
            description,
            "",
            "## Navigation",
            "",
            "- [Project README](../../README.md)",
            "- [Documentation index](../../docs/README.md)",
            "- [Architecture overview](../../docs/architecture.md)",
            "- [Architecture review](../../docs/architecture-review.md)",
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
            f"- `{default_summary}`",
            "",
            "## Notes",
            "",
            "- Add bibliography-specific macros in `source.toml` under `[macros]`.",
            "- Add broad regex rules in `[[regex_rules]]`.",
            "- `rules.json`, `review_variants.json`, and `ignored_variants.json` are local runtime "
            "state managed by the workflow.",
            "- The runtime JSON files are gitignored and do not need to be committed.",
            "",
        ]
    )
