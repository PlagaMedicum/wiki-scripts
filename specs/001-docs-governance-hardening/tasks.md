---
docmeta:
  status: working
  review: feature-local
  purpose: Implementation backlog and close-out state for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Tasks: Docs Governance Hardening


**Organization**: Tasks are grouped by user story so delivered work stays traceable and the
remaining open work is explicit. Engineering implementation is largely complete; the open backlog is
now focused on managed-governance review capture, temporary-surface cleanup, and feature close-out.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when the task touches different files and does not depend on incomplete work
- **[Story]**: Maps the task to one user story from `spec.md`
- Every task includes the exact file path(s) it changes or validates

## Phase 1: Setup (Shared Workflow Inputs)

**Purpose**: Establish the canonical command surface, workflow docs, and planning inputs used by the rest of the feature

- [X] T001 Rename and document the canonical docs command in `.specify/extensions/docs/extension.yml`, `.specify/extensions/docs/commands/speckit.docs.md`, `.agents/skills/speckit-docs/SKILL.md`, and repo references under `specs/`
- [X] T002 Update shared workflow guidance and conservative Spec Kit defaults in `README.md`, `AGENTS.md`, `.specify/templates/spec-template.md`, `.specify/templates/plan-template.md`, and `.specify/templates/tasks-template.md`
- [X] T003 [P] Establish feature-local workflow surfaces and metadata guidance in `specs/001-docs-governance-hardening/questions.md`, `specs/001-docs-governance-hardening/review-queue.md`, and `specs/001-docs-governance-hardening/contracts/status-report.md`

---

## Phase 2: Foundational (Blocking Workflow Semantics)

**Purpose**: Land the core repo-wide semantics that every user story depends on

**⚠️ CRITICAL**: No user-story work can be considered coherent without these foundations

- [X] T004 [P] Implement the canonical frontmatter schema and registry-backed sync/lint rules in `tools/doc_status.py` and `.specify/doc-registry.json`
- [X] T005 [P] Implement deterministic queue precedence, closure-ready semantics, and compact status-section labels in `tools/doc_workflow.py` and `specs/001-docs-governance-hardening/contracts/status-report.md`
- [X] T006 [P] Add baseline docs-workflow regression coverage for tracked Markdown scanning, no-active-feature fallback, registry precedence, closure suppression, and canonical frontmatter linting in `tools/tests/test_doc_workflow.py`
- [X] T007 [P] Encode the follow-on roadmap explicitly in `specs/000-repo-governance/tasks.md`, `specs/000-repo-governance/research.md`, and `specs/README.md`

**Checkpoint**: Foundation is in place; user-story work is traceable and independently testable

---

## Phase 3: User Story 1 - Reliable `speckit.docs` Status Workflow (Priority: P1) 🎯 MVP

**Goal**: Make the docs status workflow accurately reflect the real managed-doc and active-feature action surface

**Independent Test**: Run `python3 tools/doc_workflow.py status --json` and confirm that managed-doc approvals, feature-local comment requests, terminal queue states, and unresolved-marker detection all match the file-backed workflow state

### Implementation for User Story 1

- [X] T008 [US1] Extend deterministic queue reporting for `questions.md`, `review-queue.md`, and closure semantics in `tools/doc_workflow.py`
- [X] T009 [P] [US1] Add regression coverage for terminal question states, no-active-feature fallback, registry-versus-feature precedence, and unresolved-marker false positives in `tools/tests/test_doc_workflow.py`
- [X] T010 [US1] Align the status contract and operator docs with the delivered queue behavior in `specs/001-docs-governance-hardening/spec.md`, `specs/001-docs-governance-hardening/contracts/status-report.md`, `specs/001-docs-governance-hardening/quickstart.md`, and `.specify/extensions/docs/README.md`

**Checkpoint**: The docs queue is deterministic, documented, and independently reviewable

---

## Phase 4: User Story 2 - Safe Frontmatter Metadata And Guardrails (Priority: P2)

**Goal**: Keep metadata migration and feature generation conservative, inspectable, and truthful while reconciling the remaining managed-governance review drift

**Independent Test**: Run `python3 tools/doc_status.py lint`, `python3 tools/doc_workflow.py sync --dry-run --scope managed`, and `bash .specify/scripts/bash/setup-plan.sh --json`; confirm that sync is scoped/previewable, plan setup preserves existing content, and managed governance docs no longer carry Markdown-only review drift or inline TODO review comments

### Implementation for User Story 2

- [X] T011 [US2] Implement frontmatter-first metadata migration and lean-by-type schema rules in `tools/doc_status.py`, `.specify/doc-registry.json`, and tracked Markdown workflow docs
- [X] T012 [US2] Add `--dry-run` and `--scope {all, managed, active-feature}` controls in `tools/doc_status.py` and `tools/doc_workflow.py`, and add guarded overwrite behavior in `.specify/scripts/bash/setup-plan.sh`
- [X] T013 [P] [US2] Add regression coverage for scoped sync, dry-run preview, preserved plan setup, and explicit forced overwrite in `tools/tests/test_doc_workflow.py`
- [ ] T014 [US2] Move unresolved inline review comments out of `specs/000-repo-governance/spec.md` and `specs/000-repo-governance/quickstart.md` into `specs/000-repo-governance/research.md` or another authoritative temporary review surface, then remove the inline TODO markers from the maintained docs
- [ ] T015 [US2] Record the durable review and approval outcomes for `specs/000-repo-governance/spec.md`, `specs/000-repo-governance/plan.md`, and `specs/000-repo-governance/quickstart.md` in `.specify/doc-registry.json`, then sync those docs so frontmatter matches the registry again
- [ ] T016 [US2] Preserve traceability for migrated review-derived governance lessons in `specs/000-repo-governance/research.md` and any touched maintained governance docs where that materially helps later audit or git-history lookup

