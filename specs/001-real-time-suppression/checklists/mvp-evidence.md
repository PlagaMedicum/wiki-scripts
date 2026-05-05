---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for MVP evidence, task-state truth, and production-readiness wording.
  source: speckit-checklist on 2026-05-06
---

# MVP Evidence Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [ ] CHK001 Are MVP completion requirements complete enough to distinguish implemented code, checked tasks, local build evidence, deployment-host launch evidence, live-hide evidence, recovery evidence, and resource evidence? [Completeness, Plan §Phase -1, Tasks §Implementation Strategy]
- [ ] CHK002 Are foundational requirements documented for the whole blocker set: shared throttle/backoff, stale PID/status truth, scheduler isolation, `server-start` tests, and non-healthy status derivation? [Completeness, Tasks §Phase 2]
- [ ] CHK003 Are requirements complete for rerunning the serial suppressor test gate and server build after Phase 2, US1, and US2 change the daemon-critical paths? [Gap, Tasks §T037-T038]
- [ ] CHK004 Are requirements defined for benchmark or controlled-event evidence covering p95/p99 live latency, burst handling, and benchmark safety before release trust is claimed? [Gap, Spec §SC-001, Spec §SC-006, Spec §SC-010]
- [ ] CHK005 Are deployment-host evidence requirements complete for `server-start`, terminal logout survival, daemon-owned status freshness, detached log path, and rollback or fallback decision points? [Completeness, Spec §SC-021, Tasks §T039]

## Requirement Clarity

- [ ] CHK006 Is the term "production-ready" or "stable daemon" defined with exact required evidence rather than task checkmarks alone? [Clarity, Quickstart §Production Readiness Gate]
- [ ] CHK007 Is the provisional status of currently checked tasks stated clearly enough that local test/build evidence cannot be mistaken for server-proven safety? [Clarity, Plan §Phase -1, Quickstart §Local Evidence]
- [ ] CHK008 Are `server-start` completion requirements clear about which behavior belongs to code implementation versus which behavior belongs to real deployment verification? [Clarity, Spec §FR-035, Tasks §T007/T010/T039]
- [ ] CHK009 Are requirements explicit about when `T037` and `T038` evidence expires and must be refreshed after subsequent daemon-critical edits? [Ambiguity, Tasks §T037-T038]
- [ ] CHK010 Are resource-measurement requirements defined with enough fields, timing, and acceptable bounds to avoid a vague "measure it later" release gate? [Clarity, Spec §SC-011, Tasks §T041]

## Requirement Consistency

- [ ] CHK011 Are task completion rules consistent with the dependency statement that Phase 2 blocks US1, US2, and production trust? [Consistency, Tasks §Phase Dependencies]
- [ ] CHK012 Are `server-start` requirements consistent across spec, plan, operator-command contract, runtime-status contract, quickstart, and tasks? [Consistency, Spec §FR-035, Plan §Phase -1, Contracts §Operator Commands]
- [ ] CHK013 Are launch-path truth requirements consistent with compatibility requirements for TUI-managed, systemd-managed, and detached-binary runs? [Consistency, Spec §FR-026..FR-029, Plan §Phase 0]
- [ ] CHK014 Are recovery-window requirements consistent between the older 30-minute wording and the sharper `last_successful_hide_at` recovery-anchor wording? [Consistency, Spec §SC-003, Spec §SC-003a]
- [ ] CHK015 Are command-report requirements consistent with the rule that one-shot commands must not overwrite or impersonate daemon-owned realtime truth? [Consistency, Spec §FR-021, Tasks §US3]

## Acceptance Criteria Quality

- [ ] CHK016 Can live-hide latency requirements be objectively measured from specified timestamps: publish, detect, queue, hide, and publish-to-hidden? [Measurability, Spec §SC-001, Spec §SC-010]
- [ ] CHK017 Can non-healthy status timing be objectively measured for stale stream, failed live hide, throttle/backoff, failed scheduled verification, stale full recheck, and invalid launch-path evidence? [Measurability, Spec §SC-002, Spec §SC-016]
- [ ] CHK018 Can recovery success be objectively measured from the selected recovery anchor through hidden or unresolved outcomes within the required time window? [Measurability, Spec §FR-006, Spec §SC-003a]
- [ ] CHK019 Can `server-start` success and failure requirements be objectively evaluated without reading secrets, raw sensitive content, or terminal-dependent state? [Measurability, Spec §FR-012, Spec §SC-021]
- [ ] CHK020 Are go/no-go criteria documented for accepting, blocking, or rolling back when deployment-host live smoke, recovery, reconciliation, nightly, or resource checks fail? [Gap, Tasks §T045]

## Scenario Coverage

- [ ] CHK021 Are primary, exception, and recovery scenarios specified for missing config, missing auth, stale PID, duplicate live daemon, unwritable state/log paths, runtime-status timeout, and child process exit during `server-start`? [Coverage, Contracts §Operator Commands]
- [ ] CHK022 Are requirements specified for source-list and request-page changes that happen while shared backoff or scheduled verification is active? [Coverage, Spec §FR-015, Tasks §T017/T026]
- [ ] CHK023 Are requirements specified for stream reopen noise versus true gaps so ordinary reconnects cannot erase degraded evidence? [Coverage, Spec §FR-024, Tasks §T021/T027]
- [ ] CHK024 Are requirements specified for scheduled verification overlap so rolling last-24h and nightly full recheck cannot starve live hiding? [Coverage, Spec §FR-003, Spec §FR-030..FR-031, Tasks §T008]
- [ ] CHK025 Are requirements specified for old or incompatible runtime-status, command-report, PID, and launch-path artifacts so they produce non-healthy or migration-needed wording? [Coverage, Spec §FR-027..FR-029]

## Dependencies & Assumptions

- [ ] CHK026 Are assumptions about the target server environment documented: filesystem permissions, process model, available shell, no systemd requirement, no tmux/screen/nohup dependency, and writable detached log path? [Assumption, Plan §Technical Context, Contracts §Operator Commands]
- [ ] CHK027 Are assumptions about MediaWiki availability, suppressor rights, and safe controlled-event pages documented for live or dry-run smoke evidence? [Assumption, Spec §SC-006, Spec §SC-010]
- [ ] CHK028 Are requirements clear about which evidence may be collected locally and which evidence must be collected only on the deployment host? [Dependency, Quickstart §Local Evidence, Tasks §T039-T041]

## Notes

- Focus areas: MVP evidence quality, task-state truth, `server-start` release gating, live/recovery proof, and resource evidence.
- Depth: standard reviewer checklist.
- Actor/timing: reviewer and implementer before continuing MVP implementation or claiming production readiness.
