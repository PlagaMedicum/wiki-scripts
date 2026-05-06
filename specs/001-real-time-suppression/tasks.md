---
docmeta:
  status: draft
  review: feature-local
  purpose: Remaining actionable task breakdown for the suppressor MVP stabilization freeze.
  source:
  - speckit-tasks regeneration on 2026-05-05
  - speckit-tasks server-start update on 2026-05-05
  - speckit-tasks config-stability update on 2026-05-06
  - speckit-tasks Q001 launch-evidence update on 2026-05-07
---

# Tasks: Real-Time Suppression Recovery

**Input**: Design documents from `specs/001-real-time-suppression/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`,
`quickstart.md`, `questions.md`, `review-queue.md`

**Tests**: Required. This is a human-safety-critical daemon feature. The tasks below track remaining
MVP stabilization work only; earlier checked-off implementation work is provisional until verified
through tests, the server build, `server-start`, and the actual launch path.

**Organization**: Tasks are ordered to stabilize the minimal server-runnable daemon first:
automatic live hiding, recovery/reconciliation/nightly fallback, truthful degraded status,
`server-start`, command surface separation, `make build-server`, and actual launch-path evidence.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel because it touches different files and does not depend on incomplete
  tasks in the same phase.
- **[Story]**: User story identifier from `spec.md`.
- Every task names exact file paths.

## Task Completion And Evidence Freshness Rules

- A task may be checked only when the named files are updated, required verification for that task
  has run, and the evidence is recorded in `specs/001-real-time-suppression/quickstart.md` when the
  task is evidence-bearing.
- Phase 2 is a hard trust dependency. US1, US2, and US3 work may be investigated or patched only as
  needed, but their tasks must not be marked complete or used for production trust until T005
  through T011 are complete and the relevant targeted tests pass.
- T037 and T038 are final MVP evidence tasks, not permanent checkmarks from an earlier source tree.
  Any later daemon-critical edit to `suppressor/src/`, `suppressor/tests/`,
  `suppressor/Cargo.toml`, `suppressor/Cargo.lock`, `suppressor/Makefile`, or launch/build code
  expires the previous serial-test or server-build result. Local snapshots may stay documented, but
  T037 and T038 stay unchecked until they are rerun after Phase 2, US1, and US2 daemon-critical
  changes are complete.
- Config changes are release-blocking operator-contract changes. Do not edit tracked config,
  target-host config, config schema, defaults, environment variable names, loading semantics, or
  deployment-required sections unless the task records the motivation, explicit human review,
  compatibility or migration behavior, rollback/fallback, and target-host verification evidence.
- Q001 is answered: the human owner approved path 1, target-host config migration to the reviewed
  tracked baseline. T040 is now blocked only on non-secret post-migration launch evidence, not on
  another config policy decision.

## Phase 1: Setup

**Purpose**: Freeze scope, preserve current work, and prepare the rsync-ready server artifact plus
one-command detached server launch path.

- [X] T001 Capture the current dirty suppressor implementation baseline and provisional-completion warning in `specs/001-real-time-suppression/quickstart.md`
- [X] T002 Verify the additive `build-server` Makefile target by running `make -C suppressor -n build-server` and recording the expected artifact path in `specs/001-real-time-suppression/quickstart.md`
- [X] T003 Verify whether `cargo-zigbuild` and `zig` are installed for the real `make build-server` command and record missing prerequisites in `specs/001-real-time-suppression/quickstart.md`
- [X] T004 Record the planned `server-start` launch receipt, safe failure modes, and launch-path evidence requirements in `specs/001-real-time-suppression/quickstart.md`

---

## Phase 2: Foundational

**Purpose**: Re-establish daemon invariants that block every story: live work must not starve,
status must not lie, scheduled work must be bounded, and the deployed binary must start detached
with truthful PID/status/log evidence.

**Critical**: No user story work can be trusted until this phase is complete.

