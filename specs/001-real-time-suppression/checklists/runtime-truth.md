---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for authoritative daemon status, state convergence, and truthful operator surfaces.
  source: speckit-checklist on 2026-04-28
---

# Runtime Truth Checklist: Real-Time Suppression Recovery

## Requirement Completeness

- [x] CHK001 Are requirements defined that the daemon-owned runtime status surface is authoritative and that one-shot commands may read it but must not overwrite it? [Completeness, Contract §Surface, Plan §Phase 2]
- [x] CHK002 Are requirements defined to distinguish stream freshness from live hide effectiveness so a fresh stream cannot by itself imply healthy protection? [Completeness, Spec §FR-007, Spec §FR-013, Contract §TUI Requirements]
- [x] CHK003 Are requirements defined for exposing the source of the latest actionable failure or outcome as `live`, `catchup`, `reconciliation`, or `source-refresh`? [Completeness, Plan §Phase 3, Contract §TUI Requirements]
- [x] CHK004 Are requirements defined for when `catching-up` must end and which non-healthy or healthy state must replace it? [Completeness, Plan §Phase 2, Contract §TUI Requirements]
- [x] CHK005 Are requirements defined for separating daemon logs from one-shot command logs, or for labeling them clearly enough that operators cannot confuse them? [Completeness, Contract §TUI Action Placement, Plan §Phase 3]

## Requirement Clarity

- [x] CHK006 Is "daemon-owned realtime truth" defined clearly enough to identify the owning process, the owned file or surface, and the write restrictions on auxiliary commands? [Clarity, Contract §Surface, Plan §Phase 0]
- [x] CHK007 Is `healthy` defined clearly enough when `current_lag_seconds=0` but the latest live suppression outcome is failed, throttled, blocked, or unresolved? [Clarity, Contract §TUI Requirements, Data Model §RealtimeHealth]
- [x] CHK008 Are "true startup", "ordinary reopen", "reconnect noise", and "gap recovery" defined clearly enough to prevent false `startup` recovery labeling? [Clarity, Plan §Phase 1, Contract §Recovery Summary Contract]
- [x] CHK009 Is the required behavior of the live-output pane in `latest` mode clear enough to decide between wrapped-row-aware following and explicit non-wrapping? [Clarity, Contract §TUI Requirements, Contract §TUI Action Placement]
- [x] CHK010 Is "degraded protection" defined clearly enough to distinguish transport freshness from inability to hide newly observed eligible edits? [Clarity, Spec §FR-013, Plan §Phase 2]

## Requirement Consistency

- [x] CHK011 Are the spec, plan, and runtime-status contract consistent that realtime health reflects both observation freshness and live hiding effectiveness? [Consistency, Spec §FR-007, Spec §FR-013, Plan §Phase 2, Contract §TUI Requirements]
- [x] CHK012 Are the operator-command and runtime-status contracts consistent that emergency catch-up and coverage output remain separate from daemon realtime truth? [Consistency, Contract §Operator Commands, Contract §Surface]
- [x] CHK013 Are launch-path verification requirements consistent across plan, quickstart, and compatibility rules so the project does not assume a systemd unit exists when the deployment uses another supervisor path? [Consistency, Plan §Phase 0, Contract §Compatibility, Quickstart §Production Readiness Gate]
- [x] CHK014 Are recovery-trigger requirements consistent that `requested_by=startup` or `last_recovery_trigger=startup` mean true bootstrap or explicit bootstrap recovery rather than any ordinary EventStreams reopen? [Consistency, Contract §Recovery Summary Contract, Plan §Phase 1]
- [x] CHK015 Are requirements for compact-terminal prioritization consistent that active realtime failure or throttle-backoff state outranks older reconciliation noise? [Consistency, Plan §Phase 3, Contract §TUI Requirements]

## Acceptance Criteria Quality

