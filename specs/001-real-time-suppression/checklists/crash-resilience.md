---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for crash-resilient suppressor runtime and candidate-first recovery.
  source: speckit-checklist crash-resilience on 2026-05-13
---

# Crash Resilience Checklist: Real-Time Suppression Recovery

## Requirement Completeness

- [x] CHK001 Are classified RevDel auth and permission failure requirements defined for live suppression actions, blocked protection status, and operator-visible next action? [Completeness, Spec §FR-004, Spec §FR-013, Plan §Phase 2b]
- [x] CHK002 Are requirements explicit that classified RevDel auth or permission failures must not terminate the daemon process? [Completeness, Plan §Phase 2b, Tasks §T067/T070]
- [x] CHK003 Are requirements defined for preserving fresh daemon-owned status after a blocked rights/session failure, including whether event observation continues, hide submission pauses, or shared backoff applies? [Completeness, Spec §FR-007, Spec §FR-017, Plan §Phase 2b]
- [x] CHK004 Are stream cursor and local state persistence failure requirements documented for parent directory creation, write or atomic replace failure classification, retry/reconnect behavior, and non-healthy status? [Completeness, Contract §Required Realtime Semantics, Plan §Phase 2b, Tasks §T068/T071]
- [x] CHK005 Are candidate-first recovery requirements documented for startup, stream-gap, and emergency catch-up windows before any ordinary full watched-set scan is allowed? [Completeness, Plan §Phase 1, Plan §Phase 2b, Tasks §T069/T072]
- [x] CHK006 Are requirements defined for recording candidate source, total candidate count, watched-candidate count, discovery timing, and fallback reason without storing real sensitive-edit identifiers? [Completeness, Data Model §RecoveryCandidateSet, Contract §Required Field Semantics, Tasks §T072]
- [x] CHK007 Are requirements documented for old deployed binaries whose runtime status lacks live/background lane and latency fields, including how that affects T052 readiness? [Completeness, Contract §Compatibility, Quickstart §Rsynced Server Crash Evidence, Tasks §T052]
- [x] CHK008 Are raw rsynced log and runtime-file privacy requirements specified for plans, tasks, docs, tests, examples, release evidence, and code comments? [Completeness, Constitution §IX, Spec §FR-012, Quickstart §Rsynced Server Crash Evidence]

## Requirement Clarity

- [x] CHK009 Is the distinction between `blocked`, `unhealthy`, and `degraded` protection clear for classified permission failure, stream-state persistence failure, and stale deployed binary cases? [Clarity, Contract §Required Realtime Semantics, Spec §FR-013, Quickstart §Current MVP Go/No-Go]
- [x] CHK010 Is "keep the daemon alive" specified precisely enough to rule out process exit while still allowing blocked hide submission, operator intervention, and truthful non-healthy status? [Clarity, Plan §Phase 2b, Tasks §T070]
- [x] CHK011 Is `state-persistence` defined clearly enough to know which local state failures affect realtime trust and which are secondary diagnostics? [Clarity, Data Model §ActionableIssue, Contract §Error Snapshot Contract, Tasks §T071]
- [x] CHK012 Are "candidate discovery unavailable", "candidate discovery incomplete", and "operator-requested full check" defined clearly enough to determine when full watched-set fallback is allowed? [Clarity, Data Model §RecoveryCandidateSet, Plan §Phase 1, Tasks §T072]
- [x] CHK013 Is the separation between T040 launch evidence, rebuilt-binary freshness, and T052 smoke readiness unambiguous? [Clarity, Quickstart §T040 Evidence Acceptance Contract, Tasks §T040/T052]

## Requirement Consistency

