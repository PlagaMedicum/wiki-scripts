---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for live-priority latency and concurrency.
  source: speckit-checklist on 2026-05-09
---

# Live-Priority Requirements Checklist: Real-Time Suppression Recovery

**Purpose**: Validate that the live-priority latency and concurrency requirements are complete,
clear, measurable, and internally consistent before implementing T053 through T066.
**Created**: 2026-05-09
**Audience/Timing**: PR reviewer before live-priority implementation.
**Focus Areas**: Live/background lane requirements, timing evidence, no fixed internal handoff SLA,
transaction boundaries, degraded status, resource evidence, and config-stability boundaries.

## Requirement Completeness

- [ ] CHK001 Are live-lane ownership requirements defined for every recentchange-triggered suppression action? [Completeness, Spec §FR-003, Plan §Phase 2a]
- [ ] CHK002 Are background-lane ownership requirements defined for reconciliation, catch-up, rolling verification, nightly full recheck, manual coverage, and one-shot command work? [Completeness, Contract §Parallel Execution Contract]
- [ ] CHK003 Are requirements defined for the exact timing samples that must be recorded: observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden? [Completeness, Spec §SC-001, Plan §Performance Goals]
- [ ] CHK004 Are lane status requirements complete for queue depth, queue capacity, in-flight count, concurrency limit, latest saturation time, and saturation reason? [Completeness, Contract §Runtime Status]
- [ ] CHK005 Are transaction-boundary requirements complete for queued, submitted, completed, and processed-revision persistence transitions? [Completeness, Plan §Phase 2a]
- [ ] CHK006 Are requirements defined for live timeout, rate-limit, full-queue, and deferred-retry outcomes without blocking newer live edits? [Completeness, Plan §Phase 2a, Tasks §T056/T062]

## Requirement Clarity

- [ ] CHK007 Is the phrase "as fast as practical" constrained by measurable evidence requirements rather than left as an implementation preference? [Clarity, Spec §FR-003, Spec §SC-001]
- [ ] CHK008 Is the absence of a fixed internal live-worker handoff SLA stated consistently enough that implementers will not invent a hard millisecond target? [Clarity, Spec §Clarifications, Tasks §Phase 6b]
- [ ] CHK009 Is "background drain" clearly distinguished from ordinary background slowdown so the blocked-background requirement is testable? [Clarity, Plan §Phase 2a, Contract §Parallel Execution Contract]
- [ ] CHK010 Are "accepted", "submitted", "visibly degraded", and "blocked" defined or traceable to status/outcome requirements? [Clarity, Spec §FR-003, Contract §Parallel Execution Contract]
- [ ] CHK011 Are "short live action deadlines" and "immediate live attempt capacity" described with enough requirement-level intent to guide implementation without changing config shape? [Clarity, Plan §Phase 2a, Tasks §T062]

## Requirement Consistency

- [ ] CHK012 Do the no-fixed-internal-SLA clarification, SC-001 external hide targets, and task wording align without conflicting timing thresholds? [Consistency, Spec §Clarifications, Spec §SC-001, Tasks §T055/T064]
- [ ] CHK013 Are live/background lane requirements consistent between the spec, plan, runtime-status contract, quickstart, and tasks? [Consistency, Spec §FR-003, Plan §Phase 2a, Contract §Parallel Execution Contract, Tasks §Phase 6b]
- [ ] CHK014 Are background concurrency requirements consistent with the reviewed default API cap of 2 and the prohibition on unreviewed config changes? [Consistency, Plan §Resource Goals, Tasks §T060]
- [ ] CHK015 Are degraded-status requirements for live queue saturation consistent with broader unhealthy/degraded protection requirements? [Consistency, Spec §FR-013, Contract §Parallel Execution Contract]
- [ ] CHK016 Are resource-economy requirements consistent with the decision to keep one daemon process and avoid a new queueing service or database? [Consistency, Plan §Technical Context, Research §Parallel Lanes]

## Acceptance Criteria Quality

- [ ] CHK017 Can the release evidence required by SC-001 objectively prove both external hide latency and non-blocking live reaction during background work? [Measurability, Spec §SC-001]
- [ ] CHK018 Are p50/p95/p99 latency reporting requirements specific enough to avoid ambiguity about which paths are summarized? [Acceptance Criteria, Contract §Runtime Status]
- [ ] CHK019 Are target-host smoke evidence requirements distinct from deterministic local timing evidence so external EventStreams delay is not confused with queue isolation? [Acceptance Criteria, Quickstart §Minimum Timing Evidence]
- [ ] CHK020 Are T064 evidence requirements written as requirement-quality evidence rather than an implicit new performance SLA? [Measurability, Tasks §T064]