- [X] T005 [P] Add or repair a shared throttle/backoff contract test covering live hiding, catch-up, reconciliation, and one-shot command callers in `suppressor/tests/config_and_state.rs`
- [X] T006 [P] Add or repair stale PID and stale `runtime_status.json` compatibility tests that must produce non-healthy status in `suppressor/tests/config_and_state.rs` and `suppressor/src/tui_status.rs`
- [X] T007 [P] Add or repair `server-start` CLI parsing, preflight, duplicate live daemon, stale PID, detached child, log redirection, and startup-timeout tests in `suppressor/src/cli.rs`, `suppressor/src/commands.rs`, `suppressor/src/app.rs`, and `suppressor/src/tui_status.rs`
- [X] T008 [P] Add or repair scheduler overlap tests proving rolling last-24h verification and nightly full recheck cannot block live hiding in `suppressor/src/scheduler.rs` and `suppressor/src/reconcile.rs`
- [X] T009 Implement the minimum shared throttle/backoff state needed by live hiding, catch-up, reconciliation, and command reports in `suppressor/src/state.rs`, `suppressor/src/runtime.rs`, `suppressor/src/catchup.rs`, `suppressor/src/reconcile.rs`, and `suppressor/src/commands.rs`
- [X] T010 Implement the additive `server-start` detached launch command, non-sensitive launch receipt, log redirection, startup wait, and safe-failure behavior in `suppressor/src/cli.rs`, `suppressor/src/app.rs`, `suppressor/src/commands.rs`, `suppressor/src/config.rs`, `suppressor/src/state.rs`, and `suppressor/src/runtime.rs`
- [X] T011 Ensure runtime status derives non-healthy or degraded protection when backoff, stale runtime, failed scheduled verification, stale full-recheck evidence, or invalid launch-path evidence is active in `suppressor/src/runtime.rs` and `suppressor/src/tui_status.rs`

**Checkpoint**: Live hiding can remain independent from slower work, blocked or stale evidence
cannot appear healthy, and the deployed binary has a verified detached launch path.

---

## Phase 3: User Story 1 - Hide New Sensitive Edits Immediately (Priority: P1)

**Goal**: Eligible watched-page edits are detected, queued, hidden or dry-run recorded, and surfaced
without waiting for manual refreshes or scheduled reconciliation.

**Independent Test**: Simulate or publish one watched eligible edit while the daemon is running and
confirm immediate queueing, hide or dry-run outcome, `last_successful_hide_at` or dry-run outcome
update, and operator status update.

### Tests for User Story 1

- [X] T012 [P] [US1] Add or repair watched recentchange-to-live-queue tests in `suppressor/src/stream.rs` and `suppressor/src/recentchange.rs`
- [X] T013 [P] [US1] Add or repair live worker outcome tests for hidden, already-hidden, skipped, retrying, and blocked states in `suppressor/src/worker.rs` and `suppressor/src/runtime.rs`
- [X] T014 [P] [US1] Add or repair live latency and bounded metrics tests for observed-to-queue and queue-to-hide evidence in `suppressor/src/metrics.rs` and `suppressor/src/runtime.rs`

### Implementation for User Story 1

- [X] T015 [US1] Ensure live recentchange dispatch bypasses scheduled reconciliation queues and remains bounded in `suppressor/src/stream.rs`, `suppressor/src/worker.rs`, and `suppressor/src/runtime.rs`
- [X] T016 [US1] Ensure successful live hides and dry-run live outcomes persist safe revision URLs, final outcome source, and recovery anchors in `suppressor/src/worker.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/state.rs`
- [X] T017 [US1] Ensure source-list and request-page changes trigger immediate bounded catch-up without manual reload in `suppressor/src/stream.rs`, `suppressor/src/cache/source.rs`, and `suppressor/src/catchup.rs`
- [X] T018 [US1] Ensure the primary status surface shows last observed watched edit, queued live action, last successful hide, latest live issue, and current launch path in `suppressor/src/tui_status.rs` and `suppressor/src/tui_view.rs`
- [X] T019 [US1] Run targeted live-path tests and record the result in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: A new watched edit is handled by the daemon live path without manual action or
waiting for nightly reconciliation.

---

## Phase 4: User Story 2 - Detect And Recover From Real-Time Stalls (Priority: P2)

