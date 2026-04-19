---
docmeta:
  status: working
  review: feature-local
  purpose: Implementation task backlog and execution state for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Tasks: Docs Governance Hardening


**Organization**: Tasks are grouped by user story so each slice can be implemented and tested independently. Because the current `plan.md` only covers the older closure-semantics slice, the first setup tasks refresh the design layer to the broader `spec.md` scope before additional implementation work continues.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when the task touches different files and does not depend on incomplete work
- **[Story]**: Maps the task to one user story from `spec.md`
- Every task includes the exact file path(s) it changes or validates

## Phase 1: Setup (Design Refresh)

**Purpose**: Bring the design artifacts up to the current `spec.md` scope before further implementation or close-out work

- [ ] T001 Refresh `specs/001-docs-governance-hardening/plan.md` to cover `speckit.docs`, unified frontmatter metadata, token-economy scope, and follow-on feature order
- [ ] T002 [P] Refresh `specs/001-docs-governance-hardening/research.md` and `specs/001-docs-governance-hardening/data-model.md` to encode the canonical header schema, compact legend rules, and delivery-state distinctions
- [ ] T003 [P] Refresh `specs/001-docs-governance-hardening/quickstart.md`, `specs/001-docs-governance-hardening/contracts/status-report.md`, and `specs/001-docs-governance-hardening/review-queue.md` to match the current workflow contract

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock the shared command, frontmatter, guardrail, and regression contracts that all user stories depend on

**⚠️ CRITICAL**: No user story is complete until these shared contracts are stable

- [ ] T004 Rename and document the canonical docs command in `.specify/extensions/docs/extension.yml`, `.specify/extensions/docs/commands/speckit.docs.md`, `.agents/skills/speckit-docs/SKILL.md`, and repo references under `specs/`
- [ ] T005 [P] Define the canonical frontmatter schema and registry-backed sync/lint rules in `tools/doc_status.py` and `.specify/doc-registry.json`
- [ ] T006 [P] Define queue precedence, closure-ready semantics, and compact status-section labels in `tools/doc_workflow.py` and `specs/001-docs-governance-hardening/contracts/status-report.md`
- [ ] T007 [P] Update conservative workflow guardrails in `.specify/templates/spec-template.md`, `.specify/templates/plan-template.md`, `.specify/templates/tasks-template.md`, `README.md`, `AGENTS.md`, and `specs/000-repo-governance/spec.md`
- [ ] T008 [P] Add baseline docs-workflow regression coverage for tracked Markdown scanning, no-active-feature fallback, registry precedence, closure suppression, and canonical frontmatter linting in `tools/tests/test_doc_workflow.py`
- [ ] T009 [P] Add baseline compact-surface regression coverage in `biblio/tests/test_cli.py`, `biblio/tests/test_runner.py`, `suppressor/src/commands.rs`, and `suppressor/src/tui_status.rs`

**Checkpoint**: The shared command, header, review-state, and regression contracts are explicit and stable

---

## Phase 3: User Story 1 - Reliable `speckit.docs` Status Workflow (Priority: P1) 🎯 MVP

**Goal**: Make `speckit.docs` and `python3 tools/doc_workflow.py status` expose the real queue state for managed docs and the active feature

**Independent Test**: Run `rtk python3 tools/doc_workflow.py status` and inspect `questions.md` / `review-queue.md`; the output must surface the right pending items, suppress terminal items, and avoid false `closure_needed`

### Tests for User Story 1

- [ ] T010 [P] [US1] Add human-readable status-output assertions for `APP`, `REV`, `ANS`, `COM`, `UPD`, `CLS`, and `ERR` in `tools/tests/test_doc_workflow.py`

### Implementation for User Story 1

- [ ] T011 [US1] Implement compact text status output and closure suppression while review work remains in `tools/doc_workflow.py`
- [ ] T012 [US1] Implement additive managed-review semantics, tracked-Markdown scanning, and non-managed frontmatter lint behavior in `tools/doc_status.py`
- [ ] T013 [US1] Align the durable managed-doc review labels and managed roots in `.specify/doc-registry.json`
- [ ] T014 [US1] Update the operator-facing `speckit.docs` workflow documentation in `.specify/extensions/docs/README.md`, `.specify/extensions/docs/commands/speckit.docs.md`, and `specs/001-docs-governance-hardening/contracts/status-report.md`

**Checkpoint**: `speckit.docs` becomes a trustworthy current-action surface for the active feature

---

## Phase 4: User Story 2 - Unified Technical Headers And Guardrails (Priority: P2)

**Goal**: Put every repo-tracked Markdown doc on one canonical technical metadata schema and keep policy-bearing workflow surfaces conservative and explicit