## Scenario Coverage

- [ ] CHK021 Are primary live scenarios covered while background reconciliation is idle, active, delayed, and blocked? [Coverage, Plan §Phase 2a]
- [ ] CHK022 Are burst requirements for at least 10 synthetic eligible watched edits tied to final outcomes, duplicate protection, and percentile reporting? [Coverage, Spec §SC-006, Tasks §T057]
- [ ] CHK023 Are source-triggered catch-up and request-page follow-up requirements covered as background work that must not starve live recent edits? [Coverage, Spec §FR-015, Tasks §T060]
- [ ] CHK024 Are one-shot diagnostic, coverage, benchmark, and report scenarios covered as background or separate work that must not overwrite daemon-owned live truth? [Coverage, Spec §FR-021, Contract §Parallel Execution Contract]

## Edge Case Coverage

- [ ] CHK025 Are edge cases documented for live queue full, live deadline exceeded, API rate-limit, network timeout, and retry deferral? [Edge Case, Plan §Phase 2a, Tasks §T056/T062]
- [ ] CHK026 Are requirements defined for duplicate or already-processed revisions crossing live/background lanes without conflicting outcomes? [Edge Case, Spec §FR-004, Tasks §T057/T061]
- [ ] CHK027 Are requirements defined for persistence failure or partial status/processed-state write failure during a suppression transaction? [Gap, Plan §Phase 2a]
- [ ] CHK028 Are privacy requirements explicit for any timing, status, or incident evidence generated by live-priority tests and release notes? [Edge Case, Spec §FR-012]

## Non-Functional Requirements

- [ ] CHK029 Are bounded queue and bounded concurrency requirements specified for both lanes without requiring a new operator-reviewed config shape? [Non-Functional, Plan §Resource Goals, Tasks §T058/T060]
- [ ] CHK030 Are low-spec resource evidence requirements complete for live/background queue depths, in-flight counts, API concurrency, status/report size, log growth, and latency summaries? [Non-Functional, Spec §SC-011, Tasks §T042]
- [ ] CHK031 Are observability requirements complete enough for an operator to distinguish live-lane pressure from background-lane pressure? [Non-Functional, Contract §Runtime Status]
- [ ] CHK032 Are reliability requirements clear that background retries, page scans, and reconciliation sleeps must not hold runtime-status, queue, or processed-revision locks? [Non-Functional, Plan §Phase 2a, Tasks §Guardrails]

## Dependencies & Assumptions

- [ ] CHK033 Are assumptions about staying in one daemon process and one local binary documented with alternatives rejected? [Assumption, Research §Parallel Lanes]
- [ ] CHK034 Are dependencies on existing Tokio, local JSON state, and the default API cap documented without requiring unplanned services or schema churn? [Dependency, Plan §Technical Context]
- [ ] CHK035 Are dependencies between T053-T066, T052 target-host smoke, and T042 resource sampling documented clearly enough to prevent stale evidence from being reused? [Dependency, Tasks §Dependencies]
- [ ] CHK036 Are config-stability approval boundaries documented for any future lane capacity or timeout configuration change? [Dependency, Tasks §Phase 6b, Plan §Phase 2a]

## Ambiguities & Conflicts

- [ ] CHK037 Is there any remaining contradiction between "short live action deadlines" and "no fixed internal live-worker handoff SLA"? [Ambiguity, Plan §Phase 2a]
- [ ] CHK038 Is "visibly degraded" tied to specific runtime status fields and operator wording rather than left as a vague state? [Ambiguity, Contract §Parallel Execution Contract]
- [ ] CHK039 Are compatibility expectations for older runtime-status files clear when lane and latency fields are absent? [Ambiguity, Contract §Field Semantics]
- [ ] CHK040 Are all live-priority requirements traceable from spec or plan into tasks T053 through T066 without orphaned requirements or orphaned tasks? [Traceability, Spec §FR-003, Plan §Phase 2a, Tasks §Phase 6b]

## Notes

- These items validate requirement quality, not implementation behavior.
- Check items off as completed: `[x]`.
- Add comments or findings inline when a requirement needs clarification or rewrite.
