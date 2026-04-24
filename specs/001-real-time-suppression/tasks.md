---
docmeta:
  status: draft
  review: feature-local
  purpose: Actionable implementation task breakdown for real-time suppression recovery.
  source: speckit-tasks on 2026-04-24
---

# Tasks: Real-Time Suppression Recovery

**Input**: Design documents from `specs/001-real-time-suppression/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`
**Tests**: Required. The feature is latency-sensitive and recovery-sensitive; each user story includes tests before implementation tasks.

**Organization**: Tasks are grouped by user story so US1 can ship as the first independently testable increment, followed by recovery visibility and accident-window verification.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase because it touches different files and has no dependency on their output.
- **[Story]**: User story identifier from `spec.md`; setup, foundational, and polish tasks omit story labels.
- Every task names the exact file path it changes or validates.

## Phase 1: Setup

**Purpose**: Confirm the implementation surface and baseline before changing the daemon.

- [ ] T001 Verify repository ignore coverage for suppressor build outputs, local daemon state, env files, and logs in `.gitignore`
- [ ] T002 [P] Run the current suppressor test baseline and record any pre-existing failures in `suppressor/docs/testing-strategy.md`
- [ ] T003 [P] Run the current docs workflow baseline and record the expected gate command in `specs/001-real-time-suppression/quickstart.md`
- [ ] T004 [P] Review existing production defaults that affect realtime recovery in `suppressor/config.toml`
- [ ] T061 [P] Diagnose silent EventStreams starvation with a controlled harness and record the suspected-fault result in `suppressor/docs/testing-strategy.md`
- [ ] T062 [P] Diagnose Last-Event-ID resume, reconnect, and replay behavior before changing recovery logic in `suppressor/src/stream.rs`
- [ ] T063 [P] Diagnose title matching, cache state, queue dispatch, worker health, and rights/session state as alternate active-incident causes in `suppressor/src/recentchange.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/worker.rs`

---

## Phase 2: Foundational

**Purpose**: Add shared config, status, API, and module boundaries needed by all user stories.

**Critical**: No user-story work should start until these tasks are complete.

- [ ] T005 Add realtime health, stream starvation, and bounded catch-up configuration fields in `suppressor/src/config.rs`
- [ ] T006 Add conservative production defaults for realtime health and bounded catch-up in `suppressor/config.toml`
- [ ] T007 Add config defaulting and deserialization tests for realtime recovery settings in `suppressor/src/config.rs`
- [ ] T008 Add realtime runtime status, recovery trigger, suppression outcome, and catch-up summary models in `suppressor/src/state.rs`
- [ ] T009 Add backward-compatible runtime status serialization tests for new realtime fields in `suppressor/src/state.rs`
- [ ] T010 Add runtime helper methods for realtime health updates, observed candidates, queued actions, and completed outcomes in `suppressor/src/runtime.rs`
- [ ] T011 Add observed-at, enqueued-at, source, and recovery-trigger metadata to revision deletion actions in `suppressor/src/runtime.rs`
- [ ] T012 Add bounded recent changes and revision visibility helper types for catch-up workflows in `suppressor/src/mw_api.rs`
- [ ] T013 [P] Add the catch-up module boundary and export it from `suppressor/src/catchup.rs` and `suppressor/src/lib.rs`
- [ ] T014 [P] Add reusable synthetic recent-change fixture builders for tests in `suppressor/src/recentchange.rs`
- [ ] T015 Extend the TUI status snapshot model to carry realtime health fields in `suppressor/src/tui_status.rs`

---

## Phase 3: User Story 1 - Hide New Sensitive Edits Immediately (Priority: P1)

**Goal**: New eligible watched-page edits are hidden automatically through the realtime path without waiting for manual reloads or reconciliation sweeps.

**Independent Test**: Publish or simulate a qualifying edit on a watched sensitive page and verify it is queued immediately, hidden within the target latency, and recorded as a completed realtime outcome.

### Tests for User Story 1

- [ ] T016 [P] [US1] Add unit tests for target-wiki recent-change classification and watched-title matching in `suppressor/src/stream.rs`
- [ ] T017 [P] [US1] Add dispatcher tests for live candidate queueing, processed-revision duplicate skips, and source metadata in `suppressor/src/runtime.rs`
- [ ] T018 [P] [US1] Add worker tests for successful live-hide outcomes and observed-to-hide timing in `suppressor/src/worker.rs`
- [ ] T064 [P] [US1] Add safety-boundary tests proving live and catch-up RevDel requests hide only public `user|comment` fields in `suppressor/src/worker.rs` and `suppressor/src/mw_api.rs`
- [ ] T065 [P] [US1] Add refusal tests for non-watched, malformed, missing-metadata, and policy-skipped revisions in `suppressor/src/runtime.rs`

### Implementation for User Story 1

