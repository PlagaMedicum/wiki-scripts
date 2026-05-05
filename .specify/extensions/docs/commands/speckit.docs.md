---
description: Run the repo's explicit docs workflow gate
docmeta:
  status: maintained
  review: workflow-local
  source: document-local metadata
---

# Run Docs Workflow


Run the repo-local deterministic docs gate.

## Behavior

This command runs the same final gate as `make docs`:

1. sync and augment Markdown frontmatter metadata
2. lint managed and local frontmatter metadata
3. run docs-tool tests
4. print deterministic doc status categories

## Execution

- **Bash**: `.specify/scripts/bash/run-doc-workflow.sh`

## Notes

- This command is explicit. It is not auto-executed as a mutating hook.
- Use it at the end of non-trivial work after `spec.md`, `plan.md`, `tasks.md`, and implementation.
- For safety-, reliability-, or performance-sensitive work, confirm that resource goals, low-spec
  verification, recovery/status evidence, and incident lessons have been captured before treating
  the docs gate as complete. Concision is fine; missing performance evidence or operational lessons
  is not.
- If an active human-safety freeze is in effect, confirm the docs gate is run for the active safety
  feature and its direct enablers only. During the active suppressor MVP freeze, unrelated docs or
  workflow cleanup must not displace `specs/001-real-time-suppression/` release evidence.
- Use `python3 tools/doc_workflow.py sync --dry-run --scope managed` or `--scope active-feature`
  when you need to preview metadata rewrites before running the full gate.
- The text status output uses stable compact section labels:
  `APP`, `REV`, `ANS`, `COM`, `UPD`, `CLS`, `ERR`.
- The status output is a review/closure queue, not an automatic approval system.
- Managed-doc review labels are additive, so provenance and terminal review/approval labels can
  coexist without remaining falsely pending.
- Managed-governance review or approval changes become durable only through
  `.specify/doc-registry.json` plus sync, not through hand-edited Markdown review labels.
- If the active feature tracks pending answers, requested comments, or queued updates in
  `questions.md` and `review-queue.md`, those items can appear in the status output too.
- Repo-level unresolved governance follow-up belongs in `specs/000-repo-governance/research.md`
  rather than as inline TODO review comments in maintained governance docs.
- Literal marker syntax shown in inline code or fenced contract examples should not be treated as a
  live unresolved item.
