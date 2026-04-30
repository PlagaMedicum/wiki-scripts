---
docmeta:
  status: draft
  review: feature-local
  purpose: Actionable implementation task breakdown for real-time suppression recovery.
  source: speckit-tasks on 2026-04-29
---

# Tasks: Real-Time Suppression Recovery

**Input**: Design documents from `specs/001-real-time-suppression/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`,
`quickstart.md`

**Tests**: Required. This feature is latency-sensitive, recovery-sensitive, compatibility-sensitive,
and operator-safety-sensitive, so every user story starts with tests for its independently
verifiable behavior.

**Organization**: Tasks are grouped by user story so the remaining work can be implemented and
validated incrementally from the current partially implemented state. User Story 1 restores
trustworthy immediate live hiding, User Story 2 restores truthful recovery and truthful operator
status, and User Story 3 restores useful operator commands and coverage reporting.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase because it touches
  different files and does not depend on incomplete work in that phase
- **[Story]**: User story identifier from `spec.md`
- Every task names the exact file paths it changes or validates

## Phase 1: Setup

**Purpose**: Re-ground the work on the actual deployment path and capture the compatibility baseline
before deeper implementation changes.

- [X] T001 Capture the actual launch-path baseline, current operator workflow, and current runtime-status versus command-report behavior in `suppressor/docs/operations.md`
- [X] T002 [P] Add older `runtime_status.json`, `command_report.json`, stale PID, and legacy `current_day_recheck` fixture coverage in `suppressor/tests/config_and_state.rs`
- [X] T003 [P] Record the operator-first status questions, current TUI pain points, and primary-row expectations in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`

---

## Phase 2: Foundational

**Purpose**: Shared contracts, compatibility-safe state, and scheduler foundations that block all
remaining user-story work.

**Critical**: No user-story phase should proceed until these shared contracts are in place.

- [X] T004 Add additive runtime-state fields for precise lag, current task, revision URLs, offline intervals, and rollback-aware compatibility notices in `suppressor/src/state.rs`
- [X] T005 [P] Add backward-compatible load and migration-needed diagnostic tests for older runtime-state and command-report shapes in `suppressor/tests/config_and_state.rs`
- [X] T006 Add config support and compatibility aliases for rolling last-24h daytime verification and randomized nightly full recheck in `suppressor/src/config.rs` and `suppressor/config.toml`
- [X] T007 [P] Add scheduler helper tests for rolling last-24h window calculation, randomized daytime delay selection, and randomized nightly full-recheck selection in `suppressor/src/scheduler.rs`
- [X] T008 Add shared revision URL and recovery-anchor selection helpers in `suppressor/src/mw_api.rs` and `suppressor/src/runtime.rs`
- [X] T009 [P] Add runtime-status contract tests for precise lag fields, current task serialization, and compatibility-notice serialization in `suppressor/src/runtime.rs` and `suppressor/tests/config_and_state.rs`
- [X] T010 Add bounded daemon-runtime versus command-report isolation helpers and compatibility parsing in `suppressor/src/state.rs` and `suppressor/src/commands.rs`

**Checkpoint**: Shared runtime, config, and compatibility surfaces are ready for story work.

---

## Phase 3: User Story 1 - Hide New Sensitive Edits Immediately (Priority: P1) 🎯 MVP

**Goal**: Eligible watched-page edits are detected, queued, hidden, and recorded immediately
without waiting for manual refreshes or scheduled reconciliation.

**Independent Test**: With the daemon running, publish or simulate a qualifying edit on a watched
page and verify the edit is queued immediately, hidden within the live target, and recorded in the
operator surface without manual reload.

### Tests for User Story 1

- [X] T011 [P] [US1] Add live stream tests for watched recentchange classification, duplicate suppression, and queue handoff in `suppressor/src/stream.rs`
- [X] T012 [P] [US1] Add runtime and worker tests for final live outcomes, `last_successful_hide_at` updates, and observed-to-queue timing in `suppressor/src/runtime.rs` and `suppressor/src/worker.rs`
- [X] T013 [P] [US1] Add source-refresh trigger tests for suppression-list deltas and request-page immediate catch-up in `suppressor/src/stream.rs` and `suppressor/src/catchup.rs`

### Implementation for User Story 1

- [X] T014 [US1] Refactor live recentchange handling into explicit watched-edit dispatch helpers in `suppressor/src/stream.rs` and `suppressor/src/recentchange.rs`
- [X] T015 [US1] Persist last successful hide details, live outcome source, and safe revision URLs in `suppressor/src/worker.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/state.rs`
- [X] T016 [US1] Record observed-to-queue and observed-to-hide latency metrics without unbounded samples in `suppressor/src/metrics.rs` and `suppressor/src/runtime.rs`
- [X] T017 [US1] Complete immediate source-refresh catch-up semantics for `Удзельнік:Wizardist/SuppressionList` and request-page triggers in `suppressor/src/stream.rs`, `suppressor/src/cache/source.rs`, and `suppressor/src/catchup.rs`
- [X] T018 [US1] Keep live hiding independent from scheduled reconciliation and manual reload paths in `suppressor/src/stream.rs` and `suppressor/src/runtime.rs`
- [X] T019 [US1] Surface last observed watched edit, queued live action, and last successful hide snapshots in `suppressor/src/tui_status.rs`

**Checkpoint**: User Story 1 is complete when a new watched edit is hidden and recorded immediately
without manual action, and source-page triggers start immediate bounded follow-up.

---

## Phase 4: User Story 2 - Detect And Recover From Real-Time Stalls (Priority: P2)

**Goal**: A running daemon that is stale, gapped, throttled, or otherwise ineffective becomes
visibly non-healthy, recovers from the last successful hide where possible, performs the approved
scheduled verification work, keeps failed verification or stale full watched-set coverage visible
as trust problems, and presents operator-first truthful status.

**Independent Test**: Simulate silent starvation, reconnect noise, a true gap, throttled recovery,
stale prior artifacts, a failed scheduled verification, and an overdue checkpoint map; verify the
daemon recovers from the correct anchor, scheduled verification runs are recorded truthfully,
failed verification does not clear on an unrelated stream reopen, and the primary status view shows
accurate protection state, next action, and full watched-set freshness evidence.

### Tests for User Story 2

- [X] T020 [P] [US2] Add stream watchdog tests for silent starvation, reconnect, invalid resume, and ordinary reopen without false startup recovery in `suppressor/src/stream.rs`
- [X] T021 [P] [US2] Add recovery-anchor and stale-state convergence tests for `last_successful_hide_at` recovery and fallback-anchor reporting in `suppressor/src/catchup.rs` and `suppressor/src/runtime.rs`
- [X] T022 [P] [US2] Add bounded API freshness-probe, precise lag calculation, and MediaWiki timestamp plus `badtimestamp` classification tests in `suppressor/src/mw_api.rs` and `suppressor/src/runtime.rs`
- [X] T023 [P] [US2] Add scheduler and overlap tests for rolling last-24h daytime verification, randomized nightly full recheck, and overlap with source-triggered or manual recovery in `suppressor/src/scheduler.rs` and `suppressor/src/reconcile.rs`
- [ ] T024 [P] [US2] Extend TUI and runtime-derivation tests for failed scheduled-verification visibility, checkpoint-freshness summaries, stale PID/runtime truth, latest actionable issue persistence, daemon-vs-command truth, and wrapped-row latest-follow behavior in `suppressor/src/tui_view.rs`, `suppressor/src/tui_status.rs`, and `suppressor/src/runtime.rs`

### Implementation for User Story 2

- [X] T025 [US2] Implement automatic gap recovery from `last_successful_hide_at` with explicit fallback-anchor reporting in `suppressor/src/catchup.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/stream.rs`
- [X] T026 [US2] Implement bounded freshness probing and wall-clock lag recalculation using compatibility seconds plus precise milliseconds in `suppressor/src/mw_api.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/state.rs`
- [X] T027 [US2] Gate startup, reconnect-noise, true gap recovery, and ordinary reopen transitions in `suppressor/src/stream.rs` and `suppressor/src/runtime.rs`
- [X] T028 [US2] Implement randomized rolling last-24h daytime verification and randomized nightly full recheck scheduling with shared backoff awareness in `suppressor/src/scheduler.rs`, `suppressor/src/reconcile.rs`, and `suppressor/src/config.rs`
- [X] T029 [US2] Persist explicit current-task, recovery-window, recent offline interval, and latest actionable issue fields in `suppressor/src/runtime.rs` and `suppressor/src/state.rs`
- [ ] T030 [US2] Extend the primary TUI status panel and derived runtime view with full watched-set freshness evidence, latest failed daytime or nightly verification outcome, and degraded-trust rows that de-emphasize bookkeeping fields in `suppressor/src/tui_status.rs` and `suppressor/src/tui_view.rs`
- [ ] T031 [US2] Surface compatibility or migration-needed diagnostics, approval text, rollback or fallback guidance, and stale PID/runtime cross-checks for invalid prior setup in `suppressor/src/runtime.rs`, `suppressor/src/state.rs`, and `suppressor/src/tui_view.rs`
- [ ] T032 [US2] Make latest-follow log rendering row-accurate and keep daemon and command logs visibly distinct in `suppressor/src/tui.rs` and `suppressor/src/tui_view.rs`
- [ ] T033 [US2] Share throttle or backoff state across live lookups, gap recovery, source-refresh catch-up, scheduled verification, reconciliation, and command surfaces, keep degraded live protection, failed scheduled verification, stale full watched-set coverage, and coalesced failure summaries visible while that state is active, and prevent stream reopen from clearing that state until a later successful verification or recovery does so in `suppressor/src/catchup.rs`, `suppressor/src/reconcile.rs`, `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui_status.rs`

**Checkpoint**: User Story 2 is complete when stale or throttled protection cannot appear healthy,
recovery starts from the last successful hide, scheduled verification is truthful, stale full
watched-set coverage is surfaced explicitly, and the primary status view answers the operator’s
core questions.

---

## Phase 5: User Story 3 - Verify Accident-Window Coverage (Priority: P3)

**Goal**: Operators can run useful catch-up and coverage actions with clear defaults, explicit
last-24h verification, direct revision links, and bounded reports that never replace daemon
realtime truth.

**Independent Test**: Run emergency catch-up and last-24h coverage from the TUI or CLI and verify
the exact window, safe revision links, unresolved next actions, and daemon-vs-command separation.

### Tests for User Story 3

- [ ] T034 [P] [US3] Add command tests for anchor-based emergency catch-up defaults, explicit `Last 24 hours` preset labeling, and bounded command-report output in `suppressor/src/commands.rs`
- [ ] T035 [P] [US3] Add TUI action tests for plain-language labels, last-24h preset wiring, refresh-status semantics, and reload-watched-pages semantics in `suppressor/src/tui.rs`
- [ ] T036 [P] [US3] Add report rendering tests for revision links, unresolved next actions, and command-report versus daemon-status separation in `suppressor/src/tui_view.rs` and `suppressor/src/commands.rs`

### Implementation for User Story 3

- [X] T037 [US3] Make emergency catch-up default to the active recovery-anchor window when available in `suppressor/src/commands.rs` and `suppressor/src/runtime.rs`
- [X] T038 [US3] Add a clearly labeled `Last 24 hours` coverage preset across `suppressor/src/cli.rs`, `suppressor/src/app.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui.rs`
- [X] T039 [US3] Render safe revision URLs and next actions in catch-up and coverage outputs in `suppressor/src/catchup.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui_view.rs`
- [X] T040 [US3] Relabel TUI actions and descriptions in plain language, including dry-run, refresh status, reload watched pages, and full watched-set recheck, in `suppressor/src/tui.rs` and `suppressor/src/tui_view.rs`
- [ ] T041 [US3] Keep bounded command-report surfaces compatible and distinct from daemon truth in `suppressor/src/state.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui_status.rs`

**Checkpoint**: User Story 3 is complete when operators can run useful coverage actions with clear
windows, clear labels, safe links, and no confusion about what the daemon itself is doing.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Close the release-evidence gap with docs, benchmark safety, low-spec verification, and
final compatibility approval evidence.

- [ ] T042 [P] Add benchmark safety, burst-of-10 controlled-event, and allow-list tests for `Удзельнік:Plaga med Bot/suppressor/tests` in `suppressor/src/commands.rs`, `suppressor/tests/api_integration.rs`, and `suppressor/tests/config_and_state.rs`
- [ ] T043 [P] Implement benchmark and low-spec verification entry points in `suppressor/src/commands.rs`, `suppressor/src/cli.rs`, and `suppressor/src/app.rs`
- [ ] T044 [P] Update operator docs for live states, recovery anchor, last-24h preset, randomized verification, reconciliation freshness evidence, and authoritative launch-path guidance in `suppressor/README.md` and `suppressor/docs/operations.md`
- [ ] T045 [P] Update implementation and runtime-boundary docs for scheduler semantics, status contracts, stale-runtime cross-checks, checkpoint-freshness evidence, bounded state, and operator-first TUI design in `suppressor/docs/implementation.md` and `suppressor/docs/runtime-boundaries.md`
- [ ] T046 [P] Update testing strategy and quickstart verification for anchor recovery, scheduler runs, operator-first TUI, reconciliation freshness truth, benchmark safety, and compatibility approval checks in `suppressor/docs/testing-strategy.md` and `specs/001-real-time-suppression/quickstart.md`
- [ ] T047 Run `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` and `rtk cargo test --manifest-path suppressor/Cargo.toml`, fixing regressions in `suppressor/tests/config_and_state.rs` and `suppressor/tests/api_integration.rs`
- [ ] T048 Run `rtk python3 tools/doc_workflow.py all` and record the docs-gate result in `specs/001-real-time-suppression/quickstart.md`
- [ ] T049 Restart the daemon through the actual launch path, verify PID/binary/runtime truth alignment, run the benchmark and low-spec checks, and capture compatibility approval evidence plus reconciliation-freshness and release-readiness results in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`
- [ ] T050 Evaluate whether the compatibility or migration-warning pattern should be generalized and, if so, document it in `specs/000-repo-governance/research.md`
- [ ] T051 [P] Add controlled rights/session failure reporting tests for live hiding and operator surfaces in `suppressor/src/worker.rs`, `suppressor/src/runtime.rs`, and `suppressor/tests/api_integration.rs`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. Establishes the actual deployment and compatibility
  baseline.