- [x] CHK014 Are spec, plan, runtime-status contract, and tasks consistent that fresh stream transport cannot imply healthy protection while the latest live hide outcome is blocked or unresolved? [Consistency, Spec §FR-007, Spec §FR-013, Contract §Required Realtime Semantics, Tasks §T073]
- [x] CHK015 Are plan and tasks consistent that the crash-resilience slice is code/runtime behavior and must not introduce config-shape churn or new required deployment config keys? [Consistency, Plan §Config Change Review, Tasks §T067-T077]
- [x] CHK016 Are candidate-first recovery requirements consistent with live/background lane requirements so background recovery discovery cannot block recentchange-triggered live work? [Consistency, Spec §FR-003, Plan §Phase 2a, Tasks §T060/T072]
- [x] CHK017 Are quickstart and tasks consistent that T042 resource sampling remains blocked until T040 logout evidence, crash resilience, rebuilt binary deployment, and T052 smoke are handled? [Consistency, Quickstart §Current MVP Go/No-Go, Tasks §Phase 6d]

## Acceptance Criteria Quality

- [x] CHK018 Can blocked-permission status freshness be objectively evaluated from written requirements without inspecting raw logs or real sensitive revision identifiers? [Measurability, Spec §SC-002, Contract §Required Realtime Semantics, Quickstart §Forbidden Evidence]
- [x] CHK019 Can stream-state persistence retry or reconnect readiness be objectively evaluated from written status fields, issue kind, and bounded backoff requirements? [Measurability, Contract §Error Snapshot Contract, Plan §Phase 2b, Tasks §T068/T071]
- [x] CHK020 Can candidate-first recovery success be objectively evaluated from written requirements for candidate source, counts, watched filtering, discovery elapsed time, and fallback reason? [Measurability, Data Model §RecoveryCandidateSet, Contract §Required Field Semantics, Tasks §T069/T072]
- [x] CHK021 Can T052 smoke readiness be objectively evaluated from written requirements for rebuilt binary identity, lane/latency fields, crash-resilience status, PID/status freshness, and controlled outcome? [Measurability, Quickstart §Rsynced Server Crash Evidence, Tasks §T052/T076]
- [x] CHK022 Are acceptance criteria defined for when an unrecoverable permission or state-persistence issue remains release-blocking rather than silently deferred? [Acceptance Criteria, Spec §SC-005, Plan §Phase 2b, Tasks §T074/T075]

## Scenario Coverage

- [x] CHK023 Are primary live RevDel permission failure requirements complete for the sequence from observed watched edit through blocked outcome and operator-visible issue? [Coverage, Spec §FR-001, Spec §FR-004, Plan §Phase 2b]
- [x] CHK024 Are recovery-path permission failure requirements defined for catch-up or verification attempts that hit the same rights/session class as live hiding? [Coverage, Spec §FR-006, Spec §FR-017, Contract §Error Snapshot Contract]
- [x] CHK025 Are stream cursor persistence requirements defined for startup, normal event processing, reconnect after decode errors, and stream-gap recovery paths? [Coverage, Spec §FR-005, Spec §FR-024, Tasks §T068/T071]
- [x] CHK026 Are candidate-first recovery requirements defined for ordinary startup, true stream gaps, manual emergency catch-up, and full-scan fallback paths? [Coverage, Plan §Phase 1, Tasks §T069/T072]
- [x] CHK027 Are target-host deployment requirements defined for the case where launch evidence is aligned but the binary is old, unhealthy, or missing lane/latency status fields? [Coverage, Contract §Compatibility, Quickstart §T040 Evidence Acceptance Contract, Tasks §T040/T052]

## Edge Case Coverage

- [x] CHK028 Are repeated auth/permission failures required to coalesce or remain bounded so the TUI and logs do not flood while blocked protection stays visible? [Edge Case, Spec §FR-017, Spec §FR-019, Plan §Resource Goals]
- [x] CHK029 Are unwritable parent directories, failed atomic rename, stale cursor file, and missing cursor-file parent scenarios addressed as state-persistence requirements? [Edge Case, Plan §Phase 2b, Tasks §T068/T071]
- [x] CHK030 Are requirements defined for what happens after rights/session repair, including whether the daemon resumes live hiding, retries queued work, or requires operator action? [Gap, Spec §FR-010, Plan §Phase 2b]
- [x] CHK031 Are requirements defined for candidate discovery windows that are too old, too large, API-limited, or unavailable without silently truncating exposure coverage? [Edge Case, Data Model §RecoveryCandidateSet, Spec §FR-006]