- [x] CHK016 Can the stale or ineffective monitoring criterion be objectively evaluated when the stream is fresh but the latest live outcome remains failed or throttled? [Measurability, Spec §SC-002, Spec §SC-005, Contract §TUI Requirements]
- [x] CHK017 Can the operator-distinguishability criterion be objectively evaluated from written status labels, fields, and precedence rules without relying on raw logs? [Measurability, Spec §SC-005, Contract §TUI Requirements]
- [x] CHK018 Are measurable criteria defined for when the daemon must leave `catching-up` after recovery or backoff has ended? [Gap, Plan §Phase 2, Contract §TUI Requirements]
- [x] CHK019 Can live-output truthfulness be objectively evaluated from the written requirements for newest-row visibility and source labeling? [Measurability, Contract §TUI Requirements, Contract §TUI Action Placement]

## Scenario Coverage

- [x] CHK020 Are requirements defined for live-path rate limiting separately from catch-up or reconciliation throttling so the operator can tell which protection path is degraded? [Coverage, Spec §FR-017, Plan §Phase 1, Contract §Error Snapshot Contract]
- [x] CHK021 Are requirements defined for one-shot commands executing while the daemon is healthy, catching up, stale, or blocked, including what may appear in status versus command output? [Coverage, Contract §Operator Commands, Contract §Surface]
- [x] CHK022 Are requirements defined for reconnect decode errors or other reopen noise that should not trigger or relabel startup recovery? [Coverage, Plan §Residual Findings, Plan §Phase 1]
- [x] CHK023 Are requirements defined for source-refresh success, deferral, and failure states when shared backoff prevents immediate bounded catch-up? [Coverage, Spec §FR-015, Contract §Source Refresh Contract]

## Edge Case Coverage

- [x] CHK024 Are requirements documented for missing runtime status, stale PID files, older state-file versions, and unreadable compatibility surfaces so operator status degrades safely instead of reading healthy? [Coverage, Contract §Compatibility]
- [x] CHK025 Are requirements documented for long wrapped log lines and compact terminals so the newest daemon evidence does not fall out of view in `latest` mode? [Coverage, Contract §TUI Requirements, Contract §TUI Action Placement]
- [x] CHK026 Are requirements documented for mixed evidence where fresh target-wiki events continue to arrive while the latest live hide outcome is still failed or unresolved? [Coverage, Spec §FR-013, Plan §Phase 2]

## Non-Functional Requirements

- [x] CHK027 Are low-spec resource-economy requirements specific enough that status separation, command reporting, and log labeling do not introduce unbounded state, log, or memory growth? [Non-Functional, Spec §FR-019, Plan §Technical Context]
- [x] CHK028 Are responsiveness requirements specified for how quickly stale, throttled, blocked, or degraded-protection states must become visible after the triggering evidence appears? [Clarity, Spec §SC-002, Contract §TUI Requirements]

## Dependencies & Assumptions

- [x] CHK029 Is the assumption about the actual daemon launch path documented clearly enough to identify the authoritative diagnostic surface in each deployment mode? [Assumption, Plan §Phase 0, Contract §Compatibility]
- [x] CHK030 Are dependencies on EventStreams freshness, MediaWiki throttle hints such as `Retry-After`, and local supervisor output documented where runtime-truth requirements rely on them? [Dependency, Spec §FR-017, Research §Treat rate limiting as a first-class recovery contract, Contract §Error Snapshot Contract]
- [x] CHK031 Does the requirements set acknowledge the architectural limit that an external post-publication daemon cannot guarantee zero first-view prevention, so operator truth requirements do not imply impossible protection? [Consistency, Plan §Technical Context, Plan §Documentation impact]

## Notes

- Focus areas: authoritative daemon status, state convergence, live-versus-recovery failure truth, and TUI log/status honesty.
- Depth: standard reviewer gate.
- Actor/timing: reviewer and author before more implementation on runtime status, recovery, and TUI surfaces.
- Review pass completed on 2026-04-28 after the spec was updated with runtime-truth requirements and revalidated against the current plan, contracts, quickstart, and research artifacts.
