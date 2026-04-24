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
and the follow-on roadmap. This plan now also absorbs the review-derived governance corrections:
managed review must stay registry-backed, unresolved review comments must leave maintained standing
docs, temporary review surfaces must stay scope-specific, and durable lessons should keep
traceability when that materially helps later audit. The remaining engineering and documentation
work is therefore:

- make broad metadata rewrites inspectable and scopeable
- make plan generation preserve filled artifacts unless `--force` is used
- align `spec.md`, `research.md`, `data-model.md`, `quickstart.md`,
  `contracts/status-report.md`, and `tasks.md` with the implemented design and the review-derived
  governance rules
- keep durable review state in `.specify/doc-registry.json`, move unresolved standing-governance
  review comments out of maintained docs, and delete stale inline reminders once their substance is
  already durable elsewhere
- keep implemented, review-open, and closure-ready as separate lifecycle states

## Current State

- **Landed in repo history**: `/speckit.docs` rename, frontmatter-first metadata migration,
  compact docs-status labels, compact `biblio` and `suppressor` technical output, and the explicit
  follow-on roadmap.
- **Implemented in this working pass**: scoped and dry-run metadata sync in `tools/doc_status.py`
  and `tools/doc_workflow.py`, no-silent-overwrite guardrail in
  `.specify/scripts/bash/setup-plan.sh`, and regression tests for both.
- **Review-derived drift still being reconciled**: managed governance docs under
  `specs/000-repo-governance/` plus `.specify/memory/constitution.md` currently contain manual
  review-label edits or inline TODO review comments. Those edits capture real feedback, but not yet
  in the constitution-compliant surfaces (`.specify/doc-registry.json`,
  `specs/000-repo-governance/research.md`, or a scoped feature queue).
- **TODO inventory reviewed**: the remaining live inline TODO markers are in
  `.specify/memory/constitution.md`, `specs/000-repo-governance/spec.md`, and
  `specs/000-repo-governance/quickstart.md`. The many other `TODO` mentions under
  `001-docs-governance-hardening/` are mostly requirements text, status-contract examples, or
  checklist coverage that document the policy rather than represent open backlog items.
- **Still open**: client comment on the feature docs, explicit approval for three
  `specs/000-repo-governance/*` docs, constitution/standing-doc TODO cleanup, and eventual
  `.specify/feature.json` cleanup after those review queues are cleared.

## TODO Review Findings

- Live unresolved inline TODOs currently exist only in `.specify/memory/constitution.md`,
  `specs/000-repo-governance/spec.md`, and `specs/000-repo-governance/quickstart.md`.
- Those TODOs fall into four classes:
  - temporary-surface discipline and cleanup of resolved items from `research.md`,
    `questions.md`, and `review-queue.md`
  - stale reminders whose substance is already reflected in the constitution or current feature
    research and should therefore be deleted rather than migrated verbatim
  - suppressor-specific future-policy follow-up, such as bot-edit marking, which belongs in a named
    follow-on feature instead of an inline standing-doc comment
  - traceability guidance that should remain durable policy but not survive as unresolved TODO text
- `TODO` strings in `specs/001-docs-governance-hardening/` should stay out of the remaining-work
  inventory unless they appear as actual unresolved prose in maintained docs. Requirement wording,
  examples inside `contracts/status-report.md`, and checklist references are intentional
  documentation, not cleanup tasks.

## Delivery Priorities

1. Finish write-surface safety:
   - `doc_status.py sync` and `doc_workflow.py sync` must expose `--dry-run` and
     `--scope {all,managed,active-feature}`
   - `.specify/scripts/bash/setup-plan.sh` must preserve an existing non-empty `plan.md` unless
     `--force` is passed
