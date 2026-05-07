---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for deployment-host evidence, remaining MVP gates, and final go/no-go wording.
  source:
  - speckit-checklist on 2026-05-06
  - speckit-checklist Q001 launch-evidence update on 2026-05-07
---

# Deployment Evidence Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [x] CHK001 Are deployment-host evidence requirements complete enough to distinguish the locally built rsync artifact, the deployed binary path, the active config path, and the target-host runtime state paths? [Completeness, Spec §FR-034, Spec §SC-020, Tasks §T038-T040]
- [x] CHK002 Are `server-start` deployment evidence requirements complete for command line used, PID, daemon-owned runtime-status freshness, detached log path, terminal logout survival, and stale or duplicate daemon diagnostics? [Completeness, Spec §SC-021, Quickstart §Detached Server Start Check, Tasks §T040]
- [x] CHK003 Are live or controlled dry-run smoke requirements complete for observed watched edit, queued action, hide or dry-run outcome, recovery anchor update, safe revision URL, and operator status evidence? [Completeness, Spec §SC-006, Spec §SC-018, Tasks §T041]
- [x] CHK004 Are recovery, rolling last-24h reconciliation, and nightly full recheck evidence requirements complete enough to cover both successful evidence and pending or failed non-healthy evidence? [Completeness, Spec §SC-003a, Spec §SC-017, Quickstart §Deployment Go/No-Go And Rollback Gate]
- [x] CHK005 Are deployment-host resource requirements complete for daemon-alone idle, daemon-plus-TUI idle, one active live/recovery/backoff sample, queue depths, API concurrency, state/report sizes, detached log growth, and coalesced-warning counts? [Completeness, Spec §SC-011, Tasks §T042]
- [x] CHK006 Are maintained-doc requirements complete for operator workflow, runtime boundaries, implementation lessons, testing strategy, and final evidence interpretation before MVP close-out? [Completeness, Spec §Documentation Impact, Tasks §T043-T044]

## Requirement Clarity

- [x] CHK007 Is "safe to quit the server terminal" defined with objective evidence for detached process survival rather than an informal backgrounding claim? [Clarity, Spec §SC-021, Quickstart §Detached Server Start Check]
- [x] CHK008 Is "deployment host evidence" clarified so local serial tests and local server builds cannot be mistaken for target-host launch, smoke, or resource proof? [Clarity, Quickstart §Evidence Freshness And Expiry, Tasks §T039-T042]
- [x] CHK009 Is controlled dry-run smoke wording clear enough to show when dry-run is acceptable, what it proves, and what it does not prove about live RevDel writes? [Clarity, Spec §US1 Independent Test, Contract §Start dry-run, Tasks §T041]
- [x] CHK010 Are nightly full-recheck requirements clear about how to record release evidence if the daemon has not yet run through a full uninterrupted night on the target host? [Ambiguity, Spec §SC-017, Quickstart §Deployment Go/No-Go And Rollback Gate]
- [x] CHK011 Is the final go/no-go requirement explicit about which missing evidence blocks release versus which evidence allows only a narrower local-confidence claim? [Clarity, Quickstart §Production Readiness Gate, Tasks §T046]

## Requirement Consistency

- [x] CHK012 Are T037/T038 freshness rules consistent with the rule that any later daemon-critical edit expires local test/build evidence before release claims? [Consistency, Tasks §Task Completion And Evidence Freshness Rules, Quickstart §Evidence Freshness And Expiry]
- [x] CHK013 Are launch-path requirements consistent across spec, plan, operator-command contract, runtime-status contract, quickstart, and operations-doc update tasks? [Consistency, Spec §FR-026..FR-029, Plan §Compatibility/Migration, Tasks §T040/T043]
- [x] CHK014 Are one-shot command report requirements consistent with daemon-owned status requirements when emergency catch-up or `Last 24 hours` evidence is collected during deployment smoke work? [Consistency, Spec §FR-021, Spec §FR-025, Contract §Operator Commands, Tasks §T029-T036]
- [x] CHK015 Are resource-economy release bounds consistent between the spec success criterion, implementation plan resource goals, quickstart minimum evidence, and operations-doc update requirement? [Consistency, Spec §SC-011, Plan §Resource Goals, Quickstart §Benchmark And Resource Check, Tasks §T042-T043]

## Acceptance Criteria Quality

