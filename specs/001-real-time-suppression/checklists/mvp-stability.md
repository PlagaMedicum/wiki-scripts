---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for the suppressor MVP stabilization freeze.
  source: speckit-checklist on 2026-05-05
---

# MVP Stability Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [x] CHK001 Are the live-hiding requirements complete enough to cover event observation, watched-page matching, eligibility, queueing, hide or dry-run outcome, and final persisted outcome? [Completeness, Spec §FR-001..FR-004, Tasks §US1]
- [x] CHK002 Are requirements defined for keeping live hiding independent from reconciliation, coverage, reporting, and manual reload work? [Completeness, Spec §FR-003, Plan §Phase -1]
- [x] CHK003 Are automatic recovery requirements complete for daemon downtime, stream gaps, restart, source-list changes, and recovery from `last_successful_hide_at`? [Completeness, Spec §FR-005..FR-006, Spec §FR-015]
- [x] CHK004 Are daytime rolling last-24h verification and nightly full watched-set fallback both specified as daemon obligations with distinct scopes? [Completeness, Spec §FR-030..FR-031, Research §Verification Scopes]
- [x] CHK005 Are shared throttle/backoff requirements documented for live hiding, catch-up, source refresh, scheduled verification, reconciliation, and one-shot command paths? [Gap, Spec §FR-017, Tasks §Phase 2]
- [x] CHK006 Are launch-path and stale-runtime requirements complete enough to prevent false healthy readings from stale PID or stale `runtime_status.json` artifacts? [Completeness, Spec §FR-026..FR-029, Research §Runtime Truth]
- [x] CHK007 Are server-build requirements complete for the aarch64 Linux musl artifact, Makefile target, artifact path, and rsync-ready release evidence? [Completeness, Spec §FR-034, Spec §SC-020, Plan §Technical Context]

## Requirement Clarity

- [x] CHK008 Is "immediate" live hiding quantified with measurable latency targets and evidence requirements rather than left as a vague urgency statement? [Clarity, Spec §SC-001]
- [x] CHK009 Are "healthy", "degraded", "blocked", "stale", and "recovering" status meanings defined clearly enough to avoid conflicting operator interpretations? [Clarity, Spec §FR-007, Spec §FR-013, Contract §Runtime Status]
- [x] CHK010 Is the recovery anchor rule clear about when `last_successful_hide_at`, a trusted fallback, or an operator-specified window applies? [Clarity, Spec §FR-006, Data Model §RecoveryAnchor]
- [x] CHK011 Is the phrase "bounded" clarified with concrete queue, concurrency, warning-summary, state-size, or log-volume limits where those limits affect daemon trust? [Ambiguity, Spec §FR-019, Plan §Resource Goals]
- [x] CHK012 Is the "actual launch path" requirement clear about which surfaces are authoritative for TUI-managed, systemd-managed, or other supervisor deployments? [Clarity, Spec §FR-026, Quickstart §Actual Launch-Path Check]
- [x] CHK013 Is "rsync-ready" defined with enough artifact path, target triple, build command, and credential-exclusion detail for release evidence? [Clarity, Spec §FR-034, Quickstart §Server Build Check]

## Requirement Consistency

- [x] CHK014 Are MVP scope boundaries consistent between the constitution freeze, plan critical path, quickstart critical path, and tasks MVP scope? [Consistency, Constitution §VIII, Plan §Summary, Quickstart §Active MVP Critical Path, Tasks §Suggested MVP Scope]
- [x] CHK015 Are performance goals consistent with the resource-economy requirement, without allowing low resource use to weaken live-hide latency or recovery targets? [Consistency, Spec §SC-001..SC-003a, Spec §FR-019, Plan §Resource Goals]
- [x] CHK016 Are one-shot command requirements consistent with daemon-owned runtime status requirements, especially where both surfaces show recovery or coverage evidence? [Consistency, Spec §FR-021, Spec §FR-025, Contract §Operator Commands]
- [x] CHK017 Are daytime verification, nightly full recheck, emergency catch-up, and accident-window coverage names used consistently across spec, plan, contracts, tasks, and quickstart? [Consistency, Spec §FR-009, Spec §FR-030..FR-031, Contract §Operator Commands]
- [x] CHK018 Are build and deployment requirements consistent with the non-destructive compatibility rule that existing `build` and `release` targets remain unchanged? [Consistency, Spec §FR-034, Plan §Compatibility/Migration]

## Acceptance Criteria Quality

