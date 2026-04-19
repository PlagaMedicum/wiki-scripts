---
docmeta:
  status: maintained
  review: workflow-local
  purpose: Explains the repo-local docs extension, command surface, and frontmatter workflow.
  source: document-local metadata
---

# Deterministic Docs Workflow Extension


This local extension exposes one explicit command:

- `speckit.docs`

It runs the same repo-local final gate as `make docs` and `python3 tools/doc_workflow.py all`.

The command is intentionally explicit. It is not configured as an automatic mutating hook.

The docs gate is frontmatter-first. Managed docs sync registry-backed metadata into YAML
frontmatter, while local docs are schema-linted against the same frontmatter contract without
claiming registry-backed review state.

The final status report is deterministic and grouped into:

- `approval_needed`
- `manual_review_needed`
- `answer_needed`
- `comment_requested`
- `update_needed`
- `closure_needed`
- `registry_or_link_errors`

Managed-doc review semantics are additive. Provenance labels such as `client-input-derived` may
coexist with terminal labels such as `approved`, and the queue is derived from the combination
rather than from one label in isolation.

If the active feature has `questions.md` or `review-queue.md` files with the documented queue
schema, the status report also surfaces pending direct answers, requested comments, and feature
updates from those files.

Unresolved-marker detection is case-insensitive, but marker syntax shown inside inline code or
fenced code examples is treated as documentation, not as live unresolved work.
