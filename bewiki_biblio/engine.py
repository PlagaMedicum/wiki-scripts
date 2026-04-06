from __future__ import annotations

import re

from bewiki_biblio.models import ReplacementResult, SourceSpec, VariantInfo
from bewiki_biblio.state import variant_hash
from bewiki_biblio.text import (
    extract_entry_arg,
    extract_pages_arg,
    extract_template_arguments,
    make_review_key,
    normalize_biblio_wikitext,
    normalize_argument_value,
    normalize_entry_arg,
    normalize_pages_arg,
    normalize_review_line,
    split_candidate_units,
    split_ref_aware_segments,
)
from bewiki_biblio.utils import substitute_tokens


def replace_line_exact_rules(
    text: str,
    spec: SourceSpec,
    rules: list[dict],
) -> tuple[
    str,
    int,
    list[dict],
    list[str],
    list[str],
    list[str],
    dict[str, list[str]],
    list[str],
]:
    exact_map: dict[str, dict] = {}

    for rule in rules:
        if rule.get("kind") != "line_exact" or not rule.get("enabled", True):
            continue

        match_text = make_review_key(str(rule.get("match", "")), spec)
        replacement = str(rule.get("replacement", ""))
        if match_text and replacement:
            exact_map[match_text] = rule

    if not exact_map:
        return text, 0, [], [], [], [], {}, []

    parts: list[str] = []
    position = 0
    replaced = 0
    used_rules: list[dict] = []
    rendered_templates: list[str] = []
    page_arguments: list[str] = []
    entry_arguments: list[str] = []
    extra_argument_values: dict[str, list[str]] = {}
    matched_review_lines: list[str] = []

    for unit in split_candidate_units(text):
        parts.append(text[position : unit.start])
        body = unit.body.strip()
        normalized_body = make_review_key(body, spec)
        rule = exact_map.get(normalized_body)
        if not rule:
            parts.append(text[unit.start : unit.end])
            position = unit.end
            continue

        stored_replacement = str(rule["replacement"])
        extracted_pages = extract_pages_arg(body, spec)
        extracted_entry = extract_entry_arg(body, spec)
        extracted_arguments = extract_template_arguments(body, spec)
        if spec.template_name in stored_replacement:
            replacement = spec.render_template(
                pages=extracted_pages,
                entry=extracted_entry,
                **extracted_arguments,
            )
        else:
            replacement = stored_replacement
        parts.append(f"{unit.prefix}{replacement}{unit.trailing_newline}")
        position = unit.end
        replaced += 1
        used_rules.append(rule)
        rendered_templates.append(replacement)

        if extracted_pages:
            page_arguments.append(extracted_pages)
        if extracted_entry:
            entry_arguments.append(extracted_entry)
        for key, value in extracted_arguments.items():
            extra_argument_values.setdefault(key, []).append(value)
    parts.append(text[position:])
    return (
        "".join(parts),
        replaced,
        used_rules,
        rendered_templates,
        page_arguments,
        entry_arguments,
        extra_argument_values,
        matched_review_lines,
    )


def apply_regex_rules(
    text: str,
    spec: SourceSpec,
) -> tuple[
    str,
    int,
    list[str],
    list[str],
    list[str],
    list[str],
    dict[str, list[str]],
    list[str],
    list[str],
]:
    current = text
    replacements = 0
    used_rule_names: list[str] = []
    rendered_templates: list[str] = []
    page_arguments: list[str] = []
    entry_arguments: list[str] = []
    extra_argument_values: dict[str, list[str]] = {}
    review_reasons: list[str] = []
    matched_review_lines: list[str] = []

    for rule in spec.regex_rules:
        if not rule.enabled:
            continue

        def replace(match: re.Match[str]) -> str:
            match_text = match.group(0)
            groups = {key: (value or "") for key, value in match.groupdict().items()}
            extracted_pages = extract_pages_arg(match_text, spec)
            extracted_entry = extract_entry_arg(match_text, spec)
            extracted_arguments = extract_template_arguments(match_text, spec)
            pages = normalize_pages_arg(groups["pages"]) if groups.get("pages") else extracted_pages
            entry = normalize_entry_arg(groups["entry"]) if groups.get("entry") else extracted_entry
            template_arguments: dict[str, str] = dict(extracted_arguments)
            for key, value in groups.items():
                if key in {"pages", "entry", "prefix"} or not value:
                    continue
                template_arguments[key] = normalize_argument_value(
                    value,
                    spec.argument_normalizer(key),
                )
            template = spec.render_template(
                pages=pages,
                entry=entry,
                **template_arguments,
            )
            used_rule_names.append(rule.name)
            rendered_templates.append(template)
            if pages:
                page_arguments.append(pages)
            if entry:
                entry_arguments.append(entry)
            for key, value in template_arguments.items():
                extra_argument_values.setdefault(key, []).append(value)
            if rule.review_required:
                review_reasons.append(
                    rule.review_note or f"Rule {rule.name} requires manual review."
                )
                matched_review_lines.append(match_text)

            mapping = {
                **groups,
                "entry": entry or "",
                "pages": pages or "",
                "template": template,
                "template_name": spec.template_name,
                "source_id": spec.source_id,
            }
            return substitute_tokens(rule.replacement, mapping)

        current, count = rule.compiled.subn(replace, current)
        replacements += count

    return (
        current,
        replacements,
        used_rule_names,
        rendered_templates,
        page_arguments,
        entry_arguments,
        extra_argument_values,
        review_reasons,
        matched_review_lines,
    )


