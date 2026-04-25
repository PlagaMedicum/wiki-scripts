---
docmeta:
  status: draft
  review: feature-local
  purpose: Actionable implementation task breakdown for real-time suppression recovery.
  source: speckit-tasks on 2026-04-25
---

# Tasks: Real-Time Suppression Recovery

**Input**: Design documents from `specs/001-real-time-suppression/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`
**Tests**: Required. The feature is latency-sensitive, recovery-sensitive, and operator-safety-sensitive; test tasks precede implementation tasks in each story.

**Organization**: Tasks are grouped by user story so US1 can ship as the urgent MVP, followed by stall recovery and accident-window coverage. Cross-cutting benchmark, resource-economy, and durable-doc tasks close the feature.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase because it touches different files and has no dependency on their output.
- **[Story]**: User story identifier from `spec.md`; setup, foundational, and polish tasks omit story labels.
- Every task names the exact file path it changes or validates.

## Phase 1: Setup

**Purpose**: Establish the current baseline and avoid hiding pre-existing failures inside the fix.

- [ ] T001 Run the serialized suppressor baseline test command and record existing failures or pass status in `suppressor/docs/testing-strategy.md`
- [ ] T002 [P] Run the repo docs workflow baseline and record the expected close-out command in `specs/001-real-time-suppression/quickstart.md`
- [ ] T003 [P] Audit current realtime, catch-up, API, and resource defaults and record the release constraints in `suppressor/docs/operations.md`
- [ ] T004 [P] Audit current stream, cache, catch-up, API, worker, runtime, and TUI module ownership and record the internal boundary map in `suppressor/docs/implementation.md`
- [ ] T005 [P] Capture the 2026-04-25 terminal warning storm symptoms and safe diagnostic evidence in `suppressor/docs/operations.md`

---

## Phase 2: Foundational

**Purpose**: Add shared contracts, bounded-resource defaults, and test surfaces needed by all user stories.

**Critical**: No user-story work should start until these tasks are complete.

- [ ] T006 Add a shared MediaWiki UTC second-precision timestamp serializer for API parameters in `suppressor/src/mw_api.rs`
- [ ] T007 [P] Add timestamp serialization tests for `rvstart`, coverage windows, and future API timestamp parameters in `suppressor/src/mw_api.rs`
- [ ] T008 Add `ApiFailureSnapshot`, retryability, operation, and safe-message types in `suppressor/src/mw_api.rs` and `suppressor/src/state.rs`
- [ ] T009 [P] Add API failure classification tests for JSON API errors, non-JSON responses, HTTP status failures, decode failures, timeouts, and network errors in `suppressor/src/mw_api.rs`
- [ ] T010 Add `SourceListRefresh`, `ResourceEconomySnapshot`, `BenchmarkRun`, and durable realtime status fields in `suppressor/src/state.rs`
- [ ] T011 [P] Add backward-compatible runtime-status load/save tests for realtime, source-refresh, latest-error, and resource-economy fields in `suppressor/src/state.rs`
- [ ] T012 Add bounded queue, catch-up concurrency, warning aggregation, freshness probe, benchmark, and retention settings in `suppressor/src/config.rs`
- [ ] T013 Add conservative production defaults for bounded queues, low catch-up concurrency, freshness probes, warning summaries, and state retention in `suppressor/config.toml`
- [ ] T014 [P] Add config defaulting and TOML deserialization tests for all new resource and recovery settings in `suppressor/src/config.rs`
- [ ] T015 Define catch-up request, catch-up result, source-refresh catch-up, and warning-summary structs in `suppressor/src/catchup.rs`
- [ ] T016 [P] Export any new catch-up/service-boundary module items through `suppressor/src/lib.rs`
- [ ] T017 Add source-cache diff helpers for newly added and removed watched titles in `suppressor/src/cache.rs`
- [ ] T018 [P] Add source-cache diff tests for unchanged, added, removed, redirect-derived, and malformed-title cases in `suppressor/src/cache.rs`
- [ ] T019 Add runtime helper methods for realtime status, source-refresh status, queued actions, final outcomes, error snapshots, warning summaries, and resource summaries in `suppressor/src/runtime.rs`
- [ ] T020 [P] Add synthetic recentchange, source-page event, request-page event, and API-response fixtures for tests in `suppressor/src/recentchange.rs`
- [ ] T021 Add realtime, source-refresh, latest-error, warning-summary, benchmark, and resource fields to the TUI status snapshot in `suppressor/src/tui_status.rs`