- [x] CHK019 Can live-hide latency success criteria be objectively measured with publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings? [Measurability, Spec §SC-001, Spec §SC-010]
- [x] CHK020 Are stale or ineffective monitoring criteria measurable for both silent streams and fresh streams with failed, throttled, blocked, or unresolved live outcomes? [Measurability, Spec §SC-002]
- [x] CHK021 Are restart and recovery success criteria reconciled so SC-003 and SC-003a do not define duplicate or conflicting recovery windows? [Conflict, Spec §SC-003, Spec §SC-003a]
- [x] CHK022 Are MVP go/no-go requirements specified with objective evidence for tests, server build, launch path, live hiding, recovery, reconciliation, nightly fallback, backoff, and rollback? [Completeness, Tasks §T034..T042, Quickstart §Active MVP Critical Path]
- [x] CHK023 Are resource-economy success criteria measurable on the deployment host for idle daemon plus TUI, queue depth, state size, API concurrency, and warning summaries? [Measurability, Spec §SC-011, Plan §Resource Goals]
- [x] CHK024 Are server-build acceptance criteria measurable without embedding rsync destination, credentials, tokens, cookies, or `.env` values in release evidence? [Acceptance Criteria, Spec §SC-020, Data Model §DeploymentArtifact]

## Scenario Coverage

- [x] CHK025 Are primary live-protection, alternate dry-run, exception failure, recovery catch-up, and non-functional resource scenarios all covered by explicit requirements? [Coverage, Spec §User Stories, Spec §Edge Cases]
- [x] CHK026 Are rights, session, permission, MediaWiki rate-limit, non-JSON response, and timestamp rejection scenarios represented as requirements rather than only test ideas? [Coverage, Spec §FR-010, Spec §FR-016..FR-017]
- [x] CHK027 Are source-list and request-page change scenarios specified for added pages, changed request pages, deferred catch-up, and retry points? [Coverage, Spec §FR-015, Data Model §SourceRefreshEvent]
- [x] CHK028 Are command-surface scenarios covered for emergency catch-up, `Last 24 hours`, arbitrary coverage windows, command reports, and daemon-vs-command separation? [Coverage, Spec §FR-008..FR-009, Spec §FR-021, Contract §Operator Commands]
- [x] CHK029 Are deployment scenarios covered for local development, aarch64 musl server build, actual server launch, rollback, and compatibility approval? [Coverage, Spec §FR-026..FR-034, Quickstart §Server Build Check]

## Edge Case Coverage

- [x] CHK030 Are stale PID, stale runtime-status, unreadable older state, and incompatible operator artifact cases specified as non-healthy or migration-needed outcomes? [Edge Case, Spec §FR-027..FR-029]
- [x] CHK031 Are reconnect noise and ordinary stream reopen cases specified separately from true startup recovery and true gap recovery? [Edge Case, Spec §FR-023..FR-024]
- [x] CHK032 Are overlapping recovery, source-refresh catch-up, rolling verification, nightly full recheck, and manual command cases specified with priority or deferral rules? [Edge Case, Spec §Edge Cases, Plan §Phase -1]
- [x] CHK033 Are missing local build prerequisites such as `cargo-zigbuild`, Zig, or target toolchain requirements captured as release-readiness requirements? [Gap, Spec §FR-034, Tasks §T003, Tasks §T035]

## Dependencies & Assumptions

- [x] CHK034 Are assumptions about be.wikipedia.org availability, EventStreams behavior, MediaWiki API behavior, and suppressor account rights documented with non-healthy fallback requirements? [Assumption, Spec §Assumptions, Spec §FR-010, Spec §FR-017]
- [x] CHK035 Are dependencies on local JSON state, PID files, TUI supervisor behavior, and optional systemd deployment documented without assuming one launch path is always authoritative? [Dependency, Plan §Technical Context, Quickstart §Actual Launch-Path Check]
- [x] CHK036 Are secrets, credentials, hidden text, sensitive article content, cookies, and `.env` handling requirements complete across logs, reports, runtime status, build evidence, and deployment evidence? [Security, Spec §FR-012, Plan §Constraints, Data Model §DeploymentArtifact]

## Notes

- These checklist items validate requirement quality, not implementation behavior.
- Focus areas: suppressor MVP stability, live hiding, recovery/reconciliation/nightly fallback,
  status truth, resource bounds, command separation, and aarch64 musl server-build readiness.
- Depth: standard requirements-review gate for the active human-safety freeze.
- Actor/timing: author and reviewer before implementation proceeds beyond MVP stabilization.
