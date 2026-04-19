#!/usr/bin/env python3
"""Sync and lint managed Markdown metadata from a deterministic registry."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

DOCMETA_START = "<!-- DOCMETA:START -->"
DOCMETA_END = "<!-- DOCMETA:END -->"
SOURCE_LINE = "> Source: .specify/doc-registry.json"
DOCMETA_RE = re.compile(
    rf"{re.escape(DOCMETA_START)}\n.*?\n{re.escape(DOCMETA_END)}\n?",
    re.DOTALL,
)


@dataclass(frozen=True)
class ManagedDoc:
    path: str
    status: str
    review: tuple[str, ...]
    purpose: str


class RegistryError(RuntimeError):
    """Registry validation failed."""


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


def build_block(doc: ManagedDoc) -> str:
    review = ", ".join(doc.review)
    return (
        f"{DOCMETA_START}\n"
        f"> Status: {doc.status}\n"
        f"> Review: {review}\n"
        f"> Purpose: {doc.purpose}\n"
        f"{SOURCE_LINE}\n"
        f"{DOCMETA_END}\n"
    )


def insert_block(text: str, block: str, rel_path: str) -> str:
    if DOCMETA_RE.search(text):
        return DOCMETA_RE.sub(block, text, count=1)

    lines = text.splitlines(keepends=True)
    h1_index = next((index for index, line in enumerate(lines) if line.startswith("# ")), None)
    if h1_index is None:
        raise RegistryError(f"{rel_path}: expected first line to be an H1 heading")

    after_h1 = h1_index + 1
    while after_h1 < len(lines) and lines[after_h1].strip() == "":
        after_h1 += 1

    legacy_end = after_h1
    while legacy_end < len(lines) and lines[legacy_end].startswith("> "):
        legacy_end += 1
    while legacy_end < len(lines) and lines[legacy_end].strip() == "":
        legacy_end += 1

    body_start = legacy_end if legacy_end > after_h1 else after_h1
    return (
        "".join(lines[: h1_index + 1])
        + "\n"
        + block
        + ("\n" if body_start < len(lines) else "")
        + "".join(lines[body_start:])
    )


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
    changed: list[str] = []

    for doc in docs:
        path = root / doc.path
        if not path.is_file():
            raise RegistryError(f"tracked doc is missing: {doc.path}")
        text = path.read_text(encoding="utf-8")
        updated = insert_block(text, build_block(doc), doc.path)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(doc.path)
    return changed


def lint(root: Path, registry_path: Path) -> list[str]:
    registry = load_registry(registry_path)
    docs = registry_documents(registry)
    tracked_paths = {doc.path for doc in docs}
    errors: list[str] = []

    for doc in docs:
        path = root / doc.path
        if not path.is_file():
            errors.append(f"tracked doc is missing: {doc.path}")
            continue
        expected = build_block(doc)
        text = path.read_text(encoding="utf-8")
        if not DOCMETA_RE.search(text):
            errors.append(f"{doc.path}: missing DOCMETA block")
            continue
        actual = DOCMETA_RE.search(text).group(0)
        if actual != expected:
            errors.append(f"{doc.path}: DOCMETA block does not match registry")

    for rel in sorted(managed_candidates(root, registry) - tracked_paths):
        errors.append(f"{rel}: managed markdown file is not listed in .specify/doc-registry.json")

    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync", help="Rewrite managed doc metadata from the registry")
    subparsers.add_parser("lint", help="Check that managed doc metadata matches the registry")

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