**Checkpoint**: Foundation is ready when shared structs serialize safely, config defaults are bounded, and tests can build synthetic live/catch-up/source events without network access.

---

## Phase 3: User Story 1 - Hide New Sensitive Edits Immediately (Priority: P1) - MVP

**Goal**: New eligible watched-page edits are detected, queued, hidden, and reported immediately without waiting for manual refreshes or reconciliation.

**Independent Test**: Simulate or publish a qualifying edit on a watched page and verify it is queued immediately, hidden within the target, and recorded as a live outcome without manual reload.

### Tests for User Story 1

- [ ] T022 [P] [US1] Add live target-wiki event classification and watched-title matching tests in `suppressor/src/stream.rs`
- [ ] T023 [P] [US1] Add live dispatcher tests for immediate queueing, duplicate skips, policy skips, missing metadata, and final outcome recording in `suppressor/src/runtime.rs`
- [ ] T024 [P] [US1] Add RevDel safety-boundary tests proving live hide requests target only public `user|comment` fields in `suppressor/src/worker.rs`
- [ ] T025 [P] [US1] Add observed-to-queue and observed-to-hide timing tests for successful, already-hidden, skipped, failed, retrying, and unresolved live outcomes in `suppressor/src/worker.rs`
- [ ] T026 [P] [US1] Add source-list recentchange tests that refresh `Удзельнік:Wizardist/SuppressionList`, diff newly added titles, and start immediate bounded catch-up in `suppressor/src/stream.rs`
- [ ] T027 [P] [US1] Add request-page trigger tests for `Вікіпедыя:Запыты да схавальнікаў` recent-window catch-up in `suppressor/src/stream.rs`
- [ ] T028 [P] [US1] Add compact TUI status snapshot tests for last observed event, matched edit, queued action, successful hide, and source-refresh summary in `suppressor/src/tui_status.rs`

### Implementation for User Story 1

- [ ] T029 [US1] Extract testable live recentchange handling from the EventStreams loop in `suppressor/src/stream.rs`
- [ ] T030 [US1] Queue eligible live watched-page edits immediately with observed-at, enqueued-at, source, and recovery-trigger metadata in `suppressor/src/runtime.rs`
- [ ] T031 [US1] Update stream status on stream open, target-wiki event, watched match, queued live action, and source-page event in `suppressor/src/stream.rs`
- [ ] T032 [US1] Record event-observed-to-queue and event-observed-to-hide metrics without adding unbounded samples in `suppressor/src/metrics.rs`
- [ ] T033 [US1] Persist successful live hide, already-hidden, skipped, failed, retrying, unresolved, and blocked outcomes in `suppressor/src/worker.rs`
- [ ] T034 [US1] Ensure live hiding does not wait for nightly reconciliation, current-day reconciliation, or manual cache reload in `suppressor/src/stream.rs`
- [ ] T035 [US1] Implement refresh-plus-immediate-catch-up for `Удзельнік:Wizardist/SuppressionList` source-list changes in `suppressor/src/stream.rs` and `suppressor/src/catchup.rs`
- [ ] T036 [US1] Implement request-page recent-window catch-up for `Вікіпедыя:Запыты да схавальнікаў` and configured request pages in `suppressor/src/stream.rs` and `suppressor/src/catchup.rs`
- [ ] T037 [US1] Persist source-refresh outcomes, newly added title counts, catch-up scope, and safe errors in `suppressor/src/state.rs`
- [ ] T038 [US1] Render live hide status and source-refresh catch-up status compactly in `suppressor/src/tui_view.rs`
- [ ] T039 [US1] Update US1 quickstart verification for live hiding, source-list immediate recovery, request-page recovery, and latency evidence in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US1 is independently complete when a controlled eligible live event and a source-list edit both trigger bounded immediate handling without manual reload or reconciliation.

