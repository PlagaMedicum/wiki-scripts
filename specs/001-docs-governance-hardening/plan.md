---
docmeta:
  status: working
  review: feature-local
  purpose: Implementation plan and closure path for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Implementation Plan: Docs Governance Hardening


## Summary

Bring `001-docs-governance-hardening` from "implemented in the tree" to "artifact-coherent and
review-ready" by reconciling the feature stack with the delivered frontmatter-first workflow and
its safety guardrails. The core implementation already exists: `/speckit.docs`, frontmatter-first
metadata migration, compact status labels, compact `biblio` and `suppressor` technical surfaces,
and the follow-on roadmap. This plan focuses on the remaining engineering work needed to make that
implementation honest and maintainable:

- make broad metadata rewrites inspectable and scopeable
- make plan generation preserve filled artifacts unless `--force` is used
- align `spec.md`, `research.md`, `data-model.md`, `quickstart.md`,
  `contracts/status-report.md`, and `tasks.md` with the implemented design
- keep implemented, review-open, and closure-ready as separate lifecycle states

## Current State

- **Landed in repo history**: `/speckit.docs` rename, frontmatter-first metadata migration,
  compact docs-status labels, compact `biblio` and `suppressor` technical output, and the explicit
  follow-on roadmap.
- **Implemented in this working pass**: scoped and dry-run metadata sync in `tools/doc_status.py`
  and `tools/doc_workflow.py`, no-silent-overwrite guardrail in
  `.specify/scripts/bash/setup-plan.sh`, and regression tests for both.
- **Still open**: client comment on the feature docs, explicit approval for three
  `specs/000-repo-governance/*` docs, and eventual `.specify/feature.json` cleanup after those
  review queues are cleared.

## Delivery Priorities

1. Finish write-surface safety:
   - `doc_status.py sync` and `doc_workflow.py sync` must expose `--dry-run` and
     `--scope {all,managed,active-feature}`
   - `.specify/scripts/bash/setup-plan.sh` must preserve an existing non-empty `plan.md` unless
     `--force` is passed
2. Reconcile the feature artifacts:
   - all design docs must describe the same frontmatter-first, lean-by-type metadata model
   - all planning docs must describe the same write-surface safety rules and close-out model
3. Preserve lifecycle clarity:
   - completed implementation must remain distinct from review-open and closure-ready
   - `closure_needed` must stay suppressed while feature-local review items remain pending
4. Preserve the conservative `.specify` model:
   - durable approval/manual-review state stays anchored to `.specify/doc-registry.json`
   - docs-maintenance and feature generation remain separate documented write surfaces

## Technical Context

**Language/Version**: Python 3.x for repo tooling; Markdown, JSON, and shell-script workflow docs  
**Primary Dependencies**: Python standard library, existing `tools/doc_workflow.py`,
`tools/doc_status.py`, `.specify/scripts/bash/setup-plan.sh`, Spec Kit shell scripts, git for
documented close-out hygiene  
**Storage**: Repository Markdown and JSON files under `.specify/`, `specs/`, `README.md`, and
`tools/`  
**Testing**: `python3 -m unittest discover -s tools/tests -p 'test_*.py'`, docs gate via
`python3 tools/doc_workflow.py all`, plus targeted regression tests for sync scoping, dry-run
preview, and no-silent-overwrite plan setup  
**Target Platform**: Local maintainer shell in this repository  
**Project Type**: Repo tooling plus governance/documentation workflow hardening  
**Performance Goals**: Deterministic docs status should remain fast enough for routine local use on
the current repo size  
**Constraints**: No automatic approvals; preserve the standing-governance vs feature-doc boundary;
keep review states explicit and file-backed; keep durable approval/manual-review state anchored to
`.specify/doc-registry.json`; keep repo-local Spec Kit overrides conservative unless explicitly
approved; do not turn the docs gate into a general git policy engine; do not silently overwrite a
filled feature artifact  
**Scale/Scope**: One repo, one standing governance stack, one active hardening feature, and one
late-stage reconciliation slice that makes the existing implementation and docs stack agree

If a direct human answer is still required, write it into `questions.md` or a feature-local review
file and either resolve it during research or stop instead of inventing policy. Do not rewrite
managed-doc review labels by hand; change `.specify/doc-registry.json` when durable review state
changes.

## Constitution Check

*GATE: Must pass before implementation and be re-checked after design reconciliation.*

- **I. Separate Tools First**: Pass. The work stays inside repo workflow tooling and governance
  docs. It does not merge `biblio` and `suppressor` or alter their ownership boundaries.
- **II. Explicit Boundaries, Minimal Coupling**: Pass. The remediation makes the boundary between
  registry-managed review state, feature-local queue state, and feature-generation scripts stricter,
  not looser.
