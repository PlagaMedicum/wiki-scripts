---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for catch-up, stall recovery, and coverage reporting.
  source: speckit-checklist on 2026-04-24
---

# Recovery Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [ ] CHK001 Are stale, stalled, disconnected, invalid-resume, and gapped stream states all covered by recovery requirements? [Completeness, Spec §FR-005, Research §Freshness Thresholds]
- [ ] CHK002 Are startup, reconnect, stale-watchdog, manual emergency, and accident-window catch-up triggers all documented? [Completeness, Plan §Phase 3]
- [ ] CHK003 Are bounded catch-up window rules defined for default duration, caller-supplied start/end, and maximum allowed scope? [Gap, Spec §SC-003, Contract §Operator Commands]
- [ ] CHK004 Are newest-first prioritization and complete accounting requirements both stated without conflict? [Consistency, Plan §Phase 3, Spec §SC-004]
- [ ] CHK005 Are unresolved exposure reporting requirements complete for page title, revision ID, age, reason, and next action? [Completeness, Spec §User Story 3, Contract §Operator Commands]

## Requirement Clarity

- [ ] CHK006 Is "stale" quantified with a clear threshold and a clear reference point for lag calculation? [Clarity, Spec §SC-002, Contract §Runtime Status]
- [ ] CHK007 Is "recovery complete" defined clearly enough to decide when realtime health may return to healthy? [Clarity, Spec §FR-006, Contract §Runtime Status]
- [ ] CHK008 Are retrying, failed, unresolved, and blocked outcomes defined distinctly enough for implementation and operator reporting? [Clarity, Data Model §SuppressionOutcome]
- [ ] CHK009 Are accident-window inputs specified clearly for required start, optional/default end, timezone handling, and invalid window handling? [Clarity, Contract §Operator Commands]
- [ ] CHK010 Is the difference between emergency catch-up and accident-window coverage clear in purpose, inputs, and expected output? [Clarity, Contract §Operator Commands]

## Requirement Consistency

- [ ] CHK011 Are recovery requirements consistent with the assumption that nightly reconciliation is a fallback safety net, not the primary protection path? [Consistency, Spec §Assumptions]
- [ ] CHK012 Are coverage-report outcomes consistent across spec, data model, and operator command contract? [Consistency, Spec §FR-009, Data Model §CoverageWindow, Contract §Operator Commands]
- [ ] CHK013 Are recovery status states consistent between the runtime-status contract and implementation phases? [Consistency, Contract §Runtime Status, Plan §Phase 1]
- [ ] CHK014 Are retry requirements consistent with duplicate-action avoidance and already-hidden handling? [Consistency, Spec §FR-010, Data Model §SuppressionAction]

## Acceptance Criteria Quality

- [ ] CHK015 Can the 30-minute catch-up within 2 minutes success criterion be objectively evaluated from the written requirements? [Measurability, Spec §SC-003]
- [ ] CHK016 Can accident-window accounting be objectively evaluated as 100% coverage from the written requirements? [Measurability, Spec §SC-004]
- [ ] CHK017 Are acceptance criteria defined for partial recovery, where some revisions are hidden and others remain unresolved? [Coverage, Spec §User Story 2, Spec §User Story 3]
- [ ] CHK018 Are acceptance criteria defined for recovery when rights/session failure blocks hiding? [Coverage, Spec §FR-005, Spec §FR-010]

## Edge Case Coverage

- [ ] CHK019 Are requirements documented for daemon downtime before start, mid-stream disconnect, and reconnect with replayed events? [Coverage, Spec §Edge Cases]
- [ ] CHK020 Are requirements documented for catch-up over pages that moved, disappeared, or left the watched set during the window? [Gap, Spec §Edge Cases]
- [ ] CHK021 Are requirements documented for retry exhaustion and operator escalation when unresolved items remain after catch-up? [Gap, Data Model §SuppressionAction]
- [ ] CHK022 Are requirements documented for avoiding sensitive content exposure in coverage reports while still giving enough identifiers for follow-up? [Coverage, Spec §FR-012, Data Model §CoverageWindow]

## Dependencies & Assumptions

- [ ] CHK023 Are external dependency assumptions for wiki availability, account rights, and API rate behavior documented at the right level? [Assumption, Spec §Assumptions]
- [ ] CHK024 Are failure classifications documented for rights/session, wiki-side terminal errors, transient network failures, and malformed responses? [Gap, Spec §FR-010]

## Notes

- Focus areas: stale realtime detection, catch-up boundaries, accident-window coverage, and unresolved exposure reporting.
- Depth: formal implementation-readiness gate.
- Actor/timing: author and reviewer before task generation and implementation.