---

## Phase 4: User Story 2 - Detect And Recover From Real-Time Stalls (Priority: P2)

**Goal**: A daemon that is running but not effectively observing/hiding becomes visibly unhealthy, recovers with bounded catch-up, and avoids warning storms.

**Independent Test**: Simulate a silent stream, reconnect, bad resume, API timestamp error, and repeated catch-up failure; verify stale/blocked status, classified errors, coalesced warnings, and bounded recovery.

### Tests for User Story 2

- [ ] T040 [P] [US2] Add controlled silent EventStreams starvation and watchdog transition tests in `suppressor/src/stream.rs`
- [ ] T041 [P] [US2] Add reconnect, invalid-resume, replay, and resume-gap recovery tests in `suppressor/src/stream.rs`
- [ ] T042 [P] [US2] Add bounded API freshness probe tests for quiet-stream versus stale-stream lag calculation in `suppressor/src/mw_api.rs`
- [ ] T043 [P] [US2] Add bounded catch-up selection, newest-first ordering, dedupe, concurrency-limit, and stop-condition tests in `suppressor/src/catchup.rs`
- [ ] T044 [P] [US2] Add `badtimestamp`, non-JSON, HTTP status, decode, timeout, auth/session, and permission classification tests in `suppressor/src/mw_api.rs`
- [ ] T045 [P] [US2] Add repeated catch-up warning coalescing tests with aggregate counts and safe title samples in `suppressor/src/catchup.rs`
- [ ] T046 [P] [US2] Add TUI rendering tests for healthy, stale, reconnecting, catching-up, unhealthy, blocked, and compact-terminal states in `suppressor/src/tui_view.rs`
- [ ] T047 [P] [US2] Add blocked rights/session and retryable transient failure status tests in `suppressor/src/worker.rs`

### Implementation for User Story 2

- [ ] T048 [US2] Add timeout or select-based watchdog handling around EventStreams reads in `suppressor/src/stream.rs`
- [ ] T049 [US2] Set stale, reconnecting, catching-up, unhealthy, and blocked realtime states with explicit recovery reasons in `suppressor/src/runtime.rs`
- [ ] T050 [US2] Implement a low-cost bounded target-wiki freshness probe using recentchanges in `suppressor/src/mw_api.rs`
- [ ] T051 [US2] Trigger bounded catch-up on startup, reconnect, silent starvation, invalid resume, and resume gaps in `suppressor/src/stream.rs`
- [ ] T052 [US2] Implement bounded catch-up windows, newest-first selection, title scope, dedupe, concurrency limits, and completion summaries in `suppressor/src/catchup.rs`
- [ ] T053 [US2] Use the shared MediaWiki timestamp serializer for catch-up, coverage, freshness, and revision-query API parameters in `suppressor/src/mw_api.rs`
- [ ] T054 [US2] Persist classified API, transport, auth/session, and source-refresh failures in realtime status without response bodies or secrets in `suppressor/src/state.rs`
- [ ] T055 [US2] Replace per-page catch-up warning spam with root-cause summary aggregation in `suppressor/src/catchup.rs`
- [ ] T056 [US2] Surface warning aggregates, classified latest errors, retryability, safe samples, and next action in `suppressor/src/tui_status.rs`
- [ ] T057 [US2] Render realtime state, lag, stale threshold, recovery trigger, latest error, and coalesced warning summary in `suppressor/src/tui_view.rs`
- [ ] T058 [US2] Persist blocked state before fatal auth, session, or permission exits in `suppressor/src/worker.rs`
- [ ] T059 [US2] Update manual reload and signal notices so cache reload is labeled diagnostic/fallback rather than realtime recovery in `suppressor/src/signal_control.rs`
- [ ] T060 [US2] Update US2 quickstart verification for silent starvation, freshness probing, timestamp errors, API classification, and warning coalescing in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US2 is independently complete when a running-but-stale daemon cannot appear healthy and repeated API failures produce one actionable summary instead of terminal spam.