- [ ] T019 [US1] Extract testable live recent-change handling from the EventStreams loop in `suppressor/src/stream.rs`
- [ ] T020 [US1] Update realtime status on stream open, target-wiki event, watched match, and queued live action in `suppressor/src/stream.rs`
- [ ] T021 [US1] Carry observed-at and enqueued-at timestamps from live events into revision deletion actions in `suppressor/src/runtime.rs`
- [ ] T022 [US1] Record event-observed-to-queue and event-observed-to-hide metrics in `suppressor/src/runtime.rs` and `suppressor/src/worker.rs`
- [ ] T023 [US1] Persist successful live hide, already-hidden, skipped, failed, retried, and unresolved outcomes in `suppressor/src/worker.rs`
- [ ] T024 [US1] Ensure the live hide path does not depend on reconciliation completion or manual cache reloads in `suppressor/src/stream.rs`
- [ ] T025 [US1] Update processed-revision skip behavior to record an auditable realtime outcome in `suppressor/src/runtime.rs`
- [ ] T026 [US1] Expose last observed event, last matched candidate, last queued hide, and last successful hide in `suppressor/src/tui_status.rs`
- [ ] T027 [US1] Update the realtime hide verification steps and expected latency evidence in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US1 should be independently testable with synthetic recent-change events and a controlled dry-run/live verification.

---

## Phase 4: User Story 2 - Detect And Recover From Real-Time Stalls (Priority: P2)

**Goal**: A daemon that is running but no longer observing or acting on recent changes becomes visibly unhealthy, reconnects, and runs bounded catch-up before reporting healthy.

**Independent Test**: Simulate a silent EventStreams stall or bad resume state and verify stale status appears within the threshold, recovery starts automatically, catch-up accounts for the missed window, and the TUI no longer looks healthy while ineffective.

### Tests for User Story 2

- [ ] T028 [P] [US2] Add controlled silent-stream starvation watchdog tests in `suppressor/src/stream.rs`
- [ ] T029 [P] [US2] Add reconnect and bounded catch-up trigger tests for invalid or stale resume state in `suppressor/src/catchup.rs`
- [ ] T030 [P] [US2] Add TUI rendering tests for healthy, stale, reconnecting, catching-up, and blocked realtime states in `suppressor/src/tui_view.rs`
- [ ] T031 [P] [US2] Add blocked auth and permission failure status tests in `suppressor/src/worker.rs`

### Implementation for User Story 2

- [ ] T032 [US2] Add a timeout or select-based watchdog around EventStreams reads in `suppressor/src/stream.rs`
- [ ] T033 [US2] Mark stale, reconnecting, catching-up, and blocked realtime health states with concrete recovery reasons in `suppressor/src/stream.rs`
- [ ] T034 [US2] Trigger bounded catch-up on startup, reconnect, silent starvation, and EventStreams resume gaps in `suppressor/src/stream.rs` and `suppressor/src/catchup.rs`
- [ ] T035 [US2] Implement bounded catch-up selection, ordering, dedupe, and stop conditions in `suppressor/src/catchup.rs`
- [ ] T036 [US2] Implement MediaWiki API calls for bounded recent-change catch-up windows in `suppressor/src/mw_api.rs`
- [ ] T037 [US2] Render realtime state, lag, stale threshold, last observed event, latest error, and recovery trigger in `suppressor/src/tui_view.rs`
- [ ] T038 [US2] Persist blocked realtime state before fatal auth or permission exits in `suppressor/src/worker.rs`
- [ ] T039 [US2] Update signal and manual reload notices to distinguish cache reloads from realtime recovery in `suppressor/src/signal_control.rs`

**Checkpoint**: US2 should prove that "daemon running" and "realtime suppression effective" are separate observable states.

---

## Phase 5: User Story 3 - Verify Accident-Window Coverage (Priority: P3)

**Goal**: Operators can run an emergency catch-up and coverage report for the suspected suppressor-rights accident window and see exactly what remains unresolved.

**Independent Test**: Run coverage against a bounded historical window and verify every eligible watched edit is reported as hidden, already hidden, skipped by policy, failed, retried, or unresolved.

### Tests for User Story 3

- [ ] T040 [P] [US3] Add coverage-window accounting tests for hidden, already-hidden, skipped, failed, retried, and unresolved outcomes in `suppressor/src/catchup.rs`
- [ ] T041 [P] [US3] Add command output formatting tests that avoid sensitive comments or text in `suppressor/src/commands.rs`
- [ ] T042 [P] [US3] Add CLI parse tests for emergency catch-up and accident-window coverage commands in `suppressor/src/cli.rs`

### Implementation for User Story 3