**Independent Test**: Open representative docs from `README.md`, `.specify/`, `.agents/`, `specs/`, `biblio/`, and `suppressor/`; each should expose the same frontmatter contract with truthful provenance and readable optional fields

### Tests for User Story 2

- [ ] T015 [P] [US2] Add schema and migration regressions for managed and non-managed frontmatter metadata in `tools/tests/test_doc_workflow.py`

### Implementation for User Story 2

- [ ] T016 [P] [US2] Apply the canonical frontmatter metadata to `.specify/templates/checklist-template.md`, `.specify/templates/constitution-template.md`, `.specify/templates/plan-template.md`, `.specify/templates/spec-template.md`, `.specify/templates/tasks-template.md`, and `AGENTS.md`
- [ ] T017 [P] [US2] Apply the canonical frontmatter metadata to `.specify/extensions/docs/README.md`, `.specify/extensions/git/README.md`, `.specify/extensions/docs/commands/speckit.docs.md`, `.specify/extensions/git/commands/*.md`, and `.agents/skills/*/SKILL.md`
- [ ] T018 [US2] Sync registry-managed frontmatter metadata across `README.md`, `specs/README.md`, `specs/000-repo-governance/*.md`, `biblio/README.md`, `biblio/docs/*.md`, `suppressor/README.md`, and `suppressor/docs/*.md` through `tools/doc_status.py`
- [ ] T019 [US2] Remove the old preview-CSS dependency and document frontmatter-only rendering expectations in `.specify/extensions/docs/README.md`, `.vscode/settings.json`, and `specs/001-docs-governance-hardening/quickstart.md`
- [ ] T020 [US2] Update conservative override guidance and file-based-question rules in `.specify/templates/spec-template.md`, `.specify/templates/plan-template.md`, `README.md`, `specs/000-repo-governance/quickstart.md`, and `specs/000-repo-governance/spec.md`

**Checkpoint**: The repo has one honest, frontmatter-first metadata system and explicit guardrails for policy-bearing docs

---

## Phase 5: User Story 3 - Token-Efficient Grounded Workflow Surfaces (Priority: P3)

**Goal**: Make repeated technical surfaces materially shorter without hiding identifiers, review distinctions, or recovery paths

**Independent Test**: Inspect representative docs-status output, frontmatter metadata, `biblio` queue/bulk lines, and `suppressor` CLI/status summaries; each compact form should stay deterministic and fully recoverable through the documented legend or expanded view

### Tests for User Story 3

- [ ] T021 [P] [US3] Add compact-output regressions for `biblio` queue and bulk-status lines in `biblio/tests/test_cli.py` and `biblio/tests/test_runner.py`
- [ ] T022 [P] [US3] Add compact-output regressions for `suppressor` auth and status-summary lines in `suppressor/src/commands.rs` and `suppressor/src/tui_status.rs`

### Implementation for User Story 3

- [ ] T023 [US3] Implement compact queue and bulk-status helper output in `biblio/biblio/ui.py`
- [ ] T024 [US3] Implement compact auth/result and status-error helper output in `suppressor/src/commands.rs` and `suppressor/src/tui_status.rs`
- [ ] T025 [US3] Add repo-local shorthand wrappers and documented recovery paths in `Makefile`, `.specify/extensions/docs/README.md`, `README.md`, and `specs/001-docs-governance-hardening/quickstart.md`

**Checkpoint**: Compact workflow surfaces reduce repetition without sacrificing diagnostics or traceability

---

## Phase 6: User Story 4 - Prioritized Follow-On Feature Roadmap (Priority: P4)

**Goal**: Encode the next scoped features directly in governance docs so the next non-trivial work starts from an explicit roadmap instead of TODO comments

**Independent Test**: Read `specs/000-repo-governance/` and the `001` feature docs; the `suppressor` features must be named and prioritized ahead of the `biblio` follow-ons

### Implementation for User Story 4

- [ ] T026 [P] [US4] Encode the next planned features in `specs/000-repo-governance/tasks.md` and `specs/000-repo-governance/research.md`
- [ ] T027 [US4] Align the roadmap rationale in `specs/001-docs-governance-hardening/spec.md`, `specs/001-docs-governance-hardening/research.md`, `specs/001-docs-governance-hardening/quickstart.md`, and `specs/README.md`
- [ ] T028 [US4] Refresh `specs/001-docs-governance-hardening/review-queue.md` and `specs/001-docs-governance-hardening/questions.md` so the remaining human actions and follow-on feature intent stay file-backed

**Checkpoint**: The next feature order is explicit, durable, and independent of inline TODO comments

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the full feature, reconcile close-out docs, and prepare the feature for human review and landing