---

## Phase 5: User Story 3 - Verify Accident-Window Coverage (Priority: P3)

**Goal**: Operators can verify a bounded accident or downtime window and see every eligible edit accounted for without exposing sensitive content.

**Independent Test**: Run accident-window coverage over a controlled window and verify all eligible edits are counted as hidden, already-hidden, skipped, failed, retrying, unresolved, or blocked with safe next actions.

### Tests for User Story 3

- [ ] T061 [P] [US3] Add coverage-window accounting tests for hidden, already-hidden, skipped, failed, retrying, unresolved, and blocked outcomes in `suppressor/src/catchup.rs`
- [ ] T062 [P] [US3] Add accident-window input validation tests for missing timezone, inverted ranges, oversized windows, dry-run, and report-only mode in `suppressor/src/cli.rs`
- [ ] T063 [P] [US3] Add emergency catch-up command tests for default 30-minute windows, explicit bounds, and maximum-scope overrides in `suppressor/src/commands.rs`
- [ ] T064 [P] [US3] Add sensitive-output tests proving coverage and emergency reports omit hidden text, raw comments, credentials, tokens, cookies, and response bodies in `suppressor/src/commands.rs`
- [ ] T065 [P] [US3] Add TUI action and progress-rendering tests for emergency catch-up and coverage report states in `suppressor/src/tui_view.rs`

### Implementation for User Story 3

- [ ] T066 [US3] Implement `CoverageWindow`, unresolved item, and per-outcome summary models in `suppressor/src/catchup.rs`
- [ ] T067 [US3] Implement emergency catch-up command handling and bounded default-window behavior in `suppressor/src/commands.rs`
- [ ] T068 [US3] Implement accident-window coverage command handling with strict timestamp validation in `suppressor/src/commands.rs`
- [ ] T069 [US3] Wire emergency catch-up and accident-window coverage CLI variants in `suppressor/src/cli.rs`
- [ ] T070 [US3] Dispatch emergency catch-up and accident-window coverage from the application entrypoint in `suppressor/src/app.rs`
- [ ] T071 [US3] Add TUI actions for emergency catch-up and accident-window coverage without expanding the action list beyond operator-focused entries in `suppressor/src/tui.rs`
- [ ] T072 [US3] Render coverage progress, outcome counts, unresolved totals, and next action compactly in `suppressor/src/tui_view.rs`
- [ ] T073 [US3] Persist latest recovery and coverage summary counts in runtime status in `suppressor/src/state.rs`
- [ ] T074 [US3] Format unresolved report items with title, revision ID, age, reason, and next action while omitting sensitive payloads in `suppressor/src/catchup.rs`
- [ ] T075 [US3] Update US3 quickstart examples and release interpretation for emergency catch-up and accident-window coverage in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US3 is independently complete when the operator can close or escalate an accident window from evidence rather than from nightly reconciliation assumptions.

---

## Phase 6: Polish, Benchmark, Resource Economy, Documentation, And Release Readiness

**Purpose**: Add production-safe benchmark evidence, low-spec verification, durable lessons, and final gates without compromising performance or documentation quality.