- **Foundational (Phase 2)**: Depends on Setup and blocks all story work because state, config, and
  compatibility contracts must be explicit first.
- **User Story 1 (Phase 3)**: Depends on Foundational and delivers the MVP live-protection path.
- **User Story 2 (Phase 4)**: Depends on Foundational and is required before production trust,
  because truthful recovery and truthful operator status are still missing.
- **User Story 3 (Phase 5)**: Depends on Foundational and reuses the shared recovery and report
  contracts.
- **Polish (Phase 6)**: Depends on the desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Can start immediately after Foundational and should be completed first.
- **US2 (P2)**: Can start after Foundational, but it is safest after US1 live-path changes settle
  because it depends on the final live outcome and recovery-anchor behavior.
- **US3 (P3)**: Can start after Foundational and parallelize with late US2 work once command-report
  isolation and compatibility helpers are in place.

### Within Each User Story

- Write the story tests first and confirm they fail against the current behavior.
- Implement the minimum code needed to satisfy the story’s independent test.
- Keep resource bounds, compatibility behavior, and daemon-vs-command truth intact while making the
  story pass.
- Validate the story independently before moving on.

### Parallel Opportunities

- Phase 1 tasks T002 and T003 can run in parallel after the baseline path is known.
- Phase 2 tasks T005, T007, and T009 can run in parallel across fixtures, scheduler tests, and
  runtime contract tests.