- [x] CHK016 Can target-host `server-start` success be objectively measured from written criteria for PID liveness, runtime-status update, launch-path label, detached log output, and post-logout survival? [Measurability, Spec §SC-021, Quickstart §Detached Server Start Check]
- [x] CHK017 Can watched-edit smoke success be objectively measured from written criteria for observed timestamp, queue timestamp, final outcome, revision URL, and `last_successful_hide_at` or dry-run equivalent? [Measurability, Spec §SC-001, Spec §SC-006, Tasks §T041]
- [x] CHK018 Can recovery and reconciliation readiness be objectively measured from written criteria for selected anchor, covered window, outcome counts, unresolved samples, backoff state, and non-healthy pending or failed evidence? [Measurability, Spec §SC-003a, Spec §SC-017, Quickstart §Recovery Anchor Check]
- [x] CHK019 Can deployment-host resource acceptance be objectively measured against pass/fail thresholds rather than subjective "seems stable" wording? [Measurability, Spec §SC-011, Quickstart §Benchmark And Resource Check]
- [x] CHK020 Can the final MVP go/no-go decision be traced to required evidence rows for tests, build, detached launch, smoke, recovery, reconciliation, nightly, backoff, resource bounds, rollback, and fallback? [Traceability, Tasks §T046, Quickstart §Deployment Go/No-Go And Rollback Gate]

## Scenario Coverage

- [x] CHK021 Are exception-flow requirements specified for target-host missing config, missing secrets, unwritable state directory, unwritable log path, stale PID, duplicate daemon, startup timeout, and unhealthy runtime status? [Coverage, Spec §Edge Cases, Contract §Operator Commands]
- [x] CHK022 Are rollback requirements specified for a deployed binary that starts the wrong daemon, leaves an orphaned child, writes stale status, or creates false healthy launch evidence? [Coverage, Spec §FR-028, Quickstart §Deployment Go/No-Go And Rollback Gate]
- [x] CHK023 Are requirements specified for deployment smoke work when MediaWiki, EventStreams, account rights, or controlled test pages are temporarily unavailable? [Coverage, Spec §Assumptions, Spec §SC-006, Spec §SC-010]
- [x] CHK024 Are requirements specified for active backoff or scheduled reconciliation occurring during the target-host smoke check without hiding live-path evidence or allowing false healthy status? [Coverage, Spec §FR-003, Spec §FR-017, Spec §SC-002]
- [x] CHK025 Are requirements specified for operator evidence after terminal reconnect, including how to identify the same daemon process and distinguish daemon output from one-shot command output? [Coverage, Spec §FR-021, Spec §FR-026, Runtime Status Contract §Primary Operator View Contract]

## Non-Functional Requirements

- [x] CHK026 Are release-evidence requirements explicit that credentials, cookies, tokens, hidden text, `.env` contents, and sensitive article content must not appear in logs, status snapshots, command reports, or copied evidence? [Security, Spec §FR-012, Plan §Constraints]
- [x] CHK027 Are low-spec stability requirements defined without allowing resource economy to weaken live-hide latency, recovery timing, status truth, or documentation evidence? [Non-Functional, Spec §FR-019, Spec §SC-011, Constitution §VII]
- [x] CHK028 Are documentation requirements specific enough to preserve deployment lessons in maintained docs instead of relying on chat history or temporary checklist text? [Non-Functional, Spec §FR-020, Spec §SC-012, Tasks §T043-T044]

## Dependencies & Assumptions

- [x] CHK029 Are target-server assumptions documented for aarch64 Linux musl execution, filesystem permissions, outbound be.wikipedia.org access, shell invocation, and no reliance on systemd, tmux, screen, shell backgrounding, or `nohup`? [Assumption, Spec §Assumptions, Plan §Target Platform]
- [x] CHK030 Are dependencies on `cargo-zigbuild`, Zig, and local Zig cache access documented as local build prerequisites without turning sandbox cache failures into source-code failures? [Dependency, Spec §FR-034, Quickstart §US2 And MVP Test/Build Evidence]
- [x] CHK031 Are docs-gate requirements clear about the known inactive `002` metadata blocker so resolving unrelated artifacts is not accidentally pulled into the active suppressor MVP freeze? [Dependency, Constitution §VIII, Tasks §T045]

## Ambiguities & Conflicts

- [x] CHK032 Is there any ambiguity about whether US3 command/report hardening must complete before target-host MVP deployment trust or only before broader operator-command trust? [Ambiguity, Tasks §Suggested MVP Scope, Tasks §US3]
- [x] CHK033 Is there any conflict between the urgent minimal MVP deployment path and the final production-readiness gate requiring docs workflow, deployment-host resource samples, and final go/no-go evidence? [Conflict, Constitution §VIII, Quickstart §Production Readiness Gate]
- [x] CHK034 Is there any ambiguity about who records the final human accept, block, fallback, or rollback decision when deployment-host evidence is partial or externally blocked? [Ambiguity, Spec §FR-028, Tasks §T046]

## Notes

