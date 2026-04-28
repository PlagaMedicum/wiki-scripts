---
docmeta:
  status: draft
  review: feature-local
  purpose: Actionable implementation task breakdown for real-time suppression recovery.
  source: speckit-tasks on 2026-04-28
---

# Tasks: Real-Time Suppression Recovery

**Input**: Design documents from `specs/001-real-time-suppression/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`
**Tests**: Required. The feature is latency-sensitive, recovery-sensitive, operator-safety-sensitive, and now compatibility-sensitive; test tasks precede implementation tasks in each story.

**Organization**: Tasks are grouped by user story so the urgent live-hiding path stays first, followed by realtime stall recovery and accident-window verification. The refreshed backlog preserves already completed work and incorporates the new remaining blockers from the updated plan: live-path `HTTP 429` handling, daemon-owned realtime truth, ordinary reopen or reconnect over-recovery, stuck `catching-up` convergence, compatibility-safe operator surfaces, migration diagnostics for invalid prior setup, truthful TUI log rendering, and restart verification on the actual launch path.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase because it touches different files and has no dependency on their output.
- **[Story]**: User story identifier from `spec.md`; setup, foundational, and polish tasks omit story labels.
- Every task names the exact file path it changes or validates.

## Phase 1: Setup

**Purpose**: Re-ground the work on the actual managed daemon and capture the remaining production symptoms before more code changes.

- [x] T001 Run the serialized suppressor baseline test command and record the baseline gate in `suppressor/docs/testing-strategy.md`
- [x] T002 [P] Run the repo docs workflow baseline and record the close-out gate in `specs/001-real-time-suppression/quickstart.md`
- [x] T003 [P] Audit current realtime, catch-up, API, and resource constraints and record them in `suppressor/docs/operations.md`
- [ ] T004 Recheck the actual managed daemon launch path, `suppressor/state/runtime_status.json`, and journal or supervisor evidence after restart and capture the active `HTTP 429`, live-path failure, ordinary-reopen, compatibility-surface, and daemon-status-authority symptoms in `suppressor/docs/operations.md`
- [ ] T005 [P] Measure current state-file sizes, retained unresolved detail, warning-summary growth, older-artifact behavior, one-shot command output behavior, and wrapped-row latest-follow behavior under repeated-failure or stale-artifact conditions and record the baseline in `suppressor/docs/operations.md`

---

## Phase 2: Foundational

**Purpose**: Keep shared contracts, config, typed recovery surfaces, and compatibility-safe status/report surfaces aligned before finishing the remaining user-story work.

**Critical**: User-story work depends on these shared contracts staying explicit and bounded.

- [x] T006 Add a shared MediaWiki UTC second-precision timestamp serializer for API parameters in `suppressor/src/mw_api.rs`
- [x] T007 [P] Add timestamp serialization tests for `rvstart`, coverage windows, and future API timestamp parameters in `suppressor/src/mw_api.rs`
- [x] T008 Add `ApiFailureSnapshot`, retryability, operation, and safe-message types in `suppressor/src/mw_api.rs` and `suppressor/src/state.rs`
- [x] T009 Extend `ApiFailureSnapshot` with throttle-specific fields such as `retry_after_seconds` and backoff metadata in `suppressor/src/mw_api.rs` and `suppressor/src/state.rs`
- [ ] T010 [P] Add API failure classification tests for `HTTP 429`, `Retry-After`, JSON API errors, non-JSON responses, HTTP status failures, decode failures, timeouts, and network errors in `suppressor/src/mw_api.rs`
- [x] T011 Add `SourceListRefresh`, `ResourceEconomySnapshot`, `WarningSummary`, and `BenchmarkRun` state types in `suppressor/src/state.rs`
- [x] T012 Add bounded catch-up defaults for request pages, warning samples, title-scope limits, freshness thresholds, and max windows in `suppressor/src/config.rs` and `suppressor/config.toml`
- [x] T013 Add explicit throttle backoff and unresolved-sample retention settings in `suppressor/src/config.rs` and `suppressor/config.toml`
- [x] T014 [P] Add config validation and TOML deserialization tests for throttle backoff and unresolved-sample retention in `suppressor/src/config.rs`
- [x] T015 Define catch-up request, title-scope, summary formatting, and warning-summary support in `suppressor/src/catchup.rs`
- [x] T016 [P] Add watched-title diff helpers and regression tests in `suppressor/src/cache/model.rs`
- [x] T017 Add runtime helper methods for realtime status, source-refresh status, latest errors, warning summaries, and resource summaries in `suppressor/src/runtime.rs`
- [ ] T018 [P] Add reusable synthetic recentchange, older runtime-status, older command-report, and stale supervisor-artifact fixtures in `suppressor/src/recentchange.rs` and `suppressor/tests/config_and_state.rs`