- US1 test tasks T011 through T013 can run in parallel.
- US2 test tasks T020 through T024 can run in parallel across stream, catch-up, API, scheduler,
  reconciliation-freshness, and TUI surfaces.
- US3 test tasks T034 through T036 can run in parallel across commands and TUI surfaces.
- Polish tasks T042 through T046 and T051 can run in parallel once the code paths stabilize.

---

## Parallel Example: User Story 1

```bash
Task: "T011 [US1] Add live stream tests for watched recentchange classification, duplicate suppression, and queue handoff in suppressor/src/stream.rs"
Task: "T012 [US1] Add runtime and worker tests for final live outcomes, last_successful_hide_at updates, and observed-to-queue timing in suppressor/src/runtime.rs and suppressor/src/worker.rs"
Task: "T013 [US1] Add source-refresh trigger tests for suppression-list deltas and request-page immediate catch-up in suppressor/src/stream.rs and suppressor/src/catchup.rs"
```

## Parallel Example: User Story 2

```bash
Task: "T020 [US2] Add stream watchdog tests for silent starvation, reconnect, invalid resume, and ordinary reopen without false startup recovery in suppressor/src/stream.rs"
Task: "T022 [US2] Add bounded API freshness-probe and precise lag calculation tests in suppressor/src/mw_api.rs and suppressor/src/runtime.rs"
Task: "T023 [US2] Add scheduler and overlap tests for rolling last-24h daytime verification, randomized nightly full recheck, and overlap with source-triggered or manual recovery in suppressor/src/scheduler.rs and suppressor/src/reconcile.rs"
Task: "T024 [US2] Extend TUI and runtime-derivation tests for failed scheduled-verification visibility, checkpoint-freshness summaries, stale PID/runtime truth, latest actionable issue persistence, daemon-vs-command truth, and wrapped-row latest-follow behavior in suppressor/src/tui_view.rs, suppressor/src/tui_status.rs, and suppressor/src/runtime.rs"
```

