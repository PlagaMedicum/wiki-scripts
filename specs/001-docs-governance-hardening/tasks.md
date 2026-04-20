---
docmeta:
  status: working
  review: feature-local
  purpose: Implementation backlog and close-out state for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Tasks: Docs Governance Hardening


**Organization**: This backlog now distinguishes delivered engineering work from the remaining human
review and close-out blockers. The feature is implemented in the tree but still review-open.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when the task touches different files and does not depend on incomplete work
- **[Story]**: Maps the task to one user story from `spec.md`
- Every task includes the exact file path(s) it changes or validates

## Phase 1: Delivered Core Workflow

**Purpose**: Land the core frontmatter-first docs workflow and its deterministic queue/reporting behavior

- [X] T001 Rename and document the canonical docs command in `.specify/extensions/docs/extension.yml`, `.specify/extensions/docs/commands/speckit.docs.md`, `.agents/skills/speckit-docs/SKILL.md`, and repo references under `specs/`
- [X] T002 [P] Implement the canonical frontmatter schema and registry-backed sync/lint rules in `tools/doc_status.py` and `.specify/doc-registry.json`
- [X] T003 [P] Implement queue precedence, closure-ready semantics, and compact status-section labels in `tools/doc_workflow.py` and `specs/001-docs-governance-hardening/contracts/status-report.md`
- [X] T004 [P] Update conservative workflow guardrails in `.specify/templates/spec-template.md`, `.specify/templates/plan-template.md`, `.specify/templates/tasks-template.md`, `README.md`, `AGENTS.md`, and `specs/000-repo-governance/spec.md`
- [X] T005 [P] Add baseline docs-workflow regression coverage for tracked Markdown scanning, no-active-feature fallback, registry precedence, closure suppression, and canonical frontmatter linting in `tools/tests/test_doc_workflow.py`
- [X] T006 [P] Add baseline compact-surface regression coverage in `biblio/tests/test_cli.py`, `biblio/tests/test_runner.py`, `suppressor/src/commands.rs`, and `suppressor/src/tui_status.rs`

---

## Phase 2: Delivered Safety Reconciliation

**Purpose**: Close the remaining engineering gaps around write-surface safety and artifact truthfulness

- [X] T007 Add conservative metadata-maintenance controls in `tools/doc_status.py` and `tools/doc_workflow.py`: `--dry-run` and `--scope {all, managed, active-feature}`
- [X] T008 Add no-silent-overwrite guardrail in `.specify/scripts/bash/setup-plan.sh` with explicit `--force`
- [X] T009 [P] Add regression tests for dry-run preview, managed-only sync, active-feature-only sync, preserved plan setup, and forced overwrite in `tools/tests/test_doc_workflow.py`
- [X] T010 Refresh `specs/001-docs-governance-hardening/spec.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts/status-report.md` to match the frontmatter-first, write-surface-safe workflow
- [X] T011 Refresh `.specify/extensions/docs/README.md`, `.specify/extensions/docs/commands/speckit.docs.md`, `specs/001-docs-governance-hardening/plan.md`, and `specs/001-docs-governance-hardening/tasks.md` so operator docs and planning artifacts describe the same delivered scope
- [X] T012 Update `specs/001-docs-governance-hardening/checklists/governance.md` and `checklists/alignment.md` to reflect the current frontmatter-first and write-surface-safe contract

## Phase 3: Remaining Human Review And Close-Out

**Purpose**: Clear the final review blockers and only then close the feature

- [ ] T013 Resolve the feature-local comment requests recorded in `specs/001-docs-governance-hardening/review-queue.md` for `spec.md`, `plan.md`, `tasks.md`, `contracts/status-report.md`, and `checklists/governance.md`
- [ ] T014 Record explicit client approval in `.specify/doc-registry.json` for `specs/000-repo-governance/spec.md`, `plan.md`, and `quickstart.md`
- [ ] T015 Run `python3 -m unittest discover -s tools/tests -p 'test_*.py'`, `python3 tools/doc_workflow.py all`, confirm `status --json` shows no pending feature-local items, and only then clear `.specify/feature.json`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Delivered Core Workflow (Phase 1)**: Complete
- **Delivered Safety Reconciliation (Phase 2)**: Complete
- **Remaining Human Review And Close-Out (Phase 3)**: Depends on the delivered engineering work and remains the only open phase

### User Story Dependencies

- **US1 (P1)**: Delivered
- **US2 (P2)**: Delivered
- **US3 (P3)**: Delivered
- **US4 (P4)**: Delivered

### Parallel Opportunities

- `T013` and `T014`
- `T015` can run only after `T013` and `T014` are complete

---

## Implementation Strategy

1. Keep delivered engineering work marked complete so the task file reflects reality.
2. Treat review and approval backlog as the only remaining blockers.
3. Do not clear `.specify/feature.json` while feature-local comment requests or governance
   approvals remain pending.

## Notes

- All tasks use the strict checklist format required by the workflow
- Completed engineering work does not imply approved or closed; this feature remains review-open
  until Phase 3 is complete