- [ ] T076 [P] Add bot-test-page benchmark validation tests for page allow-listing, bot edit marker, run labels, safe content, smoke-mode samples, and no source-list mutation in `suppressor/src/commands.rs`
- [ ] T077 Implement the production-safe benchmark command for `Удзельнік:Plaga med Bot/suppressor/tests` in `suppressor/src/commands.rs`
- [ ] T078 Wire benchmark CLI and optional TUI entrypoints with safe defaults in `suppressor/src/cli.rs` and `suppressor/src/tui.rs`
- [ ] T079 Record publish-to-detect, detect-to-queue, queue-to-hide, publish-to-hidden, p50, p95, p99, and smoke-only evidence without unbounded samples in `suppressor/src/metrics.rs`
- [ ] T080 [P] Add resource-economy verification tests or dry-run checks for queue depth, API concurrency, state-file retention, benchmark sample retention, and warning aggregation in `suppressor/tests/config_and_state.rs`
- [ ] T081 Implement resource-economy verification command output for CPU, memory, queue depth, API concurrency, state file sizes, log volume, and warning coalescing in `suppressor/src/commands.rs`
- [ ] T082 Wire resource-economy verification CLI entrypoint and report-only mode in `suppressor/src/cli.rs`
- [ ] T083 [P] Update operator-facing realtime behavior, emergency commands, benchmark, and low-spec expectations in `suppressor/README.md`
- [ ] T084 [P] Update production operation guidance for stale streams, source-list recovery, classified errors, coalesced warnings, benchmarks, low-spec evidence, and stop conditions in `suppressor/docs/operations.md`
- [ ] T085 [P] Update implementation notes for internal service boundaries, timestamp serialization, source-refresh catch-up, API classification, bounded queues, and warning aggregation in `suppressor/docs/implementation.md`
- [ ] T086 [P] Update runtime boundary notes for new state fields, retention bounds, status compatibility, command surfaces, and safe payload rules in `suppressor/docs/runtime-boundaries.md`
- [ ] T087 [P] Update testing strategy with serialized/full cargo gates, mocked API cases, source-list recovery tests, benchmark safety tests, and low-spec checks in `suppressor/docs/testing-strategy.md`
- [ ] T088 Run `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` and record the gate result in `suppressor/docs/testing-strategy.md`
- [ ] T089 Run `rtk cargo test --manifest-path suppressor/Cargo.toml` and record any remaining parallel-test limits in `suppressor/docs/testing-strategy.md`
- [ ] T090 Run the controlled bot-test-page benchmark and record timing evidence, sample-size limits, and unresolved items in `suppressor/docs/operations.md`
- [ ] T091 Run low-spec resource verification for daemon, TUI, catch-up, source-refresh catch-up, benchmark, and repeated-failure scenarios and record evidence in `suppressor/docs/operations.md`
- [ ] T092 Run `rtk python3 tools/doc_workflow.py all` and record the docs gate result in `specs/001-real-time-suppression/quickstart.md`
- [ ] T093 Run final quickstart production-readiness checks and record any unavailable external wiki checks or narrower confidence claims in `specs/001-real-time-suppression/quickstart.md`
- [ ] T094 Copy durable incident lessons from feature-local artifacts into maintained suppressor docs before removing obsolete notes in `suppressor/docs/implementation.md`

---

## Dependencies And Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup and blocks all user stories.
- **US1 (Phase 3)**: Depends on Foundational and is the minimum viable urgent fix.
- **US2 (Phase 4)**: Depends on Foundational and can begin after US1 live-outcome metadata is available.
- **US3 (Phase 5)**: Depends on Foundational and reuses catch-up/outcome models from US1/US2.
- **Polish (Phase 6)**: Depends on completed user-story behavior.

### User Story Dependencies

- **US1 (P1)**: Build first. It restores immediate live hiding and source-list/request-page immediate recovery.
- **US2 (P2)**: Build second. It makes stale monitoring and repeated failures visible and recoverable.
- **US3 (P3)**: Build third. It provides operator evidence for accident-window closure.

### Within Each User Story

- Write or update the tests first and confirm they fail against the current behavior.
- Implement the smallest code path that makes the story tests pass.
- Keep queues, concurrency, retained state, warning output, and benchmark samples bounded.
- Verify the story independently before moving to the next story.

