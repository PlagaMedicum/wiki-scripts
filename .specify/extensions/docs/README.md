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

For safety-, reliability-, or performance-sensitive work, the docs gate is also the point where
resource goals, low-spec verification, recovery/status evidence, and durable incident lessons must
be present in the affected maintained or project-local docs. Documentation can be concise, but it
must not drop the performance evidence or operational lessons needed to repeat the decision.
For sensitive-edit, suppression, moderation, or incident work, those lessons must be preserved with
synthetic or redacted evidence only. The docs gate must not pass tracked files that copy real editor
names, page titles, revision IDs, diff URLs, comments, screenshots, or log excerpts identifying a
real sensitive edit.

Config changes are part of that evidence. If tracked config files, config schema, defaults,
environment variable names, loading semantics, or deployment-required sections changed, the docs
gate must preserve the specific motivation, explicit human review evidence, compatibility or
migration behavior, deployment-path verification, and rollback/fallback notes.

If an active human-safety freeze is in effect, the docs gate must preserve that routing rule and the
minimum release evidence for the active safety feature. During the active suppressor MVP freeze,
that evidence belongs in `specs/001-real-time-suppression/` and `suppressor/` docs, not in unrelated
workflow or tool cleanup.

The gate command and the maintenance command are different surfaces:

- `python3 tools/doc_workflow.py all` or `/speckit.docs` runs the full docs gate
- `python3 tools/doc_workflow.py sync ...` is the explicit metadata-maintenance entrypoint

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

Managed-governance review or approval changes are durable only when `.specify/doc-registry.json`
is updated and synced. Hand-edited review labels in managed Markdown are not the source of truth.

If the active feature has `questions.md` or `review-queue.md` files with the documented queue
schema, the status report also surfaces pending direct answers, requested comments, and feature
updates from those files.

Repo-level unresolved governance follow-up belongs in `specs/000-repo-governance/research.md`.
Maintained governance docs should not keep unresolved inline TODO-style review comments once that
follow-up has been captured in an authoritative temporary surface.

Unresolved-marker detection is case-insensitive, but marker syntax shown inside inline code or
fenced code examples is treated as documentation, not as live unresolved work.

## Safe Metadata Maintenance

Preview pending metadata rewrites without mutating files:

```bash
python3 tools/doc_workflow.py sync --dry-run --scope managed
python3 tools/doc_workflow.py sync --dry-run --scope active-feature
```

Apply a broad rewrite only when you intend to mutate the selected scope:

```bash
python3 tools/doc_workflow.py sync --scope all
```

Scope meanings:

- `managed`: registry-managed docs only
- `active-feature`: Markdown under the feature pointed to by `.specify/feature.json`
- `all`: repo-wide Markdown sync

Frontmatter is authoritative when both frontmatter and legacy `DOCMETA` are present. Legacy
`DOCMETA` may still be parsed during migration, but `DOCMETA`-only workflow docs are no longer the
maintained contract.

Broad metadata sync and feature-generation are different write surfaces. Use scope or dry-run for
the former, and explicit overwrite actions for the latter. If a broad rewrite can invalidate local
workflow assumptions or previous setup expectations, require explicit operator confirmation before
the mutating run.
