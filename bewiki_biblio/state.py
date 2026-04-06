from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from bewiki_biblio.models import SourceSpec
from bewiki_biblio.text import (
    extract_entry_arg,
    extract_pages_arg,
    extract_template_arguments,
    make_review_key,
    normalize_review_line,
)


def load_json_list(path) -> list:
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_json_list(path, data: list) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_rules(path) -> list[dict]:
    data = load_json_list(path)
    return [item for item in data if isinstance(item, dict)]


def variant_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def make_line_exact_rule(
    spec: SourceSpec,
    match_text: str,
    pages: str | None = None,
    entry: str | None = None,
    arguments: dict[str, str] | None = None,
) -> dict:
    return {
        "kind": "line_exact",
        "match": make_review_key(match_text, spec),
        "replacement": spec.render_template(
            pages=pages,
            entry=entry,
            **(arguments or {}),
        ),
        "enabled": True,
    }


def make_rule_key(rule: dict, spec: SourceSpec) -> tuple[str, str, str]:
    return (
        str(rule.get("kind", "")),
        make_review_key(str(rule.get("match", "")), spec),
        str(rule.get("replacement", "")),
    )


def merge_rules(spec: SourceSpec, base_rules: list[dict], review_lines: list[str]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for rule in base_rules:
        if not rule.get("enabled", True):
            continue
        key = make_rule_key(rule, spec)
        if key not in seen:
            merged.append(rule)
            seen.add(key)

    for line in review_lines:
        normalized = normalize_review_line(line, spec)
        pages = extract_pages_arg(line, spec)
        entry = extract_entry_arg(line, spec)
        arguments = extract_template_arguments(line, spec)
        rule = make_line_exact_rule(spec, normalized, pages, entry, arguments)
        key = make_rule_key(rule, spec)
        if key not in seen:
            merged.append(rule)
            seen.add(key)

    return merged


@dataclass
class SourceState:
    spec: SourceSpec
    base_rules: list[dict]
    review_variants: list[str]
    ignored_hashes: set[str]

    @property
    def active_rules(self) -> list[dict]:
        return merge_rules(self.spec, self.base_rules, self.review_variants)

    @property
    def review_keys(self) -> set[str]:
        return {make_review_key(item, self.spec) for item in self.review_variants}

    def add_review_variant(self, review_line: str) -> bool:
        key = make_review_key(review_line, self.spec)
        if key in self.review_keys:
            return False

        self.review_variants.append(review_line)
        save_json_list(self.spec.review_path, self.review_variants)
        return True

    def add_ignored_hash(self, value: str) -> bool:
        if value in self.ignored_hashes:
            return False

        self.ignored_hashes.add(value)
        save_json_list(self.spec.ignored_path, sorted(self.ignored_hashes))
        return True

    def ensure_rule_saved(self, rule: dict) -> bool:
        key = make_rule_key(rule, self.spec)
        existing = {make_rule_key(item, self.spec) for item in self.base_rules if item.get("enabled", True)}
        if key in existing:
            return False

        self.base_rules.append(rule)
        save_json_list(self.spec.rules_path, self.base_rules)
        return True


def load_source_state(spec: SourceSpec) -> SourceState:
    return SourceState(
        spec=spec,
        base_rules=load_rules(spec.rules_path),
        review_variants=[item for item in load_json_list(spec.review_path) if isinstance(item, str)],
        ignored_hashes={item for item in load_json_list(spec.ignored_path) if isinstance(item, str)},
    )
