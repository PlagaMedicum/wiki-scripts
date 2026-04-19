#!/usr/bin/env python3
"""Sync managed Markdown metadata and lint the repo-wide frontmatter schema."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml

DOCMETA_START = "<!-- DOCMETA:START -->"
DOCMETA_END = "<!-- DOCMETA:END -->"
DOCMETA_RE = re.compile(
    rf"{re.escape(DOCMETA_START)}\n.*?\n{re.escape(DOCMETA_END)}\n?",
    re.DOTALL,
)
DOCMETA_DETAILS_LINE = '<details class="docmeta-block">'
DOCMETA_CLOSE_LINE = "</details>"
REGISTRY_SOURCE = ".specify/doc-registry.json"
FRONTMATTER_RE = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n*", re.DOTALL)
SUMMARY_RE = re.compile(
    r"^<summary><strong>DOCMETA</strong> \| st: (?P<status>.+?) \| rv: (?P<review>.+?) \| src: (?P<src>registry|local)</summary>$"
)
FIELD_LINE_RE = re.compile(
    r"^\*\*(?P<field>Status|Review|Purpose|Source|Feature|Connected Docs|Branch|Created|Input)\*\*:\s+(?P<value>.+?)\s*$"
)
DOCMETA_FIELD_MAP = {
    "Status": "status",
    "Review": "review",
    "Purpose": "purpose",
    "Source": "source",
    "Feature": "feature",
    "Connected Docs": "connected_docs",
    "Branch": "branch",
    "Created": "created",
    "Input": "input",
}
DOCMETA_CORE_KEYS = ("status", "review", "purpose", "source")
DOCMETA_OPTIONAL_KEYS = ("feature", "connected_docs", "branch", "created", "input")
DOCMETA_CANONICAL_ORDER = DOCMETA_CORE_KEYS + DOCMETA_OPTIONAL_KEYS
APPROVAL_SOURCE_LABELS = frozenset({"client-input-derived"})
APPROVAL_TERMINAL_LABELS = frozenset({"approved", "client-confirmed"})
MANUAL_REVIEW_PENDING_LABELS = frozenset({"unreviewed"})
MANUAL_REVIEW_TERMINAL_LABELS = frozenset(
    {"reviewed", "approved", "client-confirmed", "code-reviewed", "operator-verified"}
)


@dataclass(frozen=True)
class ManagedDoc:
    path: str
    status: str
    review: tuple[str, ...]
    purpose: str


@dataclass(frozen=True)
class LegacyDocMeta:
    summary_status: str
    summary_review: str
    summary_source: str
    fields: dict[str, str]


@dataclass(frozen=True)
class ResolvedDocMeta:
    kind: str
    status: str | None
    review: tuple[str, ...]
    purpose: str | None
    source: str | None
    optional: dict[str, Any]


class RegistryError(RuntimeError):
    """Registry validation failed."""


def needs_explicit_client_approval(review_labels: Iterable[str]) -> bool:
    labels = set(review_labels)
    return bool(labels & APPROVAL_SOURCE_LABELS) and not bool(labels & APPROVAL_TERMINAL_LABELS)


def needs_manual_review(review_labels: Iterable[str]) -> bool:
    labels = set(review_labels)
    return bool(labels & MANUAL_REVIEW_PENDING_LABELS) and not bool(labels & MANUAL_REVIEW_TERMINAL_LABELS)


def load_registry(registry_path: Path) -> dict:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RegistryError("registry root must be an object")
    for key in ("allowed_statuses", "allowed_reviews", "managed_roots", "exclude_globs", "documents"):
        if key not in data:
            raise RegistryError(f"registry missing required key: {key}")
    return data


def normalize_document(entry: dict, allowed_statuses: set[str], allowed_reviews: set[str]) -> ManagedDoc:
    path = entry["path"]
    status = entry["status"]
    review = tuple(entry["review"])
    purpose = entry["purpose"]

    if status not in allowed_statuses:
        raise RegistryError(f"{path}: unknown status {status!r}")
    unknown_reviews = [label for label in review if label not in allowed_reviews]
    if unknown_reviews:
        raise RegistryError(f"{path}: unknown review labels {', '.join(unknown_reviews)}")
    if not review:
        raise RegistryError(f"{path}: review list must not be empty")

    return ManagedDoc(path=path, status=status, review=review, purpose=purpose)


def registry_documents(registry: dict) -> list[ManagedDoc]:
    allowed_statuses = set(registry["allowed_statuses"])
    allowed_reviews = set(registry["allowed_reviews"])
    docs = [normalize_document(entry, allowed_statuses, allowed_reviews) for entry in registry["documents"]]

    seen: set[str] = set()
    for doc in docs:
        if doc.path in seen:
            raise RegistryError(f"duplicate document path in registry: {doc.path}")
        seen.add(doc.path)
    return docs


def repo_markdown_paths(root: Path) -> list[Path]:
    tracked_result = subprocess.run(
        ["git", "ls-files", "--", "*.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    untracked_result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "*.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked_result.returncode == 0 and untracked_result.returncode == 0:
        rels = {
            rel
            for rel in (tracked_result.stdout.splitlines() + untracked_result.stdout.splitlines())
            if rel
        }
        return sorted((root / rel) for rel in rels if (root / rel).is_file())

    return sorted(path for path in root.rglob("*.md") if ".git" not in path.parts)


def normalize_loaded_yaml(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_loaded_yaml(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_loaded_yaml(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def parse_frontmatter(text: str, rel_path: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text, []

    raw_yaml = match.group("yaml")
    try:
        data = yaml.safe_load(raw_yaml) if raw_yaml.strip() else {}
    except yaml.YAMLError as exc:
        return None, text, [f"{rel_path}: invalid YAML frontmatter ({exc})"]

    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, text, [f"{rel_path}: YAML frontmatter root must be a mapping"]

    return normalize_loaded_yaml(data), text[match.end() :], []


def dump_frontmatter(data: dict[str, Any]) -> str:
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
        width=1000,
    ).strip()
    return f"---\n{dumped}\n---\n\n"


def normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return None


def normalize_review_labels(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        labels = [normalize_scalar(item) for item in value]
        return tuple(label for label in labels if label)

    scalar = normalize_scalar(value)
    if not scalar:
        return ()
    return tuple(part.strip() for part in scalar.split(",") if part.strip())


def render_review_value(labels: Iterable[str]) -> str | list[str]:
    normalized = tuple(label.strip() for label in labels if label.strip())
    if len(normalized) == 1:
        return normalized[0]
    return list(normalized)


def classify_doc(rel_path: str) -> str:
    if rel_path.startswith(".agents/skills/") and rel_path.endswith("/SKILL.md"):
        return "skill"
    if rel_path.startswith(".specify/extensions/") and "/commands/" in rel_path:
        return "command"
    return "general"


def metadata_source(frontmatter: dict[str, Any]) -> str | None:
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return normalize_scalar(metadata.get("source"))


def normalize_connected_docs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in (normalize_scalar(entry) for entry in value) if item]

    scalar = normalize_scalar(value)
    if not scalar:
        return []
    return [part.strip() for part in scalar.split(",") if part.strip()]


def parse_legacy_docmeta_block(text: str) -> LegacyDocMeta | None:
    match = DOCMETA_RE.search(text)
    if not match:
        return None

    lines = match.group(0).rstrip("\n").splitlines()
    if len(lines) < 7:
        return None
    if lines[0] != DOCMETA_START or lines[-1] != DOCMETA_END:
        return None
    if lines[1] != DOCMETA_DETAILS_LINE or lines[-2] != DOCMETA_CLOSE_LINE:
        return None
    summary_match = SUMMARY_RE.match(lines[2])
    if not summary_match or lines[3] != "":
        return None

    fields: dict[str, str] = {}
    for raw_line in lines[4:-2]:
        if not raw_line.strip():
            continue
        field_match = FIELD_LINE_RE.match(raw_line.rstrip())
        if not field_match:
            return None
        field = field_match.group("field")
        value = field_match.group("value")
        if value.startswith("`") and value.endswith("`") and len(value) >= 2:
            value = value[1:-1]
        fields[field] = value

    return LegacyDocMeta(
        summary_status=summary_match.group("status"),
        summary_review=summary_match.group("review"),
        summary_source=summary_match.group("src"),
        fields=fields,
    )


def resolve_docmeta(
    rel_path: str,
    frontmatter: dict[str, Any],
    legacy: LegacyDocMeta | None,
) -> ResolvedDocMeta:
    kind = classify_doc(rel_path)
    docmeta = frontmatter.get("docmeta")
    docmeta_map = docmeta if isinstance(docmeta, dict) else {}

    status = normalize_scalar(docmeta_map.get("status"))
    if not status and legacy:
        status = normalize_scalar(legacy.fields.get("Status"))

    review = normalize_review_labels(docmeta_map.get("review"))
    if not review and legacy:
        review = normalize_review_labels(legacy.fields.get("Review"))

    purpose = normalize_scalar(docmeta_map.get("purpose"))
    if not purpose and kind in {"skill", "command"}:
        purpose = normalize_scalar(frontmatter.get("description"))
    if not purpose and legacy:
        purpose = normalize_scalar(legacy.fields.get("Purpose"))

    source = normalize_scalar(docmeta_map.get("source"))
    if not source and kind == "skill":
        source = metadata_source(frontmatter)
    if not source and legacy:
        source = normalize_scalar(legacy.fields.get("Source"))

    optional: dict[str, Any] = {}
    for legacy_field, yaml_key in DOCMETA_FIELD_MAP.items():
        if yaml_key in DOCMETA_CORE_KEYS:
            continue
        if yaml_key in docmeta_map:
            value = docmeta_map[yaml_key]
        elif legacy:
            value = legacy.fields.get(legacy_field)
        else:
            value = None
        if value is None:
            continue
        if yaml_key == "connected_docs":
            normalized = normalize_connected_docs(value)
            if normalized:
                optional[yaml_key] = normalized
            continue
        scalar = normalize_scalar(value)
        if scalar:
            optional[yaml_key] = scalar

    return ResolvedDocMeta(
        kind=kind,
        status=status,
        review=review,
        purpose=purpose,
        source=source,
        optional=optional,
    )


def order_docmeta_mapping(docmeta: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in DOCMETA_CANONICAL_ORDER:
        if key in docmeta:
            ordered[key] = docmeta[key]
    for key, value in docmeta.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def with_docmeta(
    frontmatter: dict[str, Any],
    rel_path: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    kind = classify_doc(rel_path)
    result: dict[str, Any] = {}
    existing_docmeta = frontmatter.get("docmeta")
    docmeta = dict(existing_docmeta) if isinstance(existing_docmeta, dict) else {}
    docmeta.update(values)

    description_purpose = normalize_scalar(frontmatter.get("description")) if kind in {"skill", "command"} else None
    if description_purpose:
        docmeta.pop("purpose", None)

    skill_metadata_source = metadata_source(frontmatter) if kind == "skill" else None
    if skill_metadata_source:
        docmeta.pop("source", None)

    docmeta = order_docmeta_mapping(docmeta)

    inserted = False
    for key, value in frontmatter.items():
        if key == "docmeta":
            result[key] = docmeta
            inserted = True
            continue
        result[key] = value
    if not inserted:
        result["docmeta"] = docmeta
    return result


def remove_legacy_docmeta(text: str) -> str:
    return DOCMETA_RE.sub("", text, count=1)


def rebuild_text(frontmatter: dict[str, Any], body: str) -> str:
    return dump_frontmatter(frontmatter) + body.lstrip("\n")


def migrate_text(text: str, rel_path: str, managed_doc: ManagedDoc | None) -> str:
    frontmatter, body, fm_errors = parse_frontmatter(text, rel_path)
    if fm_errors:
        raise RegistryError(fm_errors[0])

    legacy = parse_legacy_docmeta_block(text)
    original_frontmatter = frontmatter or {}
    cleaned_body = remove_legacy_docmeta(body if frontmatter is not None else text)

    if managed_doc is not None:
        updated = with_docmeta(
            original_frontmatter,
            rel_path,
            {
                "status": managed_doc.status,
                "review": render_review_value(managed_doc.review),
                "purpose": managed_doc.purpose,
                "source": REGISTRY_SOURCE,
            },
        )
        return rebuild_text(updated, cleaned_body)

    resolved = resolve_docmeta(rel_path, original_frontmatter, legacy)
    if not (resolved.status and resolved.review):
        return text

    values: dict[str, Any] = {
        "status": resolved.status,
        "review": render_review_value(resolved.review),
    }
    if resolved.purpose and not (
        resolved.kind in {"skill", "command"} and normalize_scalar(original_frontmatter.get("description"))
    ):
        values["purpose"] = resolved.purpose
    if resolved.source and not (resolved.kind == "skill" and metadata_source(original_frontmatter)):
        values["source"] = resolved.source
    values.update(resolved.optional)

    updated = with_docmeta(original_frontmatter, rel_path, values)
    return rebuild_text(updated, cleaned_body)


def validate_frontmatter(
    text: str,
    rel_path: str,
    managed_doc: ManagedDoc | None = None,
) -> list[str]:
    errors: list[str] = []
    frontmatter, body, fm_errors = parse_frontmatter(text, rel_path)
    errors.extend(fm_errors)

    body_for_heading = body if frontmatter is not None else text
    if not any(line.startswith("# ") for line in body_for_heading.splitlines()):
        errors.append(f"{rel_path}: missing H1 heading")

    legacy = parse_legacy_docmeta_block(text)
    if frontmatter is None:
        if legacy is not None:
            errors.append(f"{rel_path}: legacy DOCMETA header must be migrated to YAML frontmatter")
        else:
            errors.append(f"{rel_path}: missing YAML frontmatter")
        return errors

    docmeta = frontmatter.get("docmeta")
    if docmeta is None:
        errors.append(f"{rel_path}: missing docmeta mapping in YAML frontmatter")
        docmeta_map: dict[str, Any] = {}
    elif not isinstance(docmeta, dict):
        errors.append(f"{rel_path}: docmeta must be a mapping")
        docmeta_map = {}
    else:
        docmeta_map = docmeta

    resolved = resolve_docmeta(rel_path, frontmatter, legacy)

    if resolved.kind == "general":
        for key in DOCMETA_CORE_KEYS:
            if key not in docmeta_map:
                errors.append(f"{rel_path}: docmeta missing required key {key}")
    else:
        for key in ("status", "review"):
            if key not in docmeta_map:
                errors.append(f"{rel_path}: docmeta missing required key {key}")
        if not resolved.purpose:
            errors.append(f"{rel_path}: missing purpose (docmeta.purpose or description)")
        if not resolved.source:
            errors.append(f"{rel_path}: missing source (docmeta.source or metadata.source)")

    if not resolved.status:
        errors.append(f"{rel_path}: missing status")
    if not resolved.review:
        errors.append(f"{rel_path}: missing review labels")

    if "connected_docs" in docmeta_map and not normalize_connected_docs(docmeta_map["connected_docs"]):
        errors.append(f"{rel_path}: docmeta.connected_docs must not be empty")

    if managed_doc is not None and not errors:
        if resolved.status != managed_doc.status:
            errors.append(f"{rel_path}: docmeta.status does not match registry")
        if resolved.review != managed_doc.review:
            errors.append(f"{rel_path}: docmeta.review does not match registry")
        if resolved.purpose != managed_doc.purpose:
            errors.append(f"{rel_path}: docmeta.purpose does not match registry")
        if resolved.source != REGISTRY_SOURCE:
            errors.append(f"{rel_path}: docmeta.source does not match registry")

    return errors


def managed_candidates(root: Path, registry: dict) -> set[str]:
    exclude_globs = tuple(registry["exclude_globs"])
    found: set[str] = set()

    for rel_root in registry["managed_roots"]:
        target = root / rel_root
        if target.is_file():
            rel = target.relative_to(root).as_posix()
            if not is_excluded(rel, exclude_globs):
                found.add(rel)
            continue
        if not target.is_dir():
            continue
        for path in target.rglob("*.md"):
            rel = path.relative_to(root).as_posix()
            if not is_excluded(rel, exclude_globs):
                found.add(rel)
    return found


def is_excluded(rel_path: str, exclude_globs: Iterable[str]) -> bool:
    pure = PurePosixPath(rel_path)
    return any(pure.match(pattern) for pattern in exclude_globs)


def sync(root: Path, registry_path: Path) -> list[str]:
    registry = load_registry(registry_path)
    docs = registry_documents(registry)
    docs_by_path = {doc.path: doc for doc in docs}
    changed: list[str] = []

    for doc in docs:
        if not (root / doc.path).is_file():
            raise RegistryError(f"tracked doc is missing: {doc.path}")

    for path in repo_markdown_paths(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        updated = migrate_text(text, rel, docs_by_path.get(rel))
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(rel)
    return changed


def lint(root: Path, registry_path: Path) -> list[str]:
    registry = load_registry(registry_path)
    docs = registry_documents(registry)
    tracked_paths = {doc.path for doc in docs}
    docs_by_path = {doc.path: doc for doc in docs}
    errors: list[str] = []

    for doc in docs:
        path = root / doc.path
        if not path.is_file():
            errors.append(f"tracked doc is missing: {doc.path}")
            continue
        errors.extend(validate_frontmatter(path.read_text(encoding="utf-8"), doc.path, managed_doc=doc))

    untracked_managed = managed_candidates(root, registry) - tracked_paths
    for rel in sorted(untracked_managed):
        errors.append(f"{rel}: managed markdown file is not listed in .specify/doc-registry.json")

    for path in repo_markdown_paths(root):
        rel = path.relative_to(root).as_posix()
        if rel in tracked_paths or rel in untracked_managed:
            continue
        errors.extend(validate_frontmatter(path.read_text(encoding="utf-8"), rel, managed_doc=docs_by_path.get(rel)))

    return sorted(dict.fromkeys(errors))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync", help="Rewrite managed and local Markdown metadata into frontmatter")
    subparsers.add_parser("lint", help="Check that repo Markdown metadata matches the frontmatter rules")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(__file__).resolve().parents[1]
    registry_path = root / ".specify" / "doc-registry.json"

    try:
        if args.command == "sync":
            changed = sync(root, registry_path)
            if changed:
                print(f"Synced {len(changed)} doc(s):")
                for rel in changed:
                    print(f"  {rel}")
            else:
                print("Doc metadata already in sync.")
            return 0

        errors = lint(root, registry_path)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Doc metadata lint failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print("Doc metadata lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
