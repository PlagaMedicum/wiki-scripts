from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from biblio.models import SourceSpec
from biblio.runtime_json import (
    RuntimeJsonError,
    save_json_list_atomic,
)
from biblio.runtime_json import (
    load_json_list as load_runtime_json_list,
)
from biblio.text import (
    extract_entry_arg,
    extract_pages_arg,
    extract_template_arguments,
    make_review_key,
    normalize_review_line,
)


def _load_runtime_list(path: Path, kind: str) -> list[Any]:
    return load_runtime_json_list(path, kind=kind)


def load_json_list(path: Path) -> list[Any]:
    return _load_runtime_list(path, path.name)


def _string_items(path: Path, kind: str) -> list[str]:
    values = _load_runtime_list(path, kind)
    items: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str):
            raise RuntimeJsonError(
                f"Expected {kind} at {path} to contain only strings, got {type(item).__name__} at index {index}"
            )
        items.append(item)
    return items


def load_rules(path: Path) -> list[dict[str, Any]]:
    values = _load_runtime_list(path, "rules.json")
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise RuntimeJsonError(
                f"Expected rules.json at {path} to contain only objects, got {type(item).__name__} at index {index}"
            )
        kind = item.get("kind")
        match = item.get("match")
        replacement = item.get("replacement")
        enabled = item.get("enabled", True)
        if not isinstance(kind, str):
            raise RuntimeJsonError(f"Expected rules.json at {path} to store string kind values")
        if not isinstance(match, str):
            raise RuntimeJsonError(f"Expected rules.json at {path} to store string match values")
        if not isinstance(replacement, str):
            raise RuntimeJsonError(
                f"Expected rules.json at {path} to store string replacement values"
            )
        if not isinstance(enabled, bool):
            raise RuntimeJsonError(f"Expected rules.json at {path} to store boolean enabled values")
        rules.append(dict(item))
    return rules


def load_review_variants(path: Path) -> list[str]:
    return _string_items(path, "review_variants.json")


def load_ignored_hashes(path: Path) -> set[str]:
    return set(_string_items(path, "ignored_variants.json"))


def save_json_list(path: Path, data: list[Any]) -> None:
    save_json_list_atomic(path, data, kind=path.name)


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
        "_runtime_source": "review_variants.json",
    }


def make_explicit_line_exact_rule(
    spec: SourceSpec,
    match_text: str,
    replacement: str,
) -> dict:
    return {
        "kind": "line_exact",
        "match": make_review_key(match_text, spec),
        "replacement": replacement.strip(),
        "enabled": True,
        "_runtime_source": "rules.json",
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
            merged.append({**rule, "_runtime_source": "rules.json"})
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
    _active_rules_cache: tuple[dict, ...] | None = field(default=None, init=False, repr=False)
    _review_keys_cache: frozenset[str] | None = field(default=None, init=False, repr=False)

    @property
    def active_rules(self) -> tuple[dict, ...]:
        if self._active_rules_cache is None:
            self._active_rules_cache = tuple(
                merge_rules(self.spec, self.base_rules, self.review_variants)
            )
        return self._active_rules_cache

    @property
    def review_keys(self) -> frozenset[str]:
        if self._review_keys_cache is None:
            self._review_keys_cache = frozenset(
                make_review_key(item, self.spec) for item in self.review_variants
            )
        return self._review_keys_cache

    def _invalidate_active_rules(self) -> None:
        self._active_rules_cache = None

    def _invalidate_review_keys(self) -> None:
        self._review_keys_cache = None

    def add_review_variant(self, review_line: str) -> bool:
        key = make_review_key(review_line, self.spec)
        if key in self.review_keys:
            return False

        self.review_variants.append(review_line)
        save_json_list(self.spec.review_path, self.review_variants)
        self._invalidate_review_keys()
        self._invalidate_active_rules()
        return True

    def add_ignored_hash(self, value: str) -> bool:
        if value in self.ignored_hashes:
            return False

        self.ignored_hashes.add(value)
        save_json_list(self.spec.ignored_path, sorted(self.ignored_hashes))
        return True

    def add_exact_rule(self, match_text: str, replacement: str) -> bool:
        return self.ensure_rule_saved(
            make_explicit_line_exact_rule(self.spec, match_text, replacement)
        )

    def ensure_rule_saved(self, rule: dict) -> bool:
        key = make_rule_key(rule, self.spec)
        existing = {
            make_rule_key(item, self.spec) for item in self.base_rules if item.get("enabled", True)
        }
        if key in existing:
            return False

        stored_rule = {key: value for key, value in rule.items() if key != "_runtime_source"}
        self.base_rules.append(stored_rule)
        save_json_list(self.spec.rules_path, self.base_rules)
        self._invalidate_active_rules()
        return True


def load_source_state(spec: SourceSpec) -> SourceState:
    return SourceState(
        spec=spec,
        base_rules=load_rules(spec.rules_path),
        review_variants=load_review_variants(spec.review_path),
        ignored_hashes=load_ignored_hashes(spec.ignored_path),
    )