**Checkpoint**: Foundation is ready when the shared recovery/state contracts include throttle metadata, bounded retention settings, and fixtures for stream, catch-up, and compatibility-surface failures.

---

## Phase 3: User Story 1 - Hide New Sensitive Edits Immediately (Priority: P1) 🎯 MVP

**Goal**: New eligible watched-page edits are detected, queued, hidden, and reported immediately without waiting for manual refreshes or slower reconciliation.

**Independent Test**: Simulate or publish a qualifying edit on a watched page and verify it is queued immediately, hidden within the target, and recorded as a live outcome without manual reload.

### Tests for User Story 1

- [ ] T019 [P] [US1] Add live target-wiki event classification and watched-title matching tests in `suppressor/src/stream.rs`
- [ ] T020 [P] [US1] Add live dispatcher tests for immediate queueing, duplicate skips, policy skips, missing metadata, degraded live protection outcomes, and final outcome recording in `suppressor/src/runtime.rs`
- [ ] T021 [P] [US1] Add RevDel safety-boundary tests proving live hide requests target only public `user|comment` fields in `suppressor/src/worker.rs`
- [ ] T022 [P] [US1] Add observed-to-queue and observed-to-hide timing tests for successful, already-hidden, skipped, failed, retrying, throttled, blocked, and unresolved live outcomes in `suppressor/src/worker.rs`
- [ ] T023 [P] [US1] Add source-list recentchange tests that refresh `Удзельнік:Wizardist/SuppressionList`, diff newly added titles, and start immediate bounded catch-up in `suppressor/src/stream.rs`
- [ ] T024 [P] [US1] Add request-page trigger tests for `Вікіпедыя:Запыты да схавальнікаў` recent-window catch-up in `suppressor/src/stream.rs`
- [ ] T025 [P] [US1] Add TUI status tests for last observed event, matched edit, queued action, latest live outcome, successful hide, and source-refresh summary in `suppressor/src/tui_status.rs`

### Implementation for User Story 1

- [ ] T026 [US1] Extract the live recentchange handling path into testable helper logic in `suppressor/src/stream.rs`
- [ ] T027 [US1] Queue eligible live watched-page edits with observed-at, enqueued-at, source, and recovery-trigger metadata in `suppressor/src/runtime.rs`
- [x] T028 [US1] Update realtime status on stream open, target-wiki event, watched match, queued live action, and source-page event in `suppressor/src/stream.rs`
- [ ] T029 [US1] Record observed-to-queue and observed-to-hide metrics without unbounded sample growth in `suppressor/src/metrics.rs`
- [ ] T030 [US1] Persist successful live hide, already-hidden, skipped, failed, retrying, throttled, unresolved, and blocked outcomes in `suppressor/src/worker.rs`
- [ ] T031 [US1] Ensure live hiding does not wait for nightly reconciliation, current-day reconciliation, or manual cache reload in `suppressor/src/stream.rs`
- [x] T032 [US1] Implement refresh-plus-immediate-catch-up for `Удзельнік:Wizardist/SuppressionList` changes in `suppressor/src/stream.rs` and `suppressor/src/catchup.rs`
- [x] T033 [US1] Implement request-page recent-window catch-up for `Вікіпедыя:Запыты да схавальнікаў` and configured request pages in `suppressor/src/stream.rs` and `suppressor/src/catchup.rs`
- [x] T034 [US1] Persist source-refresh outcomes, title counts, catch-up scope, and safe errors in `suppressor/src/state.rs`
- [x] T035 [US1] Render live hide status and source-refresh catch-up status compactly in `suppressor/src/tui_view.rs`
- [x] T036 [US1] Update US1 quickstart verification for live hiding, source-list recovery, request-page recovery, and latency evidence in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US1 is independently complete when a controlled eligible live event and a source-list or request-page edit both trigger bounded immediate handling without manual reload or reconciliation.