- [ ] T043 [US3] Implement accident-window coverage summary and unresolved item models in `suppressor/src/catchup.rs`
- [ ] T044 [US3] Add command handlers for emergency catch-up and accident-window coverage in `suppressor/src/commands.rs`
- [ ] T045 [US3] Wire CLI variants and application dispatch for emergency catch-up and coverage commands in `suppressor/src/cli.rs` and `suppressor/src/app.rs`
- [ ] T046 [US3] Add TUI actions for emergency catch-up and accident-window coverage in `suppressor/src/tui.rs`
- [ ] T047 [US3] Render emergency catch-up progress and coverage summaries without crowding the status pane in `suppressor/src/tui_view.rs`
- [ ] T048 [US3] Ensure coverage reports include title, revision id, age, and reason while omitting sensitive edit text in `suppressor/src/catchup.rs`
- [ ] T049 [US3] Persist latest recovery summary counts and unresolved totals in runtime status in `suppressor/src/state.rs`
- [ ] T050 [US3] Update accident-window command examples and expected report interpretation in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US3 should let an operator close the accident window with evidence instead of relying on the nightly reconciliation log.

---

## Phase 6: Polish, Documentation, And Release Readiness

**Purpose**: Update durable docs, run gates, collect evidence, and prepare the merge.

- [ ] T051 [P] Update operator-facing realtime behavior, health states, and emergency commands in `suppressor/README.md`
- [ ] T052 [P] Update production operation guidance for stale streams, catch-up, and blocked auth states in `suppressor/docs/operations.md`
- [ ] T053 [P] Update implementation notes for realtime stream handling, bounded catch-up, and outcome accounting in `suppressor/docs/implementation.md`
- [ ] T054 [P] Update runtime boundary notes for background listeners, API calls, and local state files in `suppressor/docs/runtime-boundaries.md`
- [ ] T055 [P] Update test strategy with latency, watchdog, catch-up, and accident-window verification coverage in `suppressor/docs/testing-strategy.md`
- [ ] T056 Run the suppressor test suite with serialized tests and record the gate result in `suppressor/docs/testing-strategy.md`
- [ ] T057 Run the full suppressor test suite and record any remaining flaky or integration-only constraints in `suppressor/docs/testing-strategy.md`
- [ ] T058 Run the repository docs workflow gate and record the result in `specs/001-real-time-suppression/quickstart.md`
- [ ] T059 Run a controlled dry-run or live verification benchmark for the realtime path and record latency evidence in `suppressor/docs/operations.md`
- [ ] T060 Remove obsolete feature-local notes that should remain only in git history after durable lessons are copied into `suppressor/docs/implementation.md`
- [ ] T066 Record p95 and p99 latency evidence with the controlled sample size and any smaller smoke-check limits in `suppressor/docs/operations.md`
- [ ] T067 Copy durable close-out lessons from `specs/001-real-time-suppression/` into maintained suppressor docs before removing obsolete feature-local planning notes from `specs/001-real-time-suppression/`

---

## Dependencies And Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup completion and blocks all user stories.
- **US1 (Phase 3)**: Depends on Foundational. This is the minimum viable urgent fix.
- **US2 (Phase 4)**: Depends on Foundational and should follow US1 so the recovery path can reuse live-action outcome metadata.
- **US3 (Phase 5)**: Depends on Foundational and benefits from US1/US2 outcome accounting.
- **Polish (Phase 6)**: Depends on completed user stories.

### User Story Dependencies

- **US1 (P1)**: Can be developed after Foundational; no dependency on US2 or US3.
- **US2 (P2)**: Can be developed after Foundational, but should reuse US1 action metadata if US1 lands first.
- **US3 (P3)**: Can be developed after Foundational, but should reuse US1/US2 catch-up and outcome models.

### Within Each User Story

- Write and run tests first.
- Implement the smallest code path that makes those tests pass.
- Update operator-visible status and docs for the completed story.
- Verify the story independently before starting the next story.

### Parallel Opportunities

- Setup tasks T002, T003, and T004 can run in parallel after T001 starts.
- Foundational tasks T013 and T014 can run in parallel with config/state work once module names are settled.
- US1 tests T016, T017, and T018 can run in parallel because they touch `stream.rs`, `runtime.rs`, and `worker.rs`.
- US2 tests T028, T029, T030, and T031 can run in parallel because they touch separate modules.
- US3 tests T040, T041, and T042 can run in parallel because they touch separate command, CLI, and catch-up surfaces.
- Documentation tasks T051 through T055 can run in parallel after the behavior is stable.

---

## Implementation Strategy

### MVP First: US1

1. Complete Setup and Foundational tasks.
2. Complete US1 tests and implementation.
3. Verify a synthetic recent-change event queues and records a hide without reconciliation.
4. Run a controlled dry-run or live check to measure event-observed-to-hide latency.

### Incremental Delivery

1. Ship US1 for immediate hiding.
2. Add US2 to make silent stream stalls visible and self-recovering.
3. Add US3 to close the accident window with bounded evidence.
4. Update durable docs and remove temporary feature-local notes after lessons are captured.

### Final Validation

1. Run `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1`.
2. Run `rtk cargo test --manifest-path suppressor/Cargo.toml`.
3. Run `rtk python3 tools/doc_workflow.py all`.
4. Run `/speckit.analyze` and resolve any remaining task/spec/plan inconsistencies before merge.