- **III. Narrow, Risk-Based Scope**: Pass. The slice is limited to status semantics, proof tests,
  write-surface safety, lifecycle clarity, and close-out discipline that came out of the analysis
  findings.
- **IV. Deterministic Documentation And Honest Status**: Pass if frontmatter remains authoritative,
  broad rewrites are inspectable before mutation, and review-open versus closure-ready states are
  documented explicitly.
- **V. Spec Kit First For Non-Trivial Work**: Pass. The feature continues to use `spec.md`,
  `plan.md`, and then refreshed `tasks.md` before any further implementation.

Document impact in this remediation slice:

- `.specify/scripts/bash/setup-plan.sh`
- `.specify/extensions/docs/README.md`
- `.specify/extensions/docs/commands/speckit.docs.md`
- `specs/001-docs-governance-hardening/plan.md`
- `specs/001-docs-governance-hardening/research.md`
- `specs/001-docs-governance-hardening/data-model.md`
- `specs/001-docs-governance-hardening/quickstart.md`
- `specs/001-docs-governance-hardening/contracts/status-report.md`
- `specs/001-docs-governance-hardening/tasks.md`
- `tools/doc_workflow.py`
- `tools/doc_status.py`
- `tools/tests/test_doc_workflow.py`
- optionally `review-queue.md` if human review items need to reflect the refined close-out model

Post-design re-check: still passes. The design tightens write-surface safety and lifecycle honesty
without relaxing any constitution rule or inventing automatic approval behavior.

## Project Structure

### Feature Docs

```text
specs/001-docs-governance-hardening/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── questions.md
├── review-queue.md
├── contracts/
│   └── status-report.md
├── checklists/
│   └── governance.md
└── tasks.md
```

### Tooling And Workflow Surfaces

```text
.specify/
├── feature.json
├── doc-registry.json
├── scripts/bash/
│   └── setup-plan.sh
├── memory/
│   └── constitution.md
├── extensions/docs/
│   ├── README.md
│   └── commands/speckit.docs.md
└── templates/
    ├── plan-template.md
    └── spec-template.md

specs/
├── README.md
├── 000-repo-governance/
│   ├── spec.md
│   ├── plan.md
│   ├── quickstart.md
│   ├── research.md
│   └── tasks.md
└── 001-docs-governance-hardening/
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    ├── questions.md
    ├── review-queue.md
    ├── contracts/status-report.md
    └── tasks.md

tools/
├── doc_status.py
├── doc_workflow.py
└── tests/
    └── test_doc_workflow.py

AGENTS.md
README.md
```

**Structure Decision**: This remains a repo-tooling and governance-doc change. The work stays in
the existing repo-root tools and docs instead of creating a new project tree. The late slice adds
no new subsystem; it sharpens the semantics already shared across `.specify/`, `specs/`, and
`tools/`.

## Implementation Slices

### Slice A: Safe Mutation Surfaces

- `tools/doc_status.py`: keep frontmatter authoritative and expose `sync --dry-run` plus
  `--scope {all,managed,active-feature}`
- `tools/doc_workflow.py`: expose the same safe sync controls without changing the JSON status
  schema
- `.specify/scripts/bash/setup-plan.sh`: preserve an existing `plan.md` by default and require
  `--force` for overwrite
- `tools/tests/test_doc_workflow.py`: prove dry-run preview, managed-only sync, active-feature-only
  sync, preserved plan setup, and forced overwrite

### Slice B: Artifact Reconciliation

- Refresh `spec.md`, `research.md`, `data-model.md`, `quickstart.md`,
  `contracts/status-report.md`, and `tasks.md` so they describe the same frontmatter-first,
  lean-by-type, write-surface-safe workflow
- Remove stale rendered-header and preview-CSS assumptions from planning artifacts
- Keep lifecycle language explicit: implemented in tree, review-open, closure-ready, landed in repo
  history

### Slice C: Remaining Close-Out Work

- Keep feature-local comment requests and governance approvals explicit in `review-queue.md` and
  `.specify/doc-registry.json`
- Re-run the docs gate after those review items are cleared
- Only then stop pointing `.specify/feature.json` at this feature

## Validation Plan

Run these checks before treating the checklist work as complete:

```bash
python3 -m unittest discover -s tools/tests -p 'test_*.py'
python3 tools/doc_workflow.py status --json
python3 tools/doc_workflow.py sync --dry-run --scope managed
python3 tools/doc_workflow.py sync --dry-run --scope active-feature
python3 tools/doc_workflow.py all
```

## Task Reconciliation Rule

`tasks.md` should mark delivered engineering work complete and leave only the remaining human
review, approval, and feature-pointer close-out steps open. The feature remains review-open until
those final queue items are cleared.
