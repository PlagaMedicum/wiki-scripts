from __future__ import annotations

import contextlib
import io
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
                "reviewed",
                "approved",
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

    def test_sync_writes_registry_backed_frontmatter(self) -> None:
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
            self.assertTrue(
                text.startswith(
                    "---\n"
                    "docmeta:\n"
                    "  status: maintained\n"
                    "  review: unreviewed\n"
                    "  purpose: Example purpose.\n"
                    "  source: .specify/doc-registry.json\n"
                    "---\n\n# Example\n"
                )
            )
            self.assertNotIn(doc_status.DOCMETA_START, text)
            self.assertIn("Body.\n", text)

    def test_sync_uses_registry_frontmatter_for_root_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "README.md"
            path.write_text("# Repo\n\nBody.\n", encoding="utf-8")
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

            changed = doc_status.sync(root, registry)

            self.assertEqual(changed, ["README.md"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("source: .specify/doc-registry.json", text)
            self.assertTrue(text.startswith("---\ndocmeta:\n"))
            self.assertNotIn(doc_status.DOCMETA_START, text)

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

    def test_sync_moves_frontmatter_ahead_of_leading_comment(self) -> None:
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
            self.assertTrue(text.startswith("---\ndocmeta:\n"))
            self.assertIn("\n<!-- comment -->\n# Example\n\nBody.\n", text)

    def test_lint_fails_when_frontmatter_drifts_from_registry(self) -> None:
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

            self.assertEqual(errors, ["docs/example.md: docmeta.review does not match registry"])

    def test_lint_fails_for_nonmanaged_missing_frontmatter_docmeta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            hidden = root / ".agents" / "skills" / "demo" / "SKILL.md"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            hidden.parent.mkdir(parents=True, exist_ok=True)
            hidden.write_text("---\nname: demo\n---\n\n# Demo Skill\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["reviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            errors = doc_status.lint(root, registry)

            self.assertIn(".agents/skills/demo/SKILL.md: missing docmeta mapping in YAML frontmatter", errors)
            self.assertIn(".agents/skills/demo/SKILL.md: missing status", errors)
            self.assertIn(".agents/skills/demo/SKILL.md: missing review labels", errors)

    def test_lint_fails_for_nonmanaged_legacy_docmeta_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature = root / "specs" / "001-example" / "spec.md"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature.parent.mkdir(parents=True, exist_ok=True)
            feature.write_text(
                "# Example\n\nBody first.\n\n"
                "<!-- DOCMETA:START -->\n"
                "<details class=\"docmeta-block\">\n"
                "<summary><strong>DOCMETA</strong> | st: draft | rv: local | src: local</summary>\n"
                "\n"
                "**Status**: `draft`  \n"
                "**Review**: `local`  \n"
                "**Purpose**: Example feature doc.  \n"
                "**Source**: `document-local metadata`\n"
                "</details>\n"
                "<!-- DOCMETA:END -->\n",
                encoding="utf-8",
            )
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["reviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            errors = doc_status.lint(root, registry)

            self.assertIn(
                "specs/001-example/spec.md: legacy DOCMETA header must be migrated to YAML frontmatter",
                errors,
            )

    def test_sync_merges_skill_frontmatter_without_duplicate_purpose_or_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            skill = root / ".agents" / "skills" / "demo" / "SKILL.md"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_text(
                "---\n"
                'name: "demo"\n'
                'description: "Demo skill."\n'
                'compatibility: "Requires demo"\n'
                "metadata:\n"
                '  author: "demo"\n'
                '  source: "templates/demo.md"\n'
                "---\n\n"
                "# Demo\n\n"
                "<!-- DOCMETA:START -->\n"
                "<details class=\"docmeta-block\">\n"
                "<summary><strong>DOCMETA</strong> | st: maintained | rv: workflow-local | src: local</summary>\n"
                "\n"
                "**Status**: `maintained`  \n"
                "**Review**: `workflow-local`  \n"
                "**Purpose**: Demo skill.  \n"
                "**Source**: `document-local metadata`\n"
                "</details>\n"
                "<!-- DOCMETA:END -->\n\n"
                "Body.\n",
                encoding="utf-8",
            )
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["reviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            changed = doc_status.sync(root, registry)

            self.assertIn(".agents/skills/demo/SKILL.md", changed)
            text = skill.read_text(encoding="utf-8")
            self.assertIn('name: demo', text)
            self.assertIn('description: Demo skill.', text)
            self.assertIn('source: templates/demo.md', text)
            self.assertIn("docmeta:\n  status: maintained\n  review: workflow-local\n", text)
            self.assertNotIn("purpose:", text.split("---\n\n", 1)[0])
            self.assertNotIn("document-local metadata", text)
            self.assertNotIn(doc_status.DOCMETA_START, text)

    def test_frontmatter_is_authoritative_when_legacy_docmeta_disagrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "README.md"
            path.write_text(
                "---\n"
                "docmeta:\n"
                "  status: maintained\n"
                "  review: reviewed\n"
                "  purpose: Repo overview.\n"
                "  source: .specify/doc-registry.json\n"
                "---\n\n"
                "# Repo\n\n"
                "<!-- DOCMETA:START -->\n"
                "<details class=\"docmeta-block\">\n"
                "<summary><strong>DOCMETA</strong> | st: maintained | rv: unreviewed | src: registry</summary>\n"
                "\n"
                "**Status**: `maintained`  \n"
                "**Review**: `unreviewed`  \n"
                "**Purpose**: Repo overview.  \n"
                "**Source**: `.specify/doc-registry.json`\n"
                "</details>\n"
                "<!-- DOCMETA:END -->\n\n"
                "Body.\n",
                encoding="utf-8",
            )
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["reviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            errors = doc_status.lint(root, registry)

            self.assertEqual(errors, [])

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

    def test_status_respects_additive_terminal_review_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            constitution = root / ".specify" / "memory" / "constitution.md"
            constitution.parent.mkdir(parents=True, exist_ok=True)
            readme.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            constitution.write_text("# Constitution\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["unreviewed", "reviewed"],
                        "purpose": "Repo overview.",
                    },
                    {
                        "path": ".specify/memory/constitution.md",
                        "status": "maintained",
                        "review": ["client-input-derived", "approved"],
                        "purpose": "Repo constitution.",
                    },
                ],
                managed_roots=["README.md", ".specify/memory/constitution.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(report["manual_review_needed"], [])
            self.assertEqual(report["approval_needed"], [])

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

    def test_status_suppresses_closure_when_feature_queue_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_dir = root / "specs" / "001-example"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_dir.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            (feature_dir / "tasks.md").write_text("# Tasks\n\n- [x] Done\n", encoding="utf-8")
            (feature_dir / "review-queue.md").write_text(
                "# Queue\n\n"
                "| ID | Status | Subject | Owner | Note |\n"
                "|----|--------|---------|-------|------|\n"
                "| RQ001 | comment_requested | [spec.md](./spec.md) | client | Review before closure |\n",
                encoding="utf-8",
            )
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["reviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(report["closure_needed"], [])
            self.assertEqual(
                report["comment_requested"],
                [
                    "specs/001-example/review-queue.md: RQ001 [spec.md](./spec.md) (client) - Review before closure"
                ],
            )

    def test_status_handles_missing_feature_pointer_without_queue_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["reviewed"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(report["answer_needed"], [])
            self.assertEqual(report["comment_requested"], [])
            self.assertEqual(report["closure_needed"], [])

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

    def test_status_reports_feature_question_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_dir = root / "specs" / "001-example"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_dir.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            (feature_dir / "questions.md").write_text(
                "# Questions\n\n"
                "### Q001: Add answer queue?\n\n"
                "- Status: pending-answer\n\n"
                "### Q002: Require paired docs updates?\n\n"
                "- Status: pending-comment\n\n"
                "### Q003: Answered already\n\n"
                "- Status: answered\n\n"
                "### Q004: Commented already\n\n"
                "- Status: commented\n\n"
                "### Q005: Already handled\n\n"
                "- Status: resolved\n",
                encoding="utf-8",
            )
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
                report["answer_needed"],
                ["specs/001-example/questions.md: Q001 Add answer queue?"],
            )
            self.assertEqual(
                report["comment_requested"],
                ["specs/001-example/questions.md: Q002 Require paired docs updates?"],
            )

    def test_status_reports_feature_review_queue_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_dir = root / "specs" / "001-example"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_dir.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            (feature_dir / "review-queue.md").write_text(
                "# Queue\n\n"
                "| ID | Status | Subject | Owner | Note |\n"
                "|----|--------|---------|-------|------|\n"
                "| RQ001 | comment_requested | [spec.md](./spec.md) | client | Review the updated scope |\n"
                "| RQ002 | update_needed | [plan.md](./plan.md) | maintainer | Fold in the new queue semantics |\n"
                "| RQ003 | approval_needed | [specs/README.md](../README.md) | client | Summary only |\n",
                encoding="utf-8",
            )
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
                report["comment_requested"],
                [
                    "specs/001-example/review-queue.md: RQ001 [spec.md](./spec.md) (client) - Review the updated scope"
                ],
            )
            self.assertEqual(
                report["update_needed"],
                [
                    "specs/001-example/review-queue.md: RQ002 [plan.md](./plan.md) (maintainer) - Fold in the new queue semantics"
                ],
            )

    def test_status_ignores_feature_queue_approval_rows_for_registry_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_dir = root / "specs" / "001-example"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_dir.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            (feature_dir / "review-queue.md").write_text(
                "# Queue\n\n"
                "| ID | Status | Subject | Owner | Note |\n"
                "|----|--------|---------|-------|------|\n"
                "| RQ009 | approval_needed | [spec.md](./spec.md) | client | Feature-local note only |\n",
                encoding="utf-8",
            )
            registry = self.write_registry(
                root,
                [
                    {
                        "path": "README.md",
                        "status": "maintained",
                        "review": ["client-input-derived", "approved"],
                        "purpose": "Repo overview.",
                    }
                ],
                managed_roots=["README.md"],
            )

            doc_status.sync(root, registry)
            report = doc_workflow.status_report(root, registry)

            self.assertEqual(report["approval_needed"], [])
            self.assertEqual(report["comment_requested"], [])
            self.assertEqual(report["update_needed"], [])

    def test_status_does_not_treat_specify_docs_readme_as_stale_docs_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_doc = root / "specs" / "001-example" / "spec.md"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_doc.parent.mkdir(parents=True, exist_ok=True)
            feature_doc.write_text(
                "# Feature\n\nSee `.specify/extensions/docs/README.md` for the extension docs.\n",
                encoding="utf-8",
            )
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

            self.assertEqual(report["update_needed"], [])

    def test_status_does_not_treat_tools_doc_status_py_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_doc = root / "specs" / "001-example" / "plan.md"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_doc.parent.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            feature_doc.write_text(
                "# Plan\n\nUpdate `tools/doc_status.py` and `tools/doc_workflow.py` together.\n",
                encoding="utf-8",
            )
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

            self.assertEqual(report["update_needed"], [])

    def test_status_reports_lowercase_todo_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "README.md"
            path.write_text("# Repo\n\n<!-- todo: tighten wording -->\n", encoding="utf-8")
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

    def test_status_ignores_marker_examples_in_inline_and_fenced_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            feature_dir = root / "specs" / "001-example"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            feature_dir.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-example"}), encoding="utf-8")
            (feature_dir / "contract.md").write_text(
                "# Contract\n\n"
                "Use marker syntax such as `<!-- TODO:` or `TBD` only for real unresolved items.\n\n"
                "```markdown\n"
                "Pending follow-up remains here. <!-- TODO: tighten wording -->\n"
                "```\n",
                encoding="utf-8",
            )
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

            self.assertEqual(report["update_needed"], [])

    def test_status_ignores_inactive_feature_markdown_for_update_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = root / "README.md"
            active_dir = root / "specs" / "001-active"
            inactive_dir = root / "specs" / "002-inactive"
            feature_json = root / ".specify" / "feature.json"
            tracked.write_text("# Repo\n\nBody.\n", encoding="utf-8")
            active_dir.mkdir(parents=True, exist_ok=True)
            inactive_dir.mkdir(parents=True, exist_ok=True)
            feature_json.parent.mkdir(parents=True, exist_ok=True)
            feature_json.write_text(json.dumps({"feature_directory": "specs/001-active"}), encoding="utf-8")
            (active_dir / "spec.md").write_text("# Active\n\nBody.\n", encoding="utf-8")
            (inactive_dir / "spec.md").write_text("# Inactive\n\n<!-- TODO: old note -->\n", encoding="utf-8")
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

            self.assertEqual(report["update_needed"], [])

    def test_print_status_uses_compact_section_labels(self) -> None:
        stream = io.StringIO()
        report = {
            "approval_needed": ["README.md: explicit client approval still needed"],
            "manual_review_needed": [],
            "answer_needed": [],
            "comment_requested": [],
            "update_needed": [],
            "closure_needed": [],
            "registry_or_link_errors": [],
        }

        with contextlib.redirect_stdout(stream):
            doc_workflow.print_status(report)

        output = stream.getvalue()
        self.assertIn("Legend: APP=approval_needed", output)
        self.assertIn("APP:\n  - README.md: explicit client approval still needed", output)
        self.assertIn("ERR:\n  - none", output)


if __name__ == "__main__":
    unittest.main()
