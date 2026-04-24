---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for operator visibility, sensitive-data safety, and control surfaces.
  source: speckit-checklist on 2026-04-24
---

# Operator Safety Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [x] CHK001 Are operator-visible states complete for running-and-hiding, catching-up, stale, unhealthy, blocked, stopped, and reconciliation-only activity? [Completeness, Spec §SC-005, Contract §Runtime Status]
- [x] CHK002 Are requirements defined for the exact non-sensitive fields the TUI must expose for realtime health? [Completeness, Spec §FR-007, Contract §Runtime Status]
- [x] CHK003 Are requirements defined for latest actionable error or notice content without requiring raw log inspection? [Completeness, Spec §FR-007, Spec §FR-013]
- [x] CHK004 Are requirements defined for preserving existing operator actions while adding emergency catch-up and coverage actions? [Completeness, Contract §Operator Commands]
- [x] CHK005 Are requirements defined for operator-facing reports when rights, session, rate, network, or wiki-side errors prevent hiding? [Completeness, Spec §User Story 2]

## Requirement Clarity

- [x] CHK006 Is the phrase "daemon running but real-time hiding ineffective" translated into clear unhealthy or blocked states with operator meaning? [Clarity, Spec §FR-013, Contract §Runtime Status]
- [x] CHK007 Are "operator action required" states distinguished from informational states? [Clarity, Contract §Runtime Status]
- [x] CHK008 Are requirements clear about which details may be shown in status versus which sensitive details must stay out of routine logs/status? [Clarity, Spec §FR-012, Contract §Runtime Status]
- [x] CHK009 Are command inputs and outputs specified clearly enough for emergency catch-up and coverage reports? [Clarity, Contract §Operator Commands]
- [x] CHK010 Are local-only deployment assumptions clear enough to prevent accidental public dashboard or remote-control scope expansion? [Clarity, Plan §Constitution Check, Research §Scope]

## Requirement Consistency

- [x] CHK011 Are operator status requirements consistent between spec, runtime-status contract, and plan phases? [Consistency, Spec §FR-007, Contract §Runtime Status, Plan §Phase 1]
- [x] CHK012 Are safety requirements consistent with the existing suppressor scope of public RevDel for `user|comment` only? [Consistency, Spec §FR-011, Plan §Constraints]
- [x] CHK013 Are docs-impact requirements consistent across spec and plan for README, operations, implementation, runtime boundaries, and testing strategy? [Consistency, Spec §Documentation Impact, Plan §Documentation impact]
- [x] CHK014 Are existing manual cache reload and nightly reconciliation requirements consistently described as diagnostic/fallback actions, not required live-hiding actions? [Consistency, Spec §Assumptions, Contract §Operator Commands]

## Acceptance Criteria Quality

- [x] CHK015 Can the operator-distinguishability success criterion be objectively evaluated from specified status labels and fields? [Measurability, Spec §SC-005, Contract §Runtime Status]
- [x] CHK016 Are criteria defined for what counts as an actionable notice versus a vague status message? [Gap, Spec §FR-007]
- [x] CHK017 Are criteria defined for when a rights/session/wiki failure must be treated as blocked instead of retrying or unhealthy? [Gap, Spec §FR-010, Data Model §SuppressionOutcome]
- [x] CHK018 Are criteria defined for preserving useful audit information while excluding sensitive payloads? [Measurability, Spec §FR-012]

## Scenario Coverage

- [x] CHK019 Are requirements documented for the operator console being open but not manually refreshed while background hiding continues? [Coverage, Spec §Edge Cases]
- [x] CHK020 Are requirements documented for stale PID files, missing runtime status, and old status files from pre-feature versions? [Gap, Contract §Runtime Status]
- [x] CHK021 Are requirements documented for the operator needing a short incident summary after emergency catch-up or accident-window coverage? [Coverage, Contract §Operator Commands]
- [x] CHK022 Are requirements documented for safe status display under terminal size constraints or compact TUI rendering? [Gap, Contract §Runtime Status]

## Dependencies & Assumptions

- [x] CHK023 Are assumptions around single local operator and local-machine deployment stated consistently enough for implementation boundaries? [Assumption, Plan §Technical Context]
- [x] CHK024 Are assumptions around required bot rights and fail-closed behavior captured in user-facing requirements, not only implementation notes? [Assumption, Spec §Assumptions, Plan §Constraints]

## Notes

- Focus areas: TUI/operator status, action surfaces, sensitive-data safety, and local deployment boundaries.
- Depth: formal implementation-readiness gate.
- Actor/timing: author and reviewer before task generation and implementation.