def apply_normalized_unit_regex_rules(
    text: str,
    spec: SourceSpec,
) -> tuple[
    str,
    int,
    list[str],
    list[str],
    list[str],
    list[str],
    dict[str, list[str]],
    list[str],
    list[str],
]:
    parts: list[str] = []
    position = 0
    replacements = 0
    used_rule_names: list[str] = []
    rendered_templates: list[str] = []
    page_arguments: list[str] = []
    entry_arguments: list[str] = []
    extra_argument_values: dict[str, list[str]] = {}
    review_reasons: list[str] = []
    matched_review_lines: list[str] = []

    for unit in split_candidate_units(text):
        parts.append(text[position : unit.start])
        normalized_unit = normalize_biblio_wikitext(
            text[unit.start : unit.end].rstrip("\r\n"),
            spec,
        )
        matched = False

        for rule in spec.regex_rules:
            if not rule.enabled:
                continue
            match = rule.compiled.search(normalized_unit)
            if not match:
                continue

            unit_text = unit.body
            groups = {key: (value or "") for key, value in match.groupdict().items()}
            extracted_pages = extract_pages_arg(unit_text, spec)
            extracted_entry = extract_entry_arg(unit_text, spec)
            extracted_arguments = extract_template_arguments(unit_text, spec)
            pages = normalize_pages_arg(groups["pages"]) if groups.get("pages") else extracted_pages
            entry = normalize_entry_arg(groups["entry"]) if groups.get("entry") else extracted_entry
            template_arguments: dict[str, str] = dict(extracted_arguments)
            for key, value in groups.items():
                if key in {"pages", "entry", "prefix"} or not value:
                    continue
                template_arguments[key] = normalize_argument_value(
                    value,
                    spec.argument_normalizer(key),
                )
            template = spec.render_template(
                pages=pages,
                entry=entry,
                **template_arguments,
            )
            mapping = {
                **groups,
                "entry": entry or "",
                "pages": pages or "",
                "prefix": unit.prefix,
                "template": template,
                "template_name": spec.template_name,
                "source_id": spec.source_id,
            }
            replacement = substitute_tokens(rule.replacement, mapping)

            parts.append(f"{replacement}{unit.trailing_newline}")
            position = unit.end
            replacements += 1
            used_rule_names.append(rule.name)
            rendered_templates.append(template)
            if pages:
                page_arguments.append(pages)
            if entry:
                entry_arguments.append(entry)
            for key, value in template_arguments.items():
                extra_argument_values.setdefault(key, []).append(value)
            if rule.review_required:
                review_reasons.append(
                    rule.review_note or f"Rule {rule.name} requires manual review."
                )
                matched_review_lines.append(unit.body)
            matched = True
            break

        if not matched:
            parts.append(text[unit.start : unit.end])
            position = unit.end

    parts.append(text[position:])
    return (
        "".join(parts),
        replacements,
        used_rule_names,
        rendered_templates,
        page_arguments,
        entry_arguments,
        extra_argument_values,
        review_reasons,
        matched_review_lines,
    )


def _replace_segment(
    text: str,
    spec: SourceSpec,
    active_rules: list[dict],
) -> ReplacementResult:
    (
        current,
        line_count,
        used_line_rules,
        line_templates,
        line_pages,
        line_entries,
        line_extra_argument_values,
        line_review_lines,
    ) = replace_line_exact_rules(
        text,
        spec,
        active_rules,
    )
    (
        current,
        regex_count,
        used_rule_names,
        rendered_templates,
        page_arguments,
        entry_arguments,
        extra_argument_values,
        regex_review_reasons,
        regex_review_lines,
    ) = apply_regex_rules(
        current,
        spec,
    )
    (
        current,
        normalized_regex_count,
        normalized_rule_names,
        normalized_templates,
        normalized_pages,
        normalized_entries,
        normalized_extra_argument_values,
        normalized_review_reasons,
        normalized_review_lines,
    ) = apply_normalized_unit_regex_rules(
        current,
        spec,
    )
    merged_extra_argument_values = {
        key: values[:]
        for key, values in extra_argument_values.items()
    }
    for key, values in normalized_extra_argument_values.items():
        merged_extra_argument_values.setdefault(key, []).extend(values)
    for key, values in line_extra_argument_values.items():
        merged_extra_argument_values.setdefault(key, []).extend(values)
    return ReplacementResult(
        text=current,
        replacements=regex_count + normalized_regex_count + line_count,
        used_line_rules=used_line_rules,
        used_rule_names=used_rule_names + normalized_rule_names + (["line_exact"] * line_count),
        rendered_templates=rendered_templates + normalized_templates + line_templates,
        page_arguments=page_arguments + normalized_pages + line_pages,
        entry_arguments=entry_arguments + normalized_entries + line_entries,
        extra_argument_values=merged_extra_argument_values,
        review_reasons=regex_review_reasons + normalized_review_reasons,
        matched_review_lines=line_review_lines + regex_review_lines + normalized_review_lines,
    )