---

## Phase 4: User Story 2 - Detect And Recover From Real-Time Stalls (Priority: P2)

**Goal**: A daemon that is running but not effectively observing or hiding becomes visibly unhealthy, recovers with bounded catch-up, emits compatibility or migration diagnostics when prior operator surfaces are unsafe, keeps one-shot commands from contaminating daemon truth, and handles throttling without flooding state or the TUI.

**Independent Test**: Simulate a silent stream, reconnect, ordinary reopen without a gap, invalid resume, repeated `HTTP 429` recovery failure, and stale prior operator artifacts; verify stale or throttled status, daemon-owned realtime truth, bounded backoff, compact warning summaries, and migration-needed diagnostics when previous setup assumptions are invalid.

### Tests for User Story 2

- [ ] T037 [P] [US2] Add controlled silent EventStreams starvation and watchdog transition tests in `suppressor/src/stream.rs`
- [ ] T038 [P] [US2] Add reconnect, decode-error reconnect, invalid-resume, replay, resume-gap, and ordinary-reopen-without-catch-up or false-startup-label tests in `suppressor/src/stream.rs`
- [ ] T039 [P] [US2] Add bounded API freshness-probe and stale-or-incompatible runtime-status loading tests for quiet-stream versus stale-stream lag calculation, non-healthy convergence after unresolved live failure, and safe defaults for older status shapes in `suppressor/src/mw_api.rs`, `suppressor/src/runtime.rs`, and `suppressor/tests/config_and_state.rs`
- [ ] T040 [P] [US2] Add bounded catch-up ordering, dedupe, concurrency-limit, repeated-root-cause stop-condition, and unresolved-retention tests in `suppressor/src/catchup.rs`
- [ ] T041 [P] [US2] Add `HTTP 429`, `Retry-After`, `text/plain` or HTML non-JSON, `badtimestamp`, decode, timeout, auth/session, permission, and live-versus-catch-up classification tests in `suppressor/src/mw_api.rs`
- [x] T042 [P] [US2] Add warning coalescing and bounded unresolved-sample tests with aggregate counts and safe title samples in `suppressor/src/catchup.rs`
- [ ] T043 [P] [US2] Add TUI rendering tests for healthy, stale, reconnecting, catching-up, throttled backoff, unhealthy, blocked, compatibility or migration notices, actual launch-path indicators, state convergence, latest-outcome source, daemon-vs-command status priority, and compact-priority states in `suppressor/src/tui_view.rs`
- [ ] T044 [P] [US2] Add blocked rights/session, daemon-runtime isolation, live-path throttle propagation, older-artifact diagnostics, backward-compatible command-surface, and shared rate-limit-state tests in `suppressor/src/worker.rs`, `suppressor/src/runtime.rs`, `suppressor/src/commands.rs`, and `suppressor/tests/config_and_state.rs`

### Implementation for User Story 2

