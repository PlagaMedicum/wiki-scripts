---
docmeta:
  status: working
  review: feature-local
  purpose: Implementation plan for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Implementation Plan: Docs Governance Hardening


## Summary

Bring `001-docs-governance-hardening` from "working in the current tree" to "policy-coherent and
closure-ready" by addressing the analysis findings directly. The next implementation slice should
align `closure_needed` with real review readiness, prove the documented no-active-feature and
registry-precedence rules with explicit tests, and document the difference between implemented,
review-open, and landed states so the repo does not overclaim completion just because tasks are
checked off.

## Delivery Priorities

1. Repair closure semantics:
   - make `closure_needed` mean closure-ready pointer cleanup, not just task completion
   - treat pending feature-local review/question items as closure blockers
   - keep durable approval/manual-review state anchored to `.specify/doc-registry.json`
2. Close proof gaps in automated coverage:
   - add a direct no-active-feature test
   - add a direct registry-versus-feature-queue precedence test
   - add a direct test that pending review work suppresses closure readiness
3. Clarify delivery-state language:
   - document that completed tasks do not imply approved or closed
   - keep feature docs explicit about `Draft`, review-open, and closure-ready states
   - document that "landed in repo history" requires tracked artifacts and normal git close-out
4. Preserve the existing conservative `.specify` model:
   - do not invent new durable approval semantics in feature-local files
   - keep git landing as a documented close-out check instead of expanding the docs status tool into
     a general VCS auditor

## Technical Context

**Language/Version**: Python 3.x for repo tooling; Markdown, JSON, and shell-script workflow docs  
**Primary Dependencies**: Python standard library, existing `tools/doc_workflow.py`,
`tools/doc_status.py`, Spec Kit shell scripts, git for documented close-out hygiene  
**Storage**: Repository Markdown and JSON files under `.specify/`, `specs/`, `README.md`, and
`tools/`  
**Testing**: `python3 -m unittest discover -s tools/tests -p 'test_*.py'`, docs gate via
`python3 tools/doc_workflow.py all`, plus targeted regression tests for closure semantics and queue
precedence  
**Target Platform**: Local maintainer shell in this repository  
**Project Type**: Repo tooling plus governance/documentation workflow hardening  
**Performance Goals**: Deterministic docs status should remain fast enough for routine local use on
the current repo size  
**Constraints**: No automatic approvals; preserve the standing-governance vs feature-doc boundary;
keep review states explicit and file-backed; keep durable approval/manual-review state anchored to
`.specify/doc-registry.json`; keep repo-local Spec Kit overrides conservative unless explicitly
approved; do not turn the docs gate into a general git policy engine  
**Scale/Scope**: One repo, one standing governance stack, one active hardening feature, and a
small follow-on remediation slice that resolves the current policy and coverage gaps

If a direct human answer is still required, write it into `questions.md` or a feature-local review
file and either resolve it during research or stop instead of inventing policy. Do not rewrite
managed-doc review labels by hand; change `.specify/doc-registry.json` when durable review state
changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Separate Tools First**: Pass. The work stays inside repo workflow tooling and governance
  docs. It does not merge `biblio` and `suppressor` or alter their ownership boundaries.
- **II. Explicit Boundaries, Minimal Coupling**: Pass. The remediation makes the boundary between
  registry-managed review state and feature-local queue state stricter, not looser.
- **III. Narrow, Risk-Based Scope**: Pass. The slice is limited to status semantics, proof tests,
  lifecycle clarity, and close-out discipline that came out of the analysis findings.
- **IV. Deterministic Documentation And Honest Status**: Pass if `closure_needed` stops implying
  more than the workflow can prove, and if review-open versus landed states are documented
  explicitly.
- **V. Spec Kit First For Non-Trivial Work**: Pass. The feature continues to use `spec.md`,
  `plan.md`, and then refreshed `tasks.md` before any further implementation.

Document impact in this remediation slice:

- `specs/001-docs-governance-hardening/plan.md`
- `specs/001-docs-governance-hardening/research.md`
- `specs/001-docs-governance-hardening/data-model.md`
- `specs/001-docs-governance-hardening/quickstart.md`
- `specs/001-docs-governance-hardening/contracts/status-report.md`
- `specs/001-docs-governance-hardening/tasks.md`
- `tools/doc_workflow.py`
- `tools/tests/test_doc_workflow.py`
- `AGENTS.md`
- optionally `review-queue.md` if human review items need to reflect the refined close-out model

Post-design re-check: still passes. The design tightens queue semantics and proof obligations
without relaxing any constitution rule or inventing automatic approval behavior.

## Project Structure

### Documentation (this feature)

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

### Source Code (repository root)

```text
.specify/
├── feature.json
├── doc-registry.json
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

**Structure Decision**: This remains a repo-tooling and governance-doc change. The implementation
work stays in the existing repo-root tools and docs instead of creating a new project tree. The
remediation adds no new top-level subsystem; it sharpens the semantics already shared across
`.specify/`, `specs/`, and `tools/`.

## Phase Focus

### Phase 0: Research

- Decide exact closure semantics for an active feature with completed tasks but open review items
- Decide how to prove no-active-feature fallback and registry-precedence behavior with explicit
  tests instead of relying on implied coverage
- Decide whether landed-state checks belong in the status tool or in documented close-out guidance

### Phase 1: Design

- Extend the data model with explicit feature closure and delivery-state entities
- Refine the status-report contract so queue precedence, closure gating, and lifecycle language are
  non-overlapping
- Refresh the quickstart so maintainers can tell the difference between passing the docs gate,
  clearing the review queue, and landing the feature in git history

### Phase 2: Ready For Task Generation

The next `tasks.md` refresh should produce a small remediation slice:

1. adjust `tools/doc_workflow.py` closure logic to respect pending feature-local queue state
2. add targeted regression tests for missing feature pointer, queue precedence, and closure gating
3. update close-out docs and lifecycle wording
4. verify the docs gate still passes after the semantics change

## Complexity Tracking

No constitution violations require justification for this remediation slice.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