def replace_text(
    text: str,
    spec: SourceSpec,
    active_rules: list[dict],
) -> ReplacementResult:
    parts: list[str] = []
    total_replacements = 0
    used_line_rules: list[dict] = []
    used_rule_names: list[str] = []
    rendered_templates: list[str] = []
    page_arguments: list[str] = []
    entry_arguments: list[str] = []
    extra_argument_values: dict[str, list[str]] = {}
    review_reasons: list[str] = []
    matched_review_lines: list[str] = []

    for kind, segment, open_tag, close_tag in split_ref_aware_segments(text):
        result = _replace_segment(segment, spec, active_rules)
        if kind == "ref":
            parts.append(f"{open_tag}{result.text}{close_tag}")
        else:
            parts.append(result.text)

        total_replacements += result.replacements
        used_line_rules.extend(result.used_line_rules)
        used_rule_names.extend(result.used_rule_names)
        rendered_templates.extend(result.rendered_templates)
        page_arguments.extend(result.page_arguments)
        entry_arguments.extend(result.entry_arguments)
        for key, values in result.extra_argument_values.items():
            extra_argument_values.setdefault(key, []).extend(values)
        review_reasons.extend(result.review_reasons)
        matched_review_lines.extend(result.matched_review_lines)

    return ReplacementResult(
        text="".join(parts),
        replacements=total_replacements,
        used_line_rules=used_line_rules,
        used_rule_names=used_rule_names,
        rendered_templates=rendered_templates,
        page_arguments=page_arguments,
        entry_arguments=entry_arguments,
        extra_argument_values=extra_argument_values,
        review_reasons=review_reasons,
        matched_review_lines=matched_review_lines,
    )


def is_candidate_line(raw_line: str, spec: SourceSpec) -> bool:
    line = normalize_biblio_wikitext(raw_line, spec).casefold()
    must_contain_all = [
        normalize_biblio_wikitext(term, spec).casefold()
        for term in spec.candidate.must_contain_all
    ]
    must_contain_any = [
        normalize_biblio_wikitext(term, spec).casefold()
        for term in spec.candidate.must_contain_any
    ]

    if any(term not in line for term in must_contain_all):
        return False
    if must_contain_any and not any(term in line for term in must_contain_any):
        return False
    return True


def extract_unknown_variant_infos(text: str, spec: SourceSpec) -> list[VariantInfo]:
    infos: list[VariantInfo] = []
    seen: set[str] = set()

    for _, segment, _, _ in split_ref_aware_segments(text):
        units = split_candidate_units(segment)
        for unit in units:
            body = unit.body.strip()
            if not body or not is_candidate_line(body, spec):
                continue

            review_line = body
            normalized_line = normalize_review_line(review_line, spec)
            key = normalized_line.casefold()
            if key in seen:
                continue

            seen.add(key)
            infos.append(
                VariantInfo(
                    full_line=unit.raw_text.strip(),
                    review_line=review_line,
                    normalized_line=normalized_line,
                    pages=extract_pages_arg(review_line, spec),
                    entry=extract_entry_arg(review_line, spec),
                    extra_arguments=extract_template_arguments(review_line, spec),
                )
            )

    return infos


def debug_candidate_lines(text: str, spec: SourceSpec) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    for _, segment, _, _ in split_ref_aware_segments(text):
        units = split_candidate_units(segment)
        for unit in units:
            body = unit.body.strip()
            if not body or not is_candidate_line(body, spec):
                continue

            normalized = normalize_review_line(body, spec)
            if normalized in seen:
                continue

            seen.add(normalized)
            lines.append(unit.raw_text.strip())

    return lines


def variant_review_key(info: VariantInfo) -> str:
    return info.normalized_line.casefold()


def variant_review_hash(info: VariantInfo) -> str:
    return variant_hash(variant_review_key(info))