## Non-Functional Requirements

- [x] CHK032 Are crash-resilience requirements consistent with the one-process MVP and explicit rejection of adding a new external supervisor or service for this slice? [Non-Functional, Constitution §VIII, Research §Keep daemon alive on permission and stream-state failures]
- [x] CHK033 Are retry, reconnect, warning, and fallback requirements bounded enough to avoid busy loops, unbounded logs, unbounded queues, or excessive API load on the low-spec host? [Non-Functional, Spec §FR-019, Plan §Resource Goals]
- [x] CHK034 Are privacy requirements specific enough that crash evidence uses aggregate counts, sanitized outcome classes, and synthetic fixtures instead of real log excerpts or sensitive identifiers? [Security, Constitution §IX, Spec §FR-012, Quickstart §Rsynced Server Crash Evidence]
- [x] CHK035 Are documentation requirements defined for preserving the no-process-exit, state-persistence retry, and candidate-first lessons without adding broad unrelated docs work? [Non-Functional, Spec §FR-020, Tasks §T077]

## Dependencies & Assumptions

- [x] CHK036 Are assumptions documented about the absence of a guaranteed external process supervisor on the active `server-start` MVP path? [Assumption, Research §Keep daemon alive on permission and stream-state failures, Spec §FR-035]
- [x] CHK037 Are dependencies on MediaWiki recentchanges candidate availability, API limits, and timestamp acceptance documented where candidate-first recovery relies on them? [Dependency, Spec §FR-016, Data Model §RecoveryCandidateSet, Plan §Phase 1]
- [x] CHK038 Are target-host assumptions for rsynced binary freshness, writable state/log paths, account rights, and be.wikipedia.org connectivity documented as release evidence dependencies? [Dependency, Contract §Start server daemon in background, Quickstart §Detached Server Start Check]
- [x] CHK039 Are human/operator responsibilities clear for logout-survival evidence, rights repair, manual emergency hide, and avoiding raw-log commits? [Assumption, Quickstart §Active MVP Critical Path, Review Queue §RQ002/RQ006]

## Ambiguities & Conflicts

- [x] CHK040 Is any conflict resolved between failing closed on permission failure and keeping the daemon process alive to preserve status and recovery evidence? [Conflict, Research §Keep daemon alive on permission and stream-state failures, Plan §Phase 2b]
- [x] CHK041 Is any ambiguity resolved around whether a stream cursor write failure should continue without resume state, pause stream processing, or reconnect with degraded status? [Ambiguity, Contract §Required Realtime Semantics, Tasks §T068/T071]
- [x] CHK042 Is any ambiguity resolved around whether candidate-first recovery may replace full watched-set verification, or only ordinary startup/gap/emergency catch-up paths? [Ambiguity, Plan §Phase 1, Spec §FR-030/FR-031]

## Notes

- Focus areas: crash-resilient runtime, stream state-persistence recovery, candidate-first recovery, T040/T052/T042 release gating, and public-repo privacy for rsynced evidence.
- Depth: standard reviewer gate.
- Actor/timing: author and reviewer before implementing T067 through T077 or claiming T052 readiness.
- Scope boundary: requirements quality only; this checklist does not verify code behavior, target-host operation, or resource measurements.
- Review pass completed on 2026-05-13. The current spec, plan, contracts, quickstart, and tasks
  define the required no-process-exit permission policy, state-persistence retry/reconnect policy,
  candidate-first recovery boundaries, T040/T052/T042 gate separation, and rsynced-evidence privacy
  constraints clearly enough for implementation to proceed.