### Parallel Opportunities

- Setup tasks T002 through T005 can run in parallel after T001 starts.
- Foundational tests T007, T009, T011, T014, T018, and T020 can run in parallel once task ownership is assigned.
- US1 tests T022 through T028 can run in parallel across stream, runtime, worker, and TUI status surfaces.
- US2 tests T040 through T047 can run in parallel across stream, API, catch-up, worker, and TUI surfaces.
- US3 tests T061 through T065 can run in parallel across catch-up, CLI, commands, and TUI surfaces.
- Documentation tasks T083 through T087 can run in parallel after behavior and command names stabilize.

---

## Parallel Example: US1

```bash
Task: "T022 [US1] Add live target-wiki event classification and watched-title matching tests in suppressor/src/stream.rs"
Task: "T023 [US1] Add live dispatcher tests for immediate queueing, duplicate skips, policy skips, missing metadata, and final outcome recording in suppressor/src/runtime.rs"
Task: "T024 [US1] Add RevDel safety-boundary tests proving live hide requests target only public user|comment fields in suppressor/src/worker.rs"
Task: "T028 [US1] Add compact TUI status snapshot tests for last observed event, matched edit, queued action, successful hide, and source-refresh summary in suppressor/src/tui_status.rs"
```

## Parallel Example: US2

```bash
Task: "T040 [US2] Add controlled silent EventStreams starvation and watchdog transition tests in suppressor/src/stream.rs"
Task: "T042 [US2] Add bounded API freshness probe tests for quiet-stream versus stale-stream lag calculation in suppressor/src/mw_api.rs"
Task: "T043 [US2] Add bounded catch-up selection, newest-first ordering, dedupe, concurrency-limit, and stop-condition tests in suppressor/src/catchup.rs"
Task: "T046 [US2] Add TUI rendering tests for healthy, stale, reconnecting, catching-up, unhealthy, blocked, and compact-terminal states in suppressor/src/tui_view.rs"
```

## Parallel Example: US3

```bash
Task: "T061 [US3] Add coverage-window accounting tests for hidden, already-hidden, skipped, failed, retrying, unresolved, and blocked outcomes in suppressor/src/catchup.rs"
Task: "T062 [US3] Add accident-window input validation tests for missing timezone, inverted ranges, oversized windows, dry-run, and report-only mode in suppressor/src/cli.rs"
Task: "T063 [US3] Add emergency catch-up command tests for default 30-minute windows, explicit bounds, and maximum-scope overrides in suppressor/src/commands.rs"
Task: "T065 [US3] Add TUI action and progress-rendering tests for emergency catch-up and coverage report states in suppressor/src/tui_view.rs"
```

---

## Implementation Strategy

### MVP First: US1

1. Complete Setup and Foundational tasks.
2. Complete US1 tests and implementation.
3. Verify a synthetic watched-page event queues and records a hide without reconciliation.
4. Verify a source-list edit and request-page edit start immediate bounded catch-up.
5. Measure controlled live latency against the 1-second and 5-second targets.

### Incremental Delivery

1. Ship US1 for immediate hiding and source-triggered catch-up.
2. Add US2 to make stream stalls, API failures, and warning storms visible and recoverable.
3. Add US3 to close accident windows with bounded evidence.
4. Add benchmark/resource verification and durable docs before production-readiness claims.

### Final Validation

1. Run `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1`.
2. Run `rtk cargo test --manifest-path suppressor/Cargo.toml`.
3. Run controlled bot-test-page benchmark edits only on `Удзельнік:Plaga med Bot/suppressor/tests`, with every automated edit marked as a bot edit.
4. Run low-spec daemon/TUI/catch-up/failure-storm resource checks.
5. Run `rtk python3 tools/doc_workflow.py all`.
6. Run `/speckit.analyze` before implementation starts if the plan/spec/tasks need one more consistency check.