- Focus areas: target-host launch evidence, smoke evidence, resource evidence, documentation close-out, and final MVP go/no-go wording.
- Depth: standard reviewer checklist for the remaining active safety-freeze gates.
- Actor/timing: reviewer and operator before claiming deployment or production readiness.

## Q001 Approved Launch Evidence Completeness

- [x] CHK035 Are Q001-approved path 1 migration requirements complete enough to name the reviewed baseline, the human operator's target-host config update, allowed non-secret evidence, and rollback or fallback path? [Completeness, Questions §Q001, Quickstart §T039 Config-Stability Evidence, Tasks §T040]
- [x] CHK036 Are T040 evidence requirements complete for `server-start` receipt, PID file, runtime-status path, detached log path, launch-path label, status freshness, terminal logout survival, and no-secret migration evidence? [Completeness, Spec §SC-021, Quickstart §Detached Server Start Check, Review Queue §RQ002]
- [x] CHK037 Are requirements defined for evidence collected from an already-started daemon after Q001 approval, including whether the existing process can satisfy T040 or whether a fresh `server-start` receipt is required? [Ambiguity, Questions §Q001, Tasks §T040]

## Q001 Approved Launch Evidence Clarity

- [x] CHK038 Is "daemon-owned status freshness" quantified with acceptable status-file age, update interval, launch-path label, and PID correlation criteria? [Clarity, Spec §SC-021, Runtime Status Contract §Required Top-Level Shape, Quickstart §Detached Server Start Check]
- [x] CHK039 Is "terminal logout survival" defined as reconnect evidence for the same PID plus continuing daemon-owned status updates, rather than an informal claim that the SSH terminal was closed safely? [Clarity, Spec §SC-021, Quickstart §Detached Server Start Check]
- [x] CHK040 Is "no-secret migration evidence" defined with allowed and forbidden fields so docs cannot accidentally capture `.env` values, cookies, tokens, credentials, hidden text, or sensitive page content? [Security, Spec §FR-012, Plan §Constraints, Quickstart §Config Stability And Human Review Gate]

## Q001 Approved Launch Evidence Consistency

- [x] CHK041 Are Q001 approval states consistent across `questions.md`, `review-queue.md`, plan, quickstart, operations docs, and tasks so no active doc still treats the config path choice as pending? [Consistency, Questions §Q001, Review Queue §RQ001-RQ002, Plan §Review/Approval Workflow, Tasks §T040]
- [x] CHK042 Are T039 and T040 boundaries consistent: T039 records the reviewed config decision, T040 records target-host launch evidence, and neither authorizes further config churn? [Consistency, Constitution §V, Quickstart §T039 Config-Stability Evidence, Tasks §T039-T040]
- [x] CHK043 Are `server-start` launch evidence requirements consistent with the daemon-owned runtime truth rule and one-shot command separation rule? [Consistency, Spec §FR-021, Spec §FR-026, Runtime Status Contract §Surface, Contract §Start server daemon in background]

## Q001 Approved Acceptance Criteria Quality

- [x] CHK044 Can T040 be objectively accepted or blocked from written criteria without relying on the vague statement that "the daemon was started"? [Measurability, Spec §SC-021, Tasks §T040, Review Queue §RQ002]
- [x] CHK045 Are the exact maintained docs that must receive T040 evidence named, and is the required evidence small enough to record without copying raw logs or secrets? [Traceability, Tasks §T040, Quickstart §Detached Server Start Check, Operations §Server Build And Detached Launch]
- [x] CHK046 Are partial-evidence outcomes specified for cases where the PID is alive but status is stale, status is fresh but `launch_path` is not `server-start`, the log path is missing, or logout survival is unproven? [Coverage, Spec §FR-029, Spec §SC-021, Quickstart §Actual Launch-Path Check]

## Q001 Approved Scenario Coverage

- [x] CHK047 Are exception-flow requirements defined when post-Q001 launch evidence is blocked by target-host access interruption, missing command receipt, duplicate daemon detection, stale PID, or stale runtime status? [Exception Flow, Spec §Edge Cases, Contract §Failure behavior, Review Queue §RQ002]
- [x] CHK048 Are requirements defined for preserving protection while evidence is incomplete, so the daemon may continue running but MVP deployment trust remains blocked until T040 is recorded? [Coverage, Constitution §VIII, Quickstart §Current MVP Go/No-Go, Tasks §T040]
- [x] CHK049 Are dependencies between T040, T041, and T042 clear enough that live-smoke or resource evidence cannot mark the launch-path task complete by implication? [Dependency, Tasks §T040-T042, Quickstart §Active MVP Critical Path]

## Q001 Approved Dependencies & Assumptions

