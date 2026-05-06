---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for the detached server-start launch path.
  source: speckit-checklist on 2026-05-05
---

# Server-Start Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [x] CHK001 Are detached server-start requirements complete enough to cover config resolution, runtime directory preparation, auth preflight, duplicate-daemon refusal, detached spawn, log redirection, startup wait, and final launch receipt? [Completeness, Spec §FR-035, Contract §Start server daemon in background]
- [x] CHK002 Are safe failure requirements defined for missing config, missing auth secrets, stale PID files, duplicate live daemons, unwritable state or log paths, spawn failure, startup timeout, and unhealthy runtime status? [Completeness, Spec §Edge Cases, Contract §Failure behavior]
- [x] CHK003 Are requirements defined for preserving existing `run`, `dry-run`, TUI-managed start, systemd assets, and one-shot command behavior while adding `server-start`? [Completeness, Plan §Compatibility/Migration, Contract §Compatibility]
- [x] CHK004 Are requirements defined for the detached child to survive terminal logout without requiring systemd, tmux, screen, shell backgrounding, or nohup? [Completeness, Spec §SC-021, Research §server-start]
- [x] CHK005 Are requirements defined for keeping secrets provisioning operator-controlled and preventing the launcher from creating, printing, persisting, or rsyncing credentials? [Security, Spec §Assumptions, Plan §Constraints]

## Requirement Clarity

- [x] CHK006 Is the exact operator command name, config argument, dry-run option, status-timeout option, and log-file option documented clearly enough for implementation? [Clarity, Contract §Start server daemon in background]
- [x] CHK007 Is "detached" clarified with concrete requirements for closed stdin, redirected stdout/stderr, new session behavior, and independence from the invoking SSH terminal? [Clarity, Contract §Required behavior]
- [x] CHK008 Is the successful launch receipt specified with concrete fields for mode, PID, config path, PID file, runtime status path, log path, and `server-start` launch label? [Clarity, Quickstart §Detached Server Start Check]
- [x] CHK009 Are authoritative launch-path labels clear enough to distinguish `server-start`, TUI-managed, systemd-managed, and other supervisor paths? [Clarity, Contract §Runtime Status, Quickstart §Actual Launch-Path Check]

## Requirement Consistency

- [x] CHK010 Are detached launch requirements consistent between spec, plan, operator-command contract, runtime-status contract, quickstart, data model, and tasks? [Consistency, Spec §FR-035, Plan §Phase -1, Tasks §T007/T010/T040]
- [x] CHK011 Are `server-start` requirements consistent with the daemon-owned runtime truth rule so the launcher does not overwrite or impersonate daemon status? [Consistency, Spec §FR-021, Contract §Runtime Status]
- [x] CHK012 Are detached launch failure requirements consistent with stale PID and stale runtime-status requirements instead of creating a second false-healthy status path? [Consistency, Spec §FR-029, Contract §Failure behavior]
- [x] CHK013 Are build and launch requirements consistently scoped so `make build-server` produces the rsync artifact while `server-start` starts the deployed artifact on the server? [Consistency, Spec §FR-034..FR-035, Quickstart §Server Build Check]

## Acceptance Criteria Quality

- [x] CHK014 Can server-start success be objectively measured by PID liveness, runtime-status freshness, launch-path label, log-path output, and terminal logout survival within the specified startup window? [Measurability, Spec §SC-021]
- [x] CHK015 Are startup timeout and status freshness criteria quantified enough to avoid vague "started successfully" interpretations? [Measurability, Spec §SC-021, Contract §Required behavior]
- [x] CHK016 Are release-readiness requirements tied to evidence from tests, server build, detached launch, live or dry-run smoke check, and resource/log bounds rather than task completion alone? [Acceptance Criteria, Tasks §T037..T046, Quickstart §Production Readiness Gate]

## Scenario Coverage

- [x] CHK017 Are primary live launch, alternate dry-run launch, duplicate-daemon refusal, stale artifact recovery, missing prerequisite failure, and unhealthy status outcomes all covered by explicit requirements? [Coverage, Spec §Edge Cases, Contract §Failure behavior]
- [x] CHK018 Are rsync deployment assumptions covered without embedding server destinations, credentials, tokens, cookies, or `.env` values in release evidence? [Coverage, Spec §Assumptions, Data Model §DeploymentArtifact]
- [x] CHK019 Are operator reconnect-after-logout scenarios covered by requirements for persistent PID, continuing runtime-status updates, and detached log output? [Coverage, Quickstart §Detached Server Start Check]

## Dependencies & Assumptions

- [x] CHK020 Are dependencies on local `config.toml`, `.env` or process environment, runtime state paths, PID file, runtime-status file, and log path documented without assuming one supervisor is always authoritative? [Dependency, Spec §Assumptions, Data Model §DetachedDaemonLaunch]
- [x] CHK021 Are rollback or fallback expectations documented when detached launch changes or invalidates a previously trusted operator launch workflow? [Compatibility, Spec §FR-028, Plan §Compatibility/Migration]
- [x] CHK022 Are low-spec resource and log-volume expectations extended to detached operation, including detached log growth and no busy-loop startup waiting? [Non-Functional, Plan §Resource Goals, Tasks §T042]

## Notes

- These checklist items validate requirement quality, not implementation behavior.
- Focus areas: rsync deployment, one-command detached server start, safe failure modes,
  daemon-owned status truth, terminal logout survival, and non-sensitive launch evidence.
- Depth: standard requirements-review gate for the active suppressor MVP freeze.
- Actor/timing: author and reviewer before implementation proceeds to detached launch work.