## Parallel Example: User Story 3

```bash
Task: "T034 [US3] Add command tests for anchor-based emergency catch-up defaults, explicit Last 24 hours preset labeling, and bounded command-report output in suppressor/src/commands.rs"
Task: "T035 [US3] Add TUI action tests for plain-language labels, last-24h preset wiring, refresh-status semantics, and reload-watched-pages semantics in suppressor/src/tui.rs"
Task: "T036 [US3] Add report rendering tests for revision links, unresolved next actions, and command-report versus daemon-status separation in suppressor/src/tui_view.rs and suppressor/src/commands.rs"
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Stop and validate the independent US1 live-protection flow

### Incremental Delivery

1. Setup plus Foundational establishes the compatible runtime and scheduler contracts.
2. US1 restores immediate live protection.
3. US2 restores truthful recovery and operator trust.
4. US3 restores useful operator commands and coverage evidence.
5. Phase 6 closes benchmark, low-spec, docs, and compatibility approval evidence.

### Suggested MVP Scope

The functional MVP is **Setup + Foundational + User Story 1**.  
Production-trust readiness requires **User Story 2** before the daemon should be treated as safely
recovered from this incident.

---

## Notes

- `[P]` tasks touch different files or contracts and can be split across workers.
- User story labels map directly to the stories in `spec.md` for traceability.
- This file preserves the current checked state where implementation or verification work has
  already been completed and refreshes the remaining backlog against the current spec and plan.
