#!/usr/bin/env python3
"""Unified deterministic workflow for managed repo docs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

try:
    from tools import doc_status
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    import doc_status  # type: ignore[no-redef]

UNRESOLVED_MARKERS = (
    "TODO(",
    "<!-- TODO:",
    "<!--TODO:",
    "TBD",
    "[NEEDS CLARIFICATION",
    ": not decided:",
)

STALE_REFERENCES = (
    "docs/README.md",
    "docs/decisions.md",
    "docs/open-questions.md",
    "docs/spec-driven-development.md",
    "docs/architecture-principles.md",
    "suppressor/specs/",
    "tools/doc_status.py",
)

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
TASK_ITEM_RE = re.compile(r"^- \[(?P<done>[ xX])\] ", re.MULTILINE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync", help="Rewrite managed doc metadata from the registry")
    subparsers.add_parser("lint", help="Check that managed doc metadata matches the registry")
    subparsers.add_parser("test", help="Run docs-tool unit tests")
    status_parser = subparsers.add_parser("status", help="Report deterministic docs status categories")
    status_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    subparsers.add_parser("all", help="Run sync, lint, test, and status")

    return parser.parse_args(argv)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def registry_path(root: Path) -> Path:
    return root / ".specify" / "doc-registry.json"


def managed_doc_paths(root: Path, registry: dict) -> list[Path]:
    docs = doc_status.registry_documents(registry)
    return [root / entry.path for entry in docs]


def load_feature_pointer(root: Path) -> str | None:
    feature_path = root / ".specify" / "feature.json"
    if not feature_path.is_file():
        return None
    try:
        data = json.loads(feature_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = data.get("feature_directory")
    return value if isinstance(value, str) and value else None


def feature_spec_dirs(root: Path) -> list[Path]:
    specs_dir = root / "specs"
    if not specs_dir.is_dir():
        return []
    return sorted(
        path
        for path in specs_dir.iterdir()
        if path.is_dir() and path.name != "000-repo-governance"
    )


def scan_markdown_paths(root: Path, registry: dict) -> list[Path]:
    paths: set[Path] = set(managed_doc_paths(root, registry))

    governance_dir = root / "specs" / "000-repo-governance"
    if governance_dir.is_dir():
        paths.update(governance_dir.rglob("*.md"))

    for feature_dir in feature_spec_dirs(root):
        paths.update(feature_dir.rglob("*.md"))

    return sorted(paths)


def strip_wrapping(target: str) -> str:
    stripped = target.strip()
    if stripped.startswith("<") and stripped.endswith(">"):
        return stripped[1:-1]
    return stripped


def local_link_errors(root: Path, path: Path, text: str) -> list[str]:
    errors: list[str] = []

    for match in MARKDOWN_LINK_RE.finditer(text):
        target = strip_wrapping(match.group(1))
        if not target or target.startswith("#"):
            continue
        if "://" in target or target.startswith("mailto:"):
            continue
        link_target = target.split("#", 1)[0]
        if not link_target:
            continue
        resolved = (root / link_target.lstrip("/")) if link_target.startswith("/") else (path.parent / link_target)
        if not resolved.exists():
            errors.append(f"{path.relative_to(root).as_posix()}: broken link -> {target}")

    return errors


def contains_tasks_completion(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    matches = list(TASK_ITEM_RE.finditer(text))
    return bool(matches) and all(match.group("done").lower() == "x" for match in matches)


def status_report(root: Path, registry_file: Path | None = None) -> dict[str, list[str]]:
    report = {
        "approval_needed": [],
        "manual_review_needed": [],
        "update_needed": [],
        "closure_needed": [],
        "registry_or_link_errors": [],
    }

    try:
        registry = doc_status.load_registry(registry_file or registry_path(root))
        tracked_docs = doc_status.registry_documents(registry)
    except (doc_status.RegistryError, json.JSONDecodeError) as exc:
        report["registry_or_link_errors"].append(f".specify/doc-registry.json: {exc}")
        return report

    for entry in tracked_docs:
        if "client-input-derived" in entry.review:
            report["approval_needed"].append(f"{entry.path}: explicit client approval still needed")
        if "unreviewed" in entry.review:
            report["manual_review_needed"].append(f"{entry.path}: manual review still needed")

    report["registry_or_link_errors"].extend(doc_status.lint(root, registry_file or registry_path(root)))

    for path in scan_markdown_paths(root, registry):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root).as_posix()
        for marker in UNRESOLVED_MARKERS:
            if marker in text:
                report["update_needed"].append(f"{rel}: contains unresolved marker {marker!r}")
        for stale_ref in STALE_REFERENCES:
            if stale_ref in text:
                report["update_needed"].append(f"{rel}: references stale path or command {stale_ref!r}")
        report["registry_or_link_errors"].extend(local_link_errors(root, path, text))

    active_feature = load_feature_pointer(root)
    if active_feature:
        active_dir = root / active_feature
        if not active_dir.is_dir():
            report["closure_needed"].append(
                f".specify/feature.json: points to missing feature directory {active_feature}"
            )
        elif contains_tasks_completion(active_dir / "tasks.md"):
            report["closure_needed"].append(
                f"{active_feature}: tasks are complete but the active feature pointer still targets it"
            )

    for feature_dir in feature_spec_dirs(root):
        rel = feature_dir.relative_to(root).as_posix()
        if contains_tasks_completion(feature_dir / "tasks.md") and rel != active_feature:
            report["closure_needed"].append(f"{rel}: completed feature spec should be closed or archived")

    for key in report:
        report[key] = sorted(dict.fromkeys(report[key]))

    return report


def print_status(report: dict[str, list[str]]) -> None:
    for category, items in report.items():
        print(f"{category}:")
        if not items:
            print("  - none")
            continue
        for item in items:
            print(f"  - {item}")


def run_sync(root: Path, registry_file: Path) -> int:
    try:
        changed = doc_status.sync(root, registry_file)
    except doc_status.RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if changed:
        print(f"Synced {len(changed)} doc(s):")
        for rel in changed:
            print(f"  {rel}")
    else:
        print("Doc metadata already in sync.")
    return 0


def run_lint(root: Path, registry_file: Path) -> int:
    try:
        errors = doc_status.lint(root, registry_file)
    except doc_status.RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Doc metadata lint failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print("Doc metadata lint passed.")
    return 0


def run_tests(root: Path) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tools" / "tests"), "-p", "test_*.py"],
        cwd=root,
        check=False,
    )
    return result.returncode


def has_blocking_status(report: dict[str, list[str]]) -> bool:
    return bool(report["update_needed"] or report["registry_or_link_errors"])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = repo_root()
    registry_file = registry_path(root)

    if args.command == "sync":
        return run_sync(root, registry_file)
    if args.command == "lint":
        return run_lint(root, registry_file)
    if args.command == "test":
        return run_tests(root)
    if args.command == "status":
        report = status_report(root, registry_file)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_status(report)
        return 1 if has_blocking_status(report) else 0

    if run_sync(root, registry_file) != 0:
        return 1
    if run_lint(root, registry_file) != 0:
        return 1
    if run_tests(root) != 0:
        return 1

    report = status_report(root, registry_file)
    print_status(report)
    return 1 if has_blocking_status(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