2. Reconcile managed-governance review capture and the maintained-doc TODO inventory:
   - managed review or approval changes must be recorded in `.specify/doc-registry.json`, not by
     hand-editing `docmeta.review`
   - unresolved review comments on maintained standing docs, including
     `.specify/memory/constitution.md`, must move into `specs/000-repo-governance/research.md`, a
     feature-local review file, or a follow-on feature instead of remaining inline
   - TODO comments whose substance is already durable elsewhere should be deleted rather than copied
     into another temporary surface
   - suppressor-specific follow-up such as bot-edit marking should live in the named roadmap, not
     as inline standing-governance commentary
3. Reconcile the feature artifacts:
   - all design docs must describe the same frontmatter-first, lean-by-type metadata model
   - all planning docs must describe the same write-surface safety rules, review-capture rules,
     temporary-surface split, and close-out model
4. Preserve lifecycle clarity:
   - completed implementation must remain distinct from review-open and closure-ready
   - `closure_needed` must stay suppressed while feature-local review items remain pending
5. Preserve the conservative `.specify` model:
   - durable approval/manual-review state stays anchored to `.specify/doc-registry.json`
   - docs-maintenance and feature generation remain separate documented write surfaces
   - repo-level unresolved questions live in `specs/000-repo-governance/research.md`, while
     feature-scoped human input stays in feature-local `questions.md` or `review-queue.md`
   - resolved items should be folded into durable docs and cleaned out of temporary surfaces instead
     of leaving `research.md` and feature queues as a second archive

## Technical Context

- **Language/Version**: Python 3.x for repo tooling; Markdown, JSON, and shell-script workflow
  docs
- **Primary Dependencies**: Python standard library, existing `tools/doc_workflow.py`,
  `tools/doc_status.py`, `.specify/scripts/bash/setup-plan.sh`, Spec Kit shell scripts, git for
  documented close-out hygiene
- **Storage**: Repository Markdown and JSON files under `.specify/`, `specs/`, `README.md`, and
  `tools/`
- **Testing**: `python3 -m unittest discover -s tools/tests -p 'test_*.py'`, docs gate via
  `python3 tools/doc_workflow.py all`, plus targeted regression tests for sync scoping, dry-run
  preview, no-silent-overwrite plan setup, and status/report parsing of registry-backed review
  capture
- **Target Platform**: Local maintainer shell in this repository
- **Project Type**: Repo tooling plus governance/documentation workflow hardening
- **Performance Goals**: Deterministic docs status should remain fast enough for routine local use
  on the current repo size
- **Constraints**: No automatic approvals; preserve the standing-governance vs feature-doc
  boundary; keep review states explicit and file-backed; keep durable approval/manual-review state
  anchored to `.specify/doc-registry.json`; keep repo-local Spec Kit overrides conservative unless
  explicitly approved; do not turn the docs gate into a general git policy engine; do not silently
  overwrite a filled feature artifact; do not treat Markdown-only review-label edits in managed
  docs as durable review evidence; do not leave unresolved inline TODO review comments inside
  maintained standing governance docs; do not treat contract examples or requirement prose that
  name TODO markers as live backlog items; do not copy stale inline reminders into temporary
  surfaces when current durable docs already resolve them
- **Scale/Scope**: One repo, one standing governance stack, one active hardening feature, and one
  late-stage reconciliation slice that makes the existing implementation, review capture, and docs
  stack agree

If a direct human answer is still required, write it into `questions.md` or a feature-local review
file and either resolve it during research or stop instead of inventing policy. Do not rewrite
managed-doc review labels by hand; change `.specify/doc-registry.json` when durable review state
changes. If standing-governance review produces unresolved follow-up points, move them into
`specs/000-repo-governance/research.md` or a scoped review surface instead of leaving them inline in
accepted docs.

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
  broad rewrites are inspectable before mutation, managed review state remains registry-backed,
  unresolved standing-doc review comments leave accepted docs, and review-open versus closure-ready
  states are documented explicitly.
- **V. Spec Kit First For Non-Trivial Work**: Pass. The feature continues to use `spec.md`,
  `plan.md`, and then refreshed `tasks.md` before any further implementation.