**Goal**: Stale, gapped, throttled, or ineffective protection becomes visibly non-healthy, recovery
starts from the last successful hide, and daytime/nightly verification remains truthful and bounded.

**Independent Test**: Simulate stream stall, reconnect noise, true gap, API 429, failed scheduled
verification, and stale checkpoint evidence; confirm recovery scope, bounded backoff, and degraded
status remain visible until real recovery or verification clears them.

### Tests for User Story 2

- [X] T020 [P] [US2] Add or repair recovery-anchor tests for `last_successful_hide_at`, fallback-anchor reporting, and no arbitrary recent-window truncation in `suppressor/src/catchup.rs` and `suppressor/src/runtime.rs`
- [X] T021 [P] [US2] Add or repair stream transition tests for startup recovery, ordinary reopen, reconnect noise, and true gap recovery in `suppressor/src/stream.rs`
- [X] T022 [P] [US2] Add or repair scheduled verification tests for rolling last-24h daytime windows, randomized nightly full recheck, and overlap behavior in `suppressor/src/scheduler.rs` and `suppressor/src/reconcile.rs`
- [X] T023 [P] [US2] Add or repair TUI/status derivation tests for degraded protection, failed verification visibility, stale full-recheck freshness, launch-path truth, and command-vs-daemon truth in `suppressor/src/tui_status.rs`, `suppressor/src/tui_view.rs`, and `suppressor/src/runtime.rs`

### Implementation for User Story 2

- [X] T024 [US2] Implement or repair automatic recovery from `last_successful_hide_at` with explicit fallback-anchor status in `suppressor/src/catchup.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/stream.rs`
- [X] T025 [US2] Implement or repair rolling last-24h daytime verification and randomized nightly full recheck scheduling with exact scope labels in `suppressor/src/scheduler.rs`, `suppressor/src/reconcile.rs`, and `suppressor/src/config.rs`
- [X] T026 [US2] Ensure repeated API failures coalesce into bounded warning summaries with retry/backoff visibility in `suppressor/src/mw_api.rs`, `suppressor/src/catchup.rs`, `suppressor/src/reconcile.rs`, and `suppressor/src/runtime.rs`
- [X] T027 [US2] Ensure stream reopen cannot clear degraded live protection, failed scheduled verification, stale full-recheck evidence, or invalid launch-path evidence before successful verification clears it in `suppressor/src/stream.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/tui_status.rs`
- [X] T028 [US2] Run targeted recovery, scheduler, backoff, and status tests and record the result in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: A running daemon cannot look healthy when live hiding, recovery, reconciliation,
nightly fallback, launch-path evidence, or throttled work is blocked, stale, or unresolved.

---

## Phase 5: User Story 3 - Verify Accident-Window Coverage (Priority: P3)

**Goal**: Operators can run useful emergency catch-up and coverage checks with clear windows,
bounded reports, direct revision links, and no confusion with daemon-owned realtime truth.

**Independent Test**: Run emergency catch-up and `Last 24 hours` coverage from CLI or TUI and
confirm exact window labels, bounded command report, safe revision links, unresolved next actions,
and unchanged daemon-owned realtime status.

### Tests for User Story 3

- [X] T029 [P] [US3] Add or repair command tests for anchor-based emergency catch-up defaults and explicit `Last 24 hours` preset labeling in `suppressor/src/commands.rs`
- [X] T030 [P] [US3] Add or repair command-report compatibility and bounded unresolved-list tests in `suppressor/src/state.rs` and `suppressor/src/commands.rs`
- [X] T031 [P] [US3] Add or repair TUI action and log separation tests for reload watched pages, refresh status, command output, and daemon output in `suppressor/src/tui.rs` and `suppressor/src/tui_view.rs`

### Implementation for User Story 3

