from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import doc_status
from tools import doc_workflow


class DocStatusTests(unittest.TestCase):
    def write_registry(self, root: Path, documents: list[dict], managed_roots: list[str] | None = None) -> Path:
        registry = {
            "version": 1,
            "allowed_statuses": ["maintained", "draft", "generated", "archived"],
            "allowed_reviews": [
                "unreviewed",
                "code-reviewed",
                "client-input-derived",
                "client-confirmed",
                "operator-verified",
                "generated",
            ],
            "managed_roots": managed_roots or ["docs"],
            "exclude_globs": ["specs/*/**"],
            "documents": documents,
        }
        registry_path = root / ".specify" / "doc-registry.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        return registry_path

    def test_sync_inserts_docmeta_after_h1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "example.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Example\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "docs/example.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Example purpose.",
                    }
                ],
            )

            changed = doc_status.sync(root, registry)

            self.assertEqual(changed, ["docs/example.md"])
            text = path.read_text(encoding="utf-8")
            self.assertIn(doc_status.DOCMETA_START, text)
            self.assertIn("> Review: unreviewed", text)
            self.assertIn("Body.\n", text)

    def test_lint_fails_for_untracked_managed_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "docs" / "tracked.md"
            untracked = root / "docs" / "untracked.md"
            tracked.parent.mkdir(parents=True, exist_ok=True)
            tracked.write_text("# Tracked\n\nBody.\n", encoding="utf-8")
            untracked.write_text("# Untracked\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "docs/tracked.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Tracked purpose.",
                    }
                ],
            )

            doc_status.sync(root, registry)
            errors = doc_status.lint(root, registry)

            self.assertEqual(
                errors,
                ["docs/untracked.md: managed markdown file is not listed in .specify/doc-registry.json"],
            )

    def test_sync_handles_leading_comment_before_h1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "example.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<!-- comment -->\n# Example\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "docs/example.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Example purpose.",
                    }
                ],
            )

            changed = doc_status.sync(root, registry)

            self.assertEqual(changed, ["docs/example.md"])
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("<!-- comment -->\n# Example\n\n<!-- DOCMETA:START -->\n"))

    def test_lint_fails_when_docmeta_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "example.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Example\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "docs/example.md",
                        "status": "maintained",
                        "review": ["code-reviewed"],
                        "purpose": "Example purpose.",
                    }
                ],
            )

            doc_status.sync(root, registry)
            text = path.read_text(encoding="utf-8").replace("code-reviewed", "unreviewed")
            path.write_text(text, encoding="utf-8")

            errors = doc_status.lint(root, registry)

            self.assertEqual(errors, ["docs/example.md: DOCMETA block does not match registry"])

    def test_status_reports_review_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unreviewed = root / "README.md"
            derived = root / "specs" / "000-repo-governance" / "spec.md"
            derived.parent.mkdir(parents=True, exist_ok=True)
            unreviewed.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            derived.write_text("# Governance\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Repo overview.",
                    },
                    {
                        "path": "specs/000-repo-governance/spec.md",
                        "status": "maintained",
                        "review": ["client-input-derived"],
                        "purpose": "Governance decisions.",
                    },
                ],
                managed_roots=["README.md", "specs/000-repo-governance"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(report["manual_review_needed"], ["README.md: manual review still needed"])
            self.assertEqual(
                report["approval_needed"],
                ["specs/000-repo-governance/spec.md: explicit client approval still needed"],
            )

    def test_status_reports_completed_active_feature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_tasks = root / "specs" / "001-example" / "tasks.md"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_tasks.parent.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_tasks.write_text("# Tasks\n\n- [x] Done\n", encoding="utf-8")
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(
                report["closure_needed"],
                ["specs/001-example: tasks are complete but the active feature pointer still targets it"],
            )

    def test_status_reports_broken_local_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "README.md"
            path.write_text("# Repo\n\nSee [Missing](missing.md).\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(report["registry_or_link_errors"], ["README.md: broken link -> missing.md"])

    def test_status_reports_html_todo_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "README.md"
            path.write_text("# Repo\n\n<!-- TODO: tighten wording -->\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["unreviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(
                report["update_needed"],
                ["README.md: contains unresolved marker '<!-- TODO:'"],
            )


if __name__ == "__main__":
    unittest.main()
