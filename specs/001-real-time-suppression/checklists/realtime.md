---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for the real-time hiding path.
  source: speckit-checklist on 2026-04-24
---

# Realtime Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [ ] CHK001 Are continuous monitoring requirements defined for daemon startup, normal running, reconnect, and post-cache-refresh states? [Completeness, Spec §FR-001]
- [ ] CHK002 Are requirements for immediate hiding complete across single edits, edit bursts, and watched-list changes? [Completeness, Spec §FR-002, Spec §Edge Cases]
- [ ] CHK003 Are live-path independence requirements defined so slower reconciliation cannot be treated as satisfying real-time hiding? [Completeness, Spec §FR-003, Plan §Phase 2]
- [ ] CHK004 Are watched-title matching requirements complete for normalized titles, redirects, source-list changes, and exact scope boundaries? [Coverage, Spec §FR-011, Data Model §WatchedSensitivePage]
- [ ] CHK005 Are duplicate/replayed-event requirements specified for already processed, already hidden, and concurrently queued revisions? [Coverage, Spec §FR-010, Spec §Edge Cases]

## Requirement Clarity

- [ ] CHK006 Is "immediately" quantified consistently with the 1-second and 5-second success criteria? [Clarity, Spec §SC-001]
- [ ] CHK007 Is "eligible edit" defined clearly enough to distinguish hide-required, already-hidden, skipped, and not-watched revisions? [Clarity, Spec §FR-004, Data Model §ObservedEdit]
- [ ] CHK008 Is the live event handling boundary clear between target-wiki filtering, revision-event filtering, watched-title matching, and suppression action queueing? [Clarity, Plan §Phase 2]
- [ ] CHK009 Are requirements clear about whether manual refresh/cache reload may help diagnostics but cannot be required for live hiding? [Clarity, Spec §Assumptions]
- [ ] CHK010 Is the relationship between Last-Event-ID resume state and operator-visible realtime state specified without ambiguity? [Clarity, Contract §Runtime Status]

## Requirement Consistency

- [ ] CHK011 Are the spec, plan, and runtime-status contract consistent that EventStreams is primary and bounded catch-up is recovery rather than the normal live path? [Consistency, Spec §FR-003, Research §EventStreams, Plan §Summary]
- [ ] CHK012 Are live hiding latency goals consistent between the feature success criteria and technical context? [Consistency, Spec §SC-001, Plan §Technical Context]
- [ ] CHK013 Are "daemon running", "realtime healthy", and "reconciliation idle/active" defined as separate statuses across all artifacts? [Consistency, Spec §FR-013, Contract §Runtime Status]
- [ ] CHK014 Are live-path requirements consistent with the scope rule that suppressor hides only public user/comment metadata for watched sensitive pages? [Consistency, Spec §FR-011, Plan §Constraints]

## Acceptance Criteria Quality

- [ ] CHK015 Can the live-hiding acceptance criteria be objectively evaluated without relying on manual cache reload or nightly workflow behavior? [Measurability, Spec §User Story 1]
- [ ] CHK016 Are success thresholds defined for both normal operation and degraded/recovery operation? [Acceptance Criteria, Spec §SC-001, Spec §SC-003]
- [ ] CHK017 Are measurable expectations defined for high-volume bursts or is burst behavior a requirements gap? [Gap, Spec §Edge Cases]
- [ ] CHK018 Are acceptance criteria traceable from live event observation through action queueing to final outcome recording? [Traceability, Spec §FR-002, Spec §FR-004]

## Edge Case Coverage

- [ ] CHK019 Are requirements documented for stream replay, duplicate events, and revisions hidden by another operator before daemon action? [Coverage, Spec §Edge Cases]
- [ ] CHK020 Are requirements documented for page moves, deletions, protections, or redirect changes between edit detection and hiding? [Coverage, Spec §Edge Cases]
- [ ] CHK021 Are requirements documented for source-list page changes that alter watched-title scope while the daemon is running? [Coverage, Spec §Edge Cases]
- [ ] CHK022 Are requirements documented for edits lacking expected metadata such as title, revision ID, actor, timestamp, or comment flags? [Gap, Data Model §ObservedEdit]

## Notes

- Focus areas: live EventStreams requirements, watched-title matching, latency clarity, and duplicate/replay boundaries.
- Depth: formal implementation-readiness gate.
- Actor/timing: author and reviewer before task generation and implementation.