- [ ] T029 [P] Reconcile `specs/001-docs-governance-hardening/tasks.md` and `specs/001-docs-governance-hardening/plan.md` with the final implementation and review-open state
- [ ] T030 Run `rtk python3 -m unittest discover -s tools/tests -p 'test_*.py'`, `rtk python3 -m pytest biblio/tests/test_cli.py biblio/tests/test_runner.py biblio/tests/test_page_save.py biblio/tests/test_page_analysis.py`, and `rtk cargo test`
- [ ] T031 Run `rtk python3 tools/doc_workflow.py all` and `rtk bash .specify/scripts/bash/run-doc-workflow.sh`
- [ ] T032 Update `.specify/feature.json`, `specs/001-docs-governance-hardening/review-queue.md`, and the durable review labels in `.specify/doc-registry.json` after approvals and comments are cleared

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; start immediately to repair the stale design layer
- **Foundational (Phase 2)**: Depends on Setup; blocks all user-story work because it defines the shared command, frontmatter, guardrail, and test contracts
- **User Story 1 (Phase 3)**: Depends on Foundational; delivers the MVP docs-status workflow
- **User Story 2 (Phase 4)**: Depends on Foundational; may proceed alongside US1 once the shared frontmatter contract is fixed
- **User Story 3 (Phase 5)**: Depends on Foundational and should follow the canonical command/header work from US1 and US2
- **User Story 4 (Phase 6)**: Depends on Foundational; can proceed after the roadmap and workflow terminology are stabilized
- **Polish (Phase 7)**: Depends on all desired user stories

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories after Foundational; this is the MVP slice
- **US2 (P2)**: No dependency on US1 for semantics, but it should land against the final shared header contract from Foundational
- **US3 (P3)**: Depends on the canonical command/header language from US1 and US2 so compact notation stays consistent
- **US4 (P4)**: Depends only on the stabilized governance and workflow language from Setup and Foundational

### Parallel Opportunities

- `T002` and `T003`
- `T005`, `T006`, `T007`, `T008`, and `T009`
- `T016` and `T017`
- `T021` and `T022`
- `T026` and `T028`
- `T029` can proceed while verification commands in `T030` and `T031` run

---

## Parallel Example: User Story 1

```bash
Task: "Add human-readable status-output assertions for APP, REV, ANS, COM, UPD, CLS, and ERR in tools/tests/test_doc_workflow.py"
Task: "Update the operator-facing speckit.docs workflow documentation in .specify/extensions/docs/README.md, .specify/extensions/docs/commands/speckit.docs.md, and specs/001-docs-governance-hardening/contracts/status-report.md"
```

## Parallel Example: User Story 2

```bash
Task: "Apply the canonical frontmatter metadata to .specify/templates/*.md and AGENTS.md"
Task: "Apply the canonical frontmatter metadata to .specify/extensions/**/*.md and .agents/skills/*/SKILL.md"
```

## Parallel Example: User Story 3

```bash
Task: "Add compact-output regressions for biblio queue and bulk-status lines in biblio/tests/test_cli.py and biblio/tests/test_runner.py"
Task: "Add compact-output regressions for suppressor auth and status-summary lines in suppressor/src/commands.rs and suppressor/src/tui_status.rs"
```

## Parallel Example: User Story 4

```bash
Task: "Encode the next planned features in specs/000-repo-governance/tasks.md and specs/000-repo-governance/research.md"
Task: "Refresh specs/001-docs-governance-hardening/review-queue.md and specs/001-docs-governance-hardening/questions.md so the remaining human actions and follow-on feature intent stay file-backed"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Stop and validate `speckit.docs` with `rtk python3 tools/doc_workflow.py status` and `rtk python3 tools/doc_workflow.py all`

### Incremental Delivery

1. Refresh the design layer and shared contracts
2. Land US1 so the docs-status workflow becomes trustworthy
3. Land US2 so every repo-tracked Markdown doc shares the same technical header contract
4. Land US3 so repeated technical surfaces become compact but recoverable
5. Land US4 so the next scoped features are encoded explicitly
6. Finish Polish to prepare review and landing

### Suggested MVP Scope

The smallest valuable increment is **US1 only** after Setup and Foundational. That yields a trustworthy `speckit.docs` queue without waiting for the full header and token-economy migration.

## Notes

- All tasks use the strict checklist format required by the workflow
- Tests are included because the spec and plan explicitly require proof coverage for queue semantics, header rules, and compact technical surfaces
- `specs/001-docs-governance-hardening/plan.md` currently reflects the older closure-remediation slice; the Setup phase intentionally fixes that first
