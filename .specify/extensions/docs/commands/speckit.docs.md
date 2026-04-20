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
- Use `python3 tools/doc_workflow.py sync --dry-run --scope managed` or `--scope active-feature`
  when you need to preview metadata rewrites before running the full gate.
- The text status output uses stable compact section labels:
  `APP`, `REV`, `ANS`, `COM`, `UPD`, `CLS`, `ERR`.
- The status output is a review/closure queue, not an automatic approval system.
- Managed-doc review labels are additive, so provenance and terminal review/approval labels can
  coexist without remaining falsely pending.
- If the active feature tracks pending answers, requested comments, or queued updates in
  `questions.md` and `review-queue.md`, those items can appear in the status output too.
- Literal marker syntax shown in inline code or fenced contract examples should not be treated as a
  live unresolved item.