- [x] CHK050 Are assumptions documented for the human operator providing target-host evidence manually, given the repo-local agent may not have server access and evidence must exclude credentials and sensitive content? [Assumption, Review Queue §RQ002, Quickstart §Config Stability And Human Review Gate]

## Live-Hide Hotfix Requirement Completeness

- [x] CHK051 Are incident evidence requirements complete enough to name only redacted visible watched-page facts, known revision ID if available, watched-cache membership, processed-revision state, and daemon-status facts without requiring sensitive content? [Completeness, Quickstart §Active Live-Hide Incident With Sensitive Identifiers Redacted, Tasks §T041]
- [x] CHK052 Are immediate protection requirements defined for the exposed revision while the code fix is pending, including manual hide or emergency catch-up when a revision ID is known and an explicit release block when protection cannot be proven? [Coverage, Quickstart §Active Live-Hide Incident With Sensitive Identifiers Redacted, Tasks §T041]
- [x] CHK053 Are operator-account watched-edit requirements complete enough to state that an eligible edit by a synthetic operator-account actor must still enter the live watched-revision path and must not be silently filtered as own-account noise? [Completeness, Plan §Testing Strategy, Tasks §T047]

## Live-Hide Hotfix Requirement Clarity

- [x] CHK054 Is "first failed live-path boundary" clarified with the concrete boundary classes that may explain the incident: event observation, watched-title matching, processed-revision skip, live-queue handoff, RevDel/auth outcome, or stale/wrong deployed binary? [Clarity, Plan §Summary, Plan §Phase 0, Tasks §T049]
- [x] CHK055 Are allowed non-secret server facts and forbidden evidence fields clear enough that PID, status freshness, launch path, safe revision ID, and outcome can be recorded without copying credentials, cookies, tokens, hidden text, `.env` values, or sensitive article content? [Security, Spec §FR-012, Quickstart §Active Live-Hide Incident With Sensitive Identifiers Redacted]

## Live-Hide Hotfix Requirement Consistency

- [x] CHK056 Are dependencies between T040, T041, T047 through T052, and T042 consistent so deployment-host resource sampling cannot be treated as progress while the active live-hide path remains failed or unproven? [Consistency, Tasks §Task Completion And Evidence Freshness Rules, Tasks §Phase 6a, Tasks §Phase 6b]
- [x] CHK057 Are config-stability requirements consistent that Q001 remains answered, a code-only live-hide fix does not reopen config approval, and T049 must not change config shape or deployment-required config keys? [Consistency, Plan §Review/Approval Workflow, Quickstart §T040 Evidence Acceptance Contract, Tasks §T049]

## Live-Hide Acceptance Criteria Quality

- [x] CHK058 Can the operator-account regression requirement be objectively accepted from written criteria covering a synthetic watched page, actor class, live watched-revision dispatch, and absence of own-account, bot, or non-watched filtering? [Measurability, Tasks §T047, Spec §FR-002, Spec §FR-011]
- [x] CHK059 Can the post-fix target-host smoke requirement be objectively accepted or blocked from written evidence fields for daemon PID/status freshness, watched-edit outcome, dry-run or live mode, and rollback decision? [Measurability, Tasks §T052, Spec §SC-001, Spec §SC-021]

## Live-Hide Scenario Coverage

- [x] CHK060 Are requirements specified for the stale or wrong daemon-binary scenario so a running process cannot be mistaken for the rebuilt server artifact that contains the live-hide fix? [Coverage, Plan §Summary, Tasks §T040, Tasks §T052]
- [x] CHK061 Are duplicate, already-processed, and unprocessed incident revision scenarios defined clearly enough that an unprocessed watched revision cannot be skipped silently and already-processed skips remain operator-visible? [Coverage, Spec §FR-010, Tasks §T048]
- [x] CHK062 Are RevDel/auth failure requirements defined so a failed, blocked, throttled, or unresolved live hide is recorded as degraded protection instead of being collapsed into healthy runtime status? [Exception Flow, Spec §FR-013, Spec §FR-017, Plan §Testing Strategy]

## Live-Hide Dependencies & Assumptions

- [x] CHK063 Are assumptions documented that local repo state, old screenshots, or previously checked tasks cannot prove current target-host daemon behavior, and that only fresh non-secret target-host facts can satisfy the incident gate? [Assumption, Plan §Phase 0, Quickstart §Active Live-Hide Incident With Sensitive Identifiers Redacted]
- [x] CHK064 Are rollback or fallback requirements complete for the case where the rebuilt binary still fails live or controlled dry-run smoke, including manual protection, last trusted binary/config/state workflow, and continued MVP block status? [Coverage, Quickstart §Deployment Go/No-Go And Rollback Gate, Tasks §T052]