- [x] T045 [US2] Add timeout or select-based watchdog handling around EventStreams reads in `suppressor/src/stream.rs`
- [x] T046 [US2] Set stale, reconnecting, catching-up, unhealthy, and blocked realtime states with explicit recovery reasons in `suppressor/src/runtime.rs`
- [ ] T047 [US2] Implement the low-cost bounded target-wiki freshness probe using recentchanges and honest health transitions in `suppressor/src/mw_api.rs` and `suppressor/src/runtime.rs`
- [ ] T048 [US2] Gate bounded catch-up triggers so true startup, reconnect gaps, silent starvation, invalid resume, and resume gaps recover while ordinary no-gap reopen and reconnect-decode noise do not rerun or relabel startup recovery in `suppressor/src/stream.rs`
- [x] T049 [US2] Implement rate-limit-aware catch-up with newest-first ordering, stop-early backoff, and bounded unresolved retention in `suppressor/src/catchup.rs`
- [ ] T050 [US2] Share throttle or degraded-protection state and compatibility-notice triggers across startup catch-up, source-triggered catch-up, manual catch-up, live-path revision lookups, reconciliation, and daemon-owned realtime or command-report surfaces in `suppressor/src/catchup.rs`, `suppressor/src/reconcile.rs`, `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, `suppressor/src/commands.rs`, and `suppressor/src/state.rs`
- [x] T051 [US2] Use the shared MediaWiki timestamp serializer for catch-up, coverage, freshness, and revision-query API parameters in `suppressor/src/mw_api.rs`
- [x] T052 [US2] Persist classified API, transport, auth/session, and source-refresh failures in realtime status without response bodies or secrets in `suppressor/src/state.rs`
- [x] T053 [US2] Replace per-page catch-up warning spam with root-cause summary aggregation in `suppressor/src/catchup.rs`
- [x] T054 [US2] Persist `retry_after_seconds`, `backoff_until`, `latest_recovery_warnings`, and recovery stop reasons in `suppressor/src/state.rs` and `suppressor/src/runtime.rs`
- [ ] T055 [US2] Surface throttle or degraded-protection state, emit compatibility or migration notices for stale prior state, stale pid or supervisor markers, and invalid launch-path assumptions, keep daemon realtime authority separate from one-shot command activity, converge stale `catching-up` state, and prioritize active realtime failure over lower-priority reconciliation noise in `suppressor/src/runtime.rs`, `suppressor/src/tui_status.rs`, `suppressor/src/tui_view.rs`, and `suppressor/src/tui.rs`
- [x] T056 [US2] Persist blocked state before fatal auth, session, or permission exits in `suppressor/src/worker.rs`
- [x] T057 [US2] Label manual cache reload and manual nightly signals as diagnostic or fallback actions in `suppressor/src/signal_control.rs`
- [x] T058 [US2] Update US2 quickstart verification for silent starvation, throttling, timestamp errors, API classification, warning coalescing, and compatibility or migration checks in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US2 is independently complete when a running-but-stale or throttled daemon cannot appear healthy, ordinary reopen or reconnect-noise events do not trigger false startup recovery, live-path throttling remains visible as degraded protection, and invalid previous setup assumptions produce one explicit migration-needed diagnostic instead of silent operator confusion.

---

## Phase 5: User Story 3 - Verify Accident-Window Coverage (Priority: P3)

**Goal**: Operators can verify a bounded accident or downtime window and see every eligible edit accounted for without exposing sensitive content.

**Independent Test**: Run accident-window coverage over a controlled window and verify all eligible edits are counted as hidden, already-hidden, skipped, failed, retrying, unresolved, or blocked with safe next actions and bounded command output that does not overwrite daemon status.

### Tests for User Story 3

- [ ] T059 [P] [US3] Add coverage-window accounting tests for hidden, already-hidden, skipped, failed, retrying, unresolved, and blocked outcomes in `suppressor/src/catchup.rs`
- [ ] T060 [P] [US3] Add emergency-catchup and coverage-report timestamp validation tests for missing timezone, inverted ranges, oversized windows, and override behavior in `suppressor/src/commands.rs`
- [ ] T061 [P] [US3] Add sensitive-output tests proving emergency and coverage reports omit hidden text, raw comments, credentials, tokens, cookies, and response bodies in `suppressor/src/commands.rs`
- [ ] T062 [P] [US3] Add TUI action and rendering tests for emergency catch-up and coverage report, including the correct `coverage-report` command wiring, labeled command-log output, backward-compatible command-report surfaces or migration notices, and wrapped-row latest-row follow behavior in `suppressor/src/tui.rs` and `suppressor/src/tui_view.rs`

### Implementation for User Story 3

- [x] T063 [US3] Implement emergency catch-up command handling and bounded default-window behavior in `suppressor/src/commands.rs`
- [x] T064 [US3] Implement coverage-report command handling with report-only and dry-run support in `suppressor/src/commands.rs`
- [x] T065 [US3] Wire emergency catch-up and coverage-report CLI variants through `suppressor/src/cli.rs` and `suppressor/src/app.rs`
- [ ] T066 [US3] Tighten command-side window validation, max-scope override behavior, and clearer operator errors in `suppressor/src/commands.rs` and `suppressor/src/cli.rs`
- [x] T067 [US3] Fix TUI coverage-report action wiring, separate daemon and one-shot command log sources, and make latest-mode log following row-accurate or explicitly non-wrapping in `suppressor/src/tui.rs`
- [ ] T068 [US3] Render coverage progress, outcome counts, unresolved totals, compatibility or migration notice, and next action compactly in `suppressor/src/tui_view.rs`
- [ ] T069 [US3] Persist latest emergency catch-up and coverage summary counts with bounded unresolved detail in a backward-compatible command-report surface that emits a migration notice when the previous shape is invalid and does not overwrite daemon realtime status or latest live outcome truth in `suppressor/src/state.rs` and `suppressor/src/runtime.rs`
- [ ] T070 [US3] Format unresolved report items with title, revision ID, age, reason, and next action while omitting sensitive payloads in `suppressor/src/catchup.rs` and `suppressor/src/commands.rs`
- [x] T071 [US3] Update US3 quickstart examples and release interpretation for emergency catch-up and coverage report in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: US3 is independently complete when the operator can close or escalate an accident window from bounded evidence rather than from reconciliation assumptions or mixed daemon-command status.

---

## Phase 6: Polish, Benchmark, Resource Economy, Documentation, And Release Readiness

**Purpose**: Close the production-readiness gap with benchmark evidence, low-spec verification, compatibility or migration release evidence, restart validation, and durable docs.

- [ ] T072 [P] Add bot-test-page benchmark validation tests for allow-listing, bot edit markers, run labels, safe content, smoke-mode samples, and no source-list mutation in `suppressor/src/commands.rs`
- [ ] T073 Implement the production-safe benchmark command for `Удзельнік:Plaga med Bot/suppressor/tests` in `suppressor/src/commands.rs`
- [ ] T074 Wire benchmark CLI and optional TUI entrypoints with safe defaults in `suppressor/src/cli.rs`, `suppressor/src/app.rs`, and `suppressor/src/tui.rs`
- [ ] T075 Record publish-to-detect, detect-to-queue, queue-to-hide, publish-to-hidden, p50, p95, p99, and smoke-only evidence without unbounded samples in `suppressor/src/metrics.rs`
- [ ] T076 [P] Add resource-economy verification tests or dry-run checks for queue depth, API concurrency, state-file retention, unresolved-sample retention, benchmark sample retention, and warning aggregation in `suppressor/tests/config_and_state.rs`
- [ ] T077 Implement resource-economy verification command output for CPU, memory, queue depth, API concurrency, state file sizes, log volume, and warning coalescing in `suppressor/src/commands.rs`
- [ ] T078 Wire resource-economy verification CLI and optional TUI entrypoints in `suppressor/src/cli.rs`, `suppressor/src/app.rs`, and `suppressor/src/tui.rs`
- [ ] T079 [P] Update operator-facing command and realtime behavior, compatibility-safe status surfaces, and actual verification path guidance in `suppressor/README.md`
- [ ] T080 [P] Update production operations guidance for throttling, backoff, actual launch-path verification, daemon-vs-command status authority, compatibility or migration diagnostics, low-spec evidence, and release stop conditions in `suppressor/docs/operations.md`
- [x] T081 [P] Update implementation notes for internal service boundaries, timestamp serialization, source-refresh catch-up, API classification, and bounded warnings in `suppressor/docs/implementation.md`
- [x] T082 [P] Update runtime-boundary notes for new state fields, retention bounds, status compatibility, and safe payload rules in `suppressor/docs/runtime-boundaries.md`
- [ ] T083 [P] Update testing strategy with throttling, freshness probing, source-trigger recovery, daemon-runtime isolation, ordinary-reopen gating, compatibility fixtures, invalid-launch-path checks, TUI latest-row behavior, benchmark safety, and managed-daemon restart checks in `suppressor/docs/testing-strategy.md`
- [x] T084 Run `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` and record the gate result in `suppressor/docs/testing-strategy.md`
- [x] T085 Run `rtk cargo test --manifest-path suppressor/Cargo.toml` and record any remaining parallel-test limits in `suppressor/docs/testing-strategy.md`
- [ ] T086 Restart the managed daemon through the actual launch path, recheck the live TUI plus journal or supervisor output and `suppressor/state/runtime_status.json`, and record the live-schema plus compatibility-surface verification in `suppressor/docs/operations.md`
- [ ] T087 Run the controlled bot-test-page benchmark and record timing evidence, sample-size limits, and unresolved items in `suppressor/docs/operations.md`
- [ ] T088 Run low-spec resource verification for daemon, TUI, catch-up, source-refresh catch-up, benchmark, and repeated-failure scenarios and record the evidence in `suppressor/docs/operations.md`
- [x] T089 Run `rtk python3 tools/doc_workflow.py all` and record the docs gate result in `specs/001-real-time-suppression/quickstart.md`
- [ ] T090 Run the final quickstart production-readiness and compatibility or migration checks against the actual deployment path and record any unavailable external wiki checks or narrower confidence claims in `specs/001-real-time-suppression/quickstart.md`
- [ ] T091 Copy durable incident lessons from feature-local artifacts into maintained suppressor docs, including daemon-runtime authority, stream-reopen gating, TUI log truthfulness, the post-publication visibility limit, and compatibility or migration warning rules, in `suppressor/docs/implementation.md`, `suppressor/docs/operations.md`, and `suppressor/docs/testing-strategy.md`
- [ ] T092 Evaluate whether the suppressor compatibility or migration-warning pattern should be generalized and, if it is reusable beyond suppressor, copy the rule into `specs/000-repo-governance/research.md`

---

## Dependencies And Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; re-ground the work on the managed daemon before more implementation.
- **Foundational (Phase 2)**: Depends on Setup and keeps shared recovery, state, and compatibility contracts consistent.
- **US1 (Phase 3)**: Depends on Foundational and remains the urgent realtime protection path.
- **US2 (Phase 4)**: Depends on Foundational and is now the primary residual production blocker because throttled recovery, stale-state convergence, and compatibility diagnostics are still incomplete.
- **US3 (Phase 5)**: Depends on Foundational and reuses catch-up and outcome models from US1 and US2.
- **Polish (Phase 6)**: Depends on completed user-story behavior and closes the release-evidence gap.

### User Story Dependencies

- **US1 (P1)**: Finish the remaining live-path tests, queueing, and outcome persistence first.
- **US2 (P2)**: Finish next; throttling across live and catch-up paths, freshness probing, state convergence, daemon-owned realtime truth, invalid-prior-setup diagnostics, and reopen gating are required for reliable production recovery.
- **US3 (P3)**: Finish after US2; it depends on the catch-up and runtime accounting surfaces being trustworthy and compatibility-safe.

### Within Each User Story

- Write or update the tests first and confirm they fail against the current behavior.
- Implement the smallest code path that makes the story tests pass.
- Keep queues, concurrency, retained state, warning output, command-report surfaces, and benchmark samples bounded.
- Verify the story independently before moving to the next story.

### Parallel Opportunities

- Setup tasks T004 and T005 can run in parallel once the managed daemon restart path is agreed.
- Foundational tasks T010, T014, and T018 can run in parallel across API, config, and fixture surfaces.
- US1 tests T019 through T025 can run in parallel across stream, runtime, worker, and TUI status surfaces.
- US2 tests T037 through T044 can run in parallel across stream, API, catch-up, worker, runtime, command, and TUI surfaces, with T039, T043, and T044 especially useful for proving the April 28 compatibility and state-convergence findings.
- US3 tests T059 through T062 can run in parallel across catch-up, commands, and TUI surfaces.
- Documentation tasks T079 through T083 can run in parallel after command names, runtime fields, and compatibility behavior stabilize.

---

## Parallel Example: User Story 1

```bash
Task: "T019 [US1] Add live target-wiki event classification and watched-title matching tests in suppressor/src/stream.rs"
Task: "T020 [US1] Add live dispatcher tests for immediate queueing, duplicate skips, policy skips, missing metadata, degraded live protection outcomes, and final outcome recording in suppressor/src/runtime.rs"
Task: "T021 [US1] Add RevDel safety-boundary tests proving live hide requests target only public user|comment fields in suppressor/src/worker.rs"
Task: "T025 [US1] Add TUI status tests for last observed event, matched edit, queued action, latest live outcome, successful hide, and source-refresh summary in suppressor/src/tui_status.rs"
```

## Parallel Example: User Story 2

```bash
Task: "T037 [US2] Add controlled silent EventStreams starvation and watchdog transition tests in suppressor/src/stream.rs"
Task: "T039 [US2] Add bounded API freshness-probe and stale-or-incompatible runtime-status loading tests in suppressor/src/mw_api.rs, suppressor/src/runtime.rs, and suppressor/tests/config_and_state.rs"
Task: "T040 [US2] Add bounded catch-up ordering, dedupe, concurrency-limit, repeated-root-cause stop-condition, and unresolved-retention tests in suppressor/src/catchup.rs"
Task: "T043 [US2] Add TUI rendering tests for healthy, stale, reconnecting, catching-up, throttled backoff, unhealthy, blocked, compatibility or migration notices, actual launch-path indicators, state convergence, latest-outcome source, daemon-vs-command status priority, and compact-priority states in suppressor/src/tui_view.rs"
```

## Parallel Example: User Story 3

```bash
Task: "T059 [US3] Add coverage-window accounting tests for hidden, already-hidden, skipped, failed, retrying, unresolved, and blocked outcomes in suppressor/src/catchup.rs"
Task: "T060 [US3] Add emergency-catchup and coverage-report timestamp validation tests for missing timezone, inverted ranges, oversized windows, and override behavior in suppressor/src/commands.rs"
Task: "T061 [US3] Add sensitive-output tests proving emergency and coverage reports omit hidden text, raw comments, credentials, tokens, cookies, and response bodies in suppressor/src/commands.rs"
Task: "T062 [US3] Add TUI action and rendering tests for emergency catch-up and coverage report, including the correct coverage-report command wiring, labeled command-log output, backward-compatible command-report surfaces or migration notices, and wrapped-row latest-row follow behavior in suppressor/src/tui.rs and suppressor/src/tui_view.rs"
```

---

## Implementation Strategy

### MVP First

1. Complete the remaining US1 work for immediate live handling.
2. Immediately follow with the US2 freshness, reopen-gating, live-throttle, daemon-truth, compatibility-diagnostic, and state-convergence subset: T038 through T055.
3. Validate the managed daemon after restart before treating the fix as production-ready.

### Incremental Delivery

1. Setup plus Foundational: confirm the managed daemon symptoms and shared contracts.
2. Finish US1: immediate live hiding and source-triggered catch-up.
3. Finish US2: honest stale or throttled status, bounded recovery, and explicit compatibility or migration diagnostics.
4. Finish US3: bounded operator evidence for accident windows.
5. Finish Polish: benchmark, low-spec checks, restart verification, compatibility-safe docs, and durable lessons.

### Final Validation

1. Run `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1`.
2. Run `rtk cargo test --manifest-path suppressor/Cargo.toml`.
3. Restart the managed daemon through the actual launch path and verify the live TUI, journal or supervisor output, `runtime_status.json`, and any bounded command-report surface.
4. Run controlled bot-test-page benchmark edits only on `Удзельнік:Plaga med Bot/suppressor/tests`, with every automated edit marked as a bot edit.
5. Run low-spec daemon, TUI, catch-up, and failure-storm resource checks.
6. Run `rtk python3 tools/doc_workflow.py all`.