Document impact in this remediation slice:

- `.specify/scripts/bash/setup-plan.sh`
- `.specify/doc-registry.json`
- `.specify/memory/constitution.md`
- `.specify/extensions/docs/README.md`
- `.specify/extensions/docs/commands/speckit.docs.md`
- `specs/000-repo-governance/spec.md`
- `specs/000-repo-governance/plan.md`
- `specs/000-repo-governance/quickstart.md`
- `specs/000-repo-governance/research.md`
- `specs/000-repo-governance/tasks.md`
- `specs/001-docs-governance-hardening/plan.md`
- `specs/001-docs-governance-hardening/research.md`
- `specs/001-docs-governance-hardening/data-model.md`
- `specs/001-docs-governance-hardening/quickstart.md`
- `specs/001-docs-governance-hardening/questions.md`
- `specs/001-docs-governance-hardening/review-queue.md`
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
│   ├── alignment.md
│   ├── governance.md
│   └── requirements.md
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

### Slice B: Review-Derived Governance Capture

- `.specify/doc-registry.json`: record durable review and approval changes for managed standing docs
- `specs/000-repo-governance/research.md`: hold only still-unresolved repo-level review comments
  until they are folded into accepted policy or spun into a new feature, and remove resolved items
  instead of letting the file become an archive
- `.specify/memory/constitution.md` plus `specs/000-repo-governance/spec.md`, `plan.md`, and
  `quickstart.md`: remove Markdown-only review drift and inline TODO review comments once each
  point has either been absorbed into durable policy, moved into `research.md`, or rehomed in a
  named follow-on feature
- `specs/000-repo-governance/tasks.md`: carry named follow-on backlog items, including the
  suppressor-specific TODO themes that should not remain embedded in maintained prose
- `specs/001-docs-governance-hardening/questions.md` and `review-queue.md`: keep feature-scoped
  human input separate from repo-level unresolved governance work
- durable lessons lifted from a feature review should keep an inspectable trace back to the
  originating feature or decision source when that helps later audit

### Slice C: Artifact Reconciliation

- Refresh `spec.md`, `research.md`, `data-model.md`, `quickstart.md`,
  `contracts/status-report.md`, and `tasks.md` so they describe the same frontmatter-first,
  lean-by-type, write-surface-safe workflow
- Remove stale rendered-header and preview-CSS assumptions from planning artifacts
- Keep lifecycle language explicit: implemented in tree, review-open, closure-ready, landed in repo
  history
- Make the temporary review-surface split and registry-backed review-capture rules explicit across
  the whole planning stack

### Slice D: Remaining Close-Out Work

- Keep feature-local comment requests and governance approvals explicit in `review-queue.md` and
  `.specify/doc-registry.json`
- Re-run the docs gate after those review items are cleared and standing governance docs no longer
  carry Markdown-only review drift or inline TODO review comments
- Only then stop pointing `.specify/feature.json` at this feature

## Validation Plan

Run these checks before treating the checklist work as complete:

```bash
python3 -m unittest discover -s tools/tests -p 'test_*.py'
python3 tools/doc_status.py lint
python3 tools/doc_workflow.py status --json
python3 tools/doc_workflow.py sync --dry-run --scope managed
python3 tools/doc_workflow.py sync --dry-run --scope active-feature
bash .specify/scripts/bash/setup-plan.sh --json
python3 tools/doc_workflow.py all
```

## Task Reconciliation Rule

`tasks.md` should mark delivered engineering work complete and leave only the remaining human
review, approval, and feature-pointer close-out steps open. The feature remains review-open until
those final queue items are cleared. Review input on maintained governance docs must first be
captured through `.specify/doc-registry.json` or the appropriate temporary review surface before it
counts toward close-out. The next `tasks.md` refresh should widen the remaining maintained-doc
cleanup to include `.specify/memory/constitution.md` and should distinguish live unresolved TODOs
from contract examples or already-resolved reminders.