**Checkpoint**: Managed-governance review state is registry-backed, inline TODO review drift is gone, and write-surface guardrails remain explicit

---

## Phase 5: User Story 3 - Token-Efficient Grounded Workflow Surfaces (Priority: P3)

**Goal**: Reduce repeated technical verbosity without losing identifiers, review distinctions, or recoverability

**Independent Test**: Inspect representative status outputs, workflow docs, and compact technical surfaces; confirm the shorthand is documented, stable, and lossless to expand

### Implementation for User Story 3

- [X] T017 [US3] Implement compact docs-workflow status labels and document their meaning in `tools/doc_workflow.py`, `specs/001-docs-governance-hardening/contracts/status-report.md`, and `specs/001-docs-governance-hardening/quickstart.md`
- [X] T018 [P] [US3] Compact repeated technical output while preserving identifiers in `biblio/biblio/ui.py`, `biblio/tests/test_cli.py`, `biblio/tests/test_runner.py`, `suppressor/src/commands.rs`, and `suppressor/src/tui_status.rs`
- [X] T019 [US3] Preserve lossless mapping from compact workflow surfaces to full meaning in `.specify/extensions/docs/README.md`, `specs/001-docs-governance-hardening/contracts/status-report.md`, and `specs/001-docs-governance-hardening/quickstart.md`

**Checkpoint**: Compact technical surfaces are grounded and auditable

---

## Phase 6: User Story 4 - Prioritized Follow-On Feature Roadmap (Priority: P4)

**Goal**: Encode the next major governance backlog chunks as named, ordered follow-on features

**Independent Test**: Read the governance roadmap docs and confirm that the next planned features are explicit, ordered, and `suppressor` comes next without relying on inline TODOs

### Implementation for User Story 4

- [X] T020 [US4] Encode the named follow-on roadmap and `suppressor`-first ordering in `specs/000-repo-governance/tasks.md`, `specs/000-repo-governance/research.md`, and `specs/README.md`
- [X] T021 [US4] Keep the feature-facing roadmap narrative aligned with the governance roadmap in `specs/001-docs-governance-hardening/spec.md`, `specs/001-docs-governance-hardening/plan.md`, and `specs/001-docs-governance-hardening/quickstart.md`

**Checkpoint**: The next feature sequence is explicit and reviewable

---

## Phase 7: Polish & Cross-Cutting Close-Out

**Purpose**: Fold current review input into the feature artifacts, rerun the gate, and only then close the feature

- [ ] T022 [P] Fold current client review comments into `specs/001-docs-governance-hardening/spec.md`, `specs/001-docs-governance-hardening/plan.md`, `specs/001-docs-governance-hardening/tasks.md`, `specs/001-docs-governance-hardening/contracts/status-report.md`, and `specs/001-docs-governance-hardening/checklists/governance.md`, then mark `RQ004` through `RQ008` resolved in `specs/001-docs-governance-hardening/review-queue.md`
- [ ] T023 Run `python3 -m unittest discover -s tools/tests -p 'test_*.py'`, `python3 tools/doc_status.py lint`, `python3 tools/doc_workflow.py status --json`, and `python3 tools/doc_workflow.py all`; confirm no pending feature-local items remain, then clear `.specify/feature.json`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Complete
- **Foundational (Phase 2)**: Complete
- **US1 (Phase 3)**: Complete
- **US2 (Phase 4)**: Partially complete; `T014`-`T016` are the main remaining engineering/documentation tasks
- **US3 (Phase 5)**: Complete
- **US4 (Phase 6)**: Complete
- **Polish & Close-Out (Phase 7)**: Depends on the remaining US2 reconciliation and the current review backlog

### User Story Dependencies

- **US1 (P1)**: Delivered
- **US2 (P2)**: Depends on foundational workflow semantics; open close-out tasks remain
- **US3 (P3)**: Delivered
- **US4 (P4)**: Delivered

### Parallel Opportunities

- `T014` and `T022` can proceed in parallel because they touch different artifact families
- `T015` depends on the final intended review state for the touched managed governance docs
- `T016` should finish before `T023` so the final validation sees the traceability and temporary-surface cleanup in place
- `T023` can run only after `T014`, `T015`, `T016`, and `T022` are complete

---

## Parallel Example: Remaining Open Work

```bash
# Governance-doc cleanup and feature-doc review folding can proceed separately:
Task: "Move unresolved inline review comments out of specs/000-repo-governance/spec.md and specs/000-repo-governance/quickstart.md into specs/000-repo-governance/research.md"
Task: "Fold current client review comments into specs/001-docs-governance-hardening/spec.md, plan.md, tasks.md, contracts/status-report.md, and checklists/governance.md"
```

---

## Implementation Strategy

### MVP First (Already Delivered)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate the deterministic docs queue

### Remaining Incremental Delivery

1. Finish the remaining US2 reconciliation work in `T014`-`T016`
2. Fold the outstanding feature-local comments in `T022`
3. Run the final validation and pointer cleanup in `T023`

### Close-Out Strategy

1. Treat managed governance review capture and inline TODO cleanup as part of the feature, not as out-of-band edits
2. Keep delivered engineering work marked complete so the backlog reflects reality
3. Do not clear `.specify/feature.json` while feature-local comment requests or managed-governance review drift remain pending

---

## Notes

- All tasks use the strict checklist format required by the workflow
- Completed engineering work does not imply approved or closed; this feature remains review-open until Phase 7 is complete
- The remaining open work is concentrated in `specs/000-repo-governance/`, `.specify/doc-registry.json`, and the feature-local review queue