- [X] T032 [US3] Ensure emergency catch-up defaults to the active recovery anchor when available and otherwise uses the bounded recent window in `suppressor/src/commands.rs` and `suppressor/src/runtime.rs`
- [X] T033 [US3] Ensure the `Last 24 hours` preset is wired through CLI, app, commands, and TUI without requiring timestamp input in `suppressor/src/cli.rs`, `suppressor/src/app.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui.rs`
- [X] T034 [US3] Ensure one-shot command reports stay bounded, compatible, and visibly separate from daemon truth in `suppressor/src/state.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui_status.rs`
- [X] T035 [US3] Ensure safe revision URLs and unresolved next actions render in catch-up, coverage, and TUI report surfaces in `suppressor/src/catchup.rs`, `suppressor/src/commands.rs`, and `suppressor/src/tui_view.rs`
- [X] T036 [US3] Run targeted command and TUI report tests and record the result in `specs/001-real-time-suppression/quickstart.md`

**Checkpoint**: Operator commands provide useful bounded evidence without impersonating daemon
health.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete only the release evidence required by the active suppressor MVP freeze.

- [X] T037 After Phase 2, US1, and US2 daemon-critical changes are complete, rerun `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` and fix MVP regressions in `suppressor/src/stream.rs`, `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, `suppressor/src/catchup.rs`, `suppressor/src/reconcile.rs`, `suppressor/src/tui_status.rs`, `suppressor/tests/config_and_state.rs`, and `suppressor/tests/api_integration.rs`
- [X] T038 After the T037-valid source tree and any build-input edits are complete, rerun `make -C suppressor build-server` and record either the built artifact path or missing local prerequisite in `specs/001-real-time-suppression/quickstart.md`
- [X] T039 Resolve the config-stability gate for the target-host `missing field realtime` failure by recording the reviewed config baseline or documented divergence, non-secret `print-effective-config` result or config/migration-needed diagnostic, explicit human review evidence, compatibility or migration decision, rollback/fallback path, and no-background-config-edit confirmation in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`
- [ ] T040 Verify the actual launch path after the Q001-approved path 1 target-host config migration with the built binary, `server-start` where rsync deployment is used, the non-secret `server-start` receipt, PID/runtime/log paths, daemon-owned status freshness, terminal logout survival, and no-secret migration evidence in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`
- [ ] T041 Run a controlled live or dry-run watched-edit smoke check and record live hiding or dry-run outcome evidence in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`
- [ ] T042 Measure at least 10 minutes of idle daemon-alone and daemon-plus-TUI CPU/RSS, one active live/recovery/backoff sample, live and recovery/reconciliation queue depths versus caps, API concurrency, state/report file sizes, detached log growth rate, and coalesced-warning counts on the deployment host; record pass/fail against SC-011 bounds in `suppressor/docs/operations.md`
- [X] T043 Update operator and runtime docs with the MVP launch path, `make build-server`, `server-start`, recovery anchor, rolling last-24h verification, nightly full recheck, config-stability review, and degraded-status meanings in `suppressor/README.md`, `suppressor/docs/operations.md`, and `suppressor/docs/runtime-boundaries.md`
- [X] T044 Update implementation and testing docs with the shared backoff contract, scheduler semantics, timestamp formatting lesson, detached server-start launch checks, config-stability review gate, and minimum server verification path in `suppressor/docs/implementation.md` and `suppressor/docs/testing-strategy.md`
- [X] T045 Run `rtk python3 tools/doc_workflow.py all` and record the result or the known inactive-`002` metadata blocker in `specs/001-real-time-suppression/quickstart.md`
- [X] T046 Produce the final MVP go/no-go checklist with explicit accept, block, and rollback decisions for test, build, config-stability, detached server-start launch, live-hide, recovery, reconciliation, nightly, backoff, deployment-host resource, and fallback evidence in `specs/001-real-time-suppression/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. Establishes the current baseline, server-build path, and
  detached server-start evidence contract.
- **Foundational (Phase 2)**: Depends on Setup and blocks all stories because shared backoff,
  runtime truth, bounded scheduler behavior, and detached launch correctness determine daemon
  safety.
- **User Story 1 (Phase 3)**: Depends on Foundational and is the first live-protection MVP slice.
- **User Story 2 (Phase 4)**: Depends on Foundational and must complete before production trust
  because stale, throttled, or launch-path-broken protection cannot appear healthy.
- **User Story 3 (Phase 5)**: Depends on Foundational and can proceed after US1 live-path evidence
  is stable.
- **Polish (Phase 6)**: Depends on US1, US2, and `server-start` for MVP release; US3 is required
  before treating command/coverage surfaces as safe.

### User Story Dependencies

- **US1 (P1)**: First daemon MVP slice; complete before deployment trust.
- **US2 (P2)**: Production-trust slice; complete before claiming stable daemon operation.
- **US3 (P3)**: Operator-command evidence slice; complete before relying on catch-up/coverage
  commands during incidents.

### Parallel Opportunities

- T005, T006, T007, and T008 can run in parallel across different foundational test surfaces.
- T012, T013, and T014 can run in parallel for US1 tests.
- T020, T021, T022, and T023 can run in parallel for US2 tests.
- T029, T030, and T031 can run in parallel for US3 tests.
- T043 and T044 can run in parallel after code behavior stabilizes.

---

## Parallel Example: User Story 1

```text
Task: "T012 [P] [US1] Add or repair watched recentchange-to-live-queue tests in suppressor/src/stream.rs and suppressor/src/recentchange.rs"
Task: "T013 [P] [US1] Add or repair live worker outcome tests for hidden, already-hidden, skipped, retrying, and blocked states in suppressor/src/worker.rs and suppressor/src/runtime.rs"
Task: "T014 [P] [US1] Add or repair live latency and bounded metrics tests for observed-to-queue and queue-to-hide evidence in suppressor/src/metrics.rs and suppressor/src/runtime.rs"
```

## Parallel Example: User Story 2

```text
Task: "T020 [P] [US2] Add or repair recovery-anchor tests for last_successful_hide_at, fallback-anchor reporting, and no arbitrary recent-window truncation in suppressor/src/catchup.rs and suppressor/src/runtime.rs"
Task: "T022 [P] [US2] Add or repair scheduled verification tests for rolling last-24h daytime windows, randomized nightly full recheck, and overlap behavior in suppressor/src/scheduler.rs and suppressor/src/reconcile.rs"
Task: "T023 [P] [US2] Add or repair TUI/status derivation tests for degraded protection, failed verification visibility, stale full-recheck freshness, launch-path truth, and command-vs-daemon truth in suppressor/src/tui_status.rs, suppressor/src/tui_view.rs, and suppressor/src/runtime.rs"
```

## Parallel Example: User Story 3

```text
Task: "T029 [P] [US3] Add or repair command tests for anchor-based emergency catch-up defaults and explicit Last 24 hours preset labeling in suppressor/src/commands.rs"
Task: "T030 [P] [US3] Add or repair command-report compatibility and bounded unresolved-list tests in suppressor/src/state.rs and suppressor/src/commands.rs"
Task: "T031 [P] [US3] Add or repair TUI action and log separation tests for reload watched pages, refresh status, command output, and daemon output in suppressor/src/tui.rs and suppressor/src/tui_view.rs"
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 live daemon path.
3. Complete US2 recovery/reconciliation/nightly truth.
4. Run the shortest suppressor test gate.
5. Build the server artifact with `make -C suppressor build-server`.
6. Treat the config-stability gate as Q001-approved path 1 and record post-migration T040 evidence.
7. Verify the actual launch path with `server-start` where rsync deployment is used, then run one
   controlled live or dry-run watched edit and the deployment-host resource sample.
8. Keep US3 command/report hardening and final docs evidence closed only if they remain consistent
   with the config-stability and deployment evidence.

### Suggested MVP Scope

The active safety-freeze MVP is Phase 1 + Phase 2 + US1 + US2 + T037 through T042. US3 and T043
through T046 are required before broader operator-command trust or feature close-out.

### Guardrails

- Do not start unrelated `biblio`, inactive `002`, broad docs, new service, or cosmetic TUI work.
- Do not treat checked tasks or generated text as release evidence.
- Do not log sensitive article content, hidden text, cookies, tokens, credentials, or `.env`
  values.
- Do not let reconciliation, catch-up, scheduled verification, or detached launch checks starve live
  hiding.
- Do not make further target-host or tracked config changes as a shortcut around T040 evidence.
