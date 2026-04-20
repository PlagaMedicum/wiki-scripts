---
docmeta:
  status: working
  review: feature-local
  purpose: Working loop for docs governance hardening and the active docs queue.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Quickstart: Docs Governance Hardening


## Review The Current Queue

Run the deterministic docs status report:

```bash
rtk python3 tools/doc_workflow.py status
```

If you need machine-readable output:

```bash
rtk python3 tools/doc_workflow.py status --json
```

Read the active feature queue alongside the status output:

- [`questions.md`](./questions.md)
- [`review-queue.md`](./review-queue.md)

If `.specify/feature.json` is absent, the command still reports managed-doc queues; only the
feature-local queue categories stay empty.

## Record New Human Questions

Do not leave direct human questions only in chat. Add them to:

- [`questions.md`](./questions.md) for open questions and requested comments
- [`review-queue.md`](./review-queue.md) for the current human action queue

If a question is answered in chat, fold it into one of those files immediately and move the entry
to `answered`, `commented`, or `resolved` as appropriate.

If a feature-local queue and the registry imply different durable review state, update the feature
queue to request alignment work and update `.specify/doc-registry.json` for the durable state
change.

## Validate The Docs Workflow

Run the explicit docs gate:

```bash
rtk python3 tools/doc_workflow.py all
```

Equivalent repo-local command:

```text
/speckit.docs
```

## Preview Or Narrow Metadata Rewrites

Preview managed-doc metadata rewrites without mutating files:

```bash
rtk python3 tools/doc_workflow.py sync --dry-run --scope managed
```

Preview only active-feature metadata rewrites:

```bash
rtk python3 tools/doc_workflow.py sync --dry-run --scope active-feature
```

Apply a broader repo-wide metadata sync only when you actually intend to mutate the selected
surface:

```bash
rtk python3 tools/doc_workflow.py sync --scope all
```

Use these modes to distinguish durable managed-doc sync from broader frontmatter migration.

## Preserve Existing Plans By Default

Planning setup now preserves an existing non-empty `plan.md` unless overwrite is requested
explicitly:

```bash
rtk bash .specify/scripts/bash/setup-plan.sh --json
```

Only use `--force` when you deliberately want to replace the current plan with the template:

```bash
rtk bash .specify/scripts/bash/setup-plan.sh --json --force
```

The script reports `PLAN_ACTION` so wrappers and tests can tell whether the run preserved the
current plan or copied the template.

## Close Out The Feature Carefully

A passing docs gate means the current tree is coherent. It does not automatically mean the feature
is approved, closure-ready, or landed in repo history.

Use this close-out sequence:

1. Run `rtk python3 tools/doc_workflow.py status --json` and confirm that the active feature has no
   pending question or review-queue items left to resolve.
2. Run `rtk python3 tools/doc_workflow.py all` and confirm the docs gate still passes.
3. Run `rtk git status --short` and confirm the active feature artifacts and related tooling/docs are
   tracked the way you expect before treating the work as landed.
4. Only after the review queue is clear and the tree is landed intentionally should `.specify/feature.json`
   stop pointing at this feature.

The feature spec may remain `Draft` until those review and approval steps are explicitly cleared.

## Follow-On Features Planned From This Work

- `002-suppressor-journalling-policy`
- `003-suppressor-operator-contract`
- `004-biblio-boundary-cut`
- `005-biblio-proof-rule`

Those follow-ons stay separate so this feature remains focused on workflow and governance hardening,
with `suppressor` work explicitly prioritized next.
