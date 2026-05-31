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
  - live-hide incident update with sensitive identifiers redacted
  - speckit-tasks live-hotfix decomposition with synthetic regression fixtures
  - speckit-tasks server-running launch-path mismatch update on 2026-05-07
  - speckit-tasks live-priority latency update on 2026-05-09
  - speckit-tasks live-latency clarification update on 2026-05-09
  - speckit-tasks rsynced crash evidence update on 2026-05-13
  - speckit-tasks deployment-identity update on 2026-05-14
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
`server-start`, command surface separation, live/background execution lanes, crash-resilient
runtime behavior, candidate-first recovery, `make build-server`, and actual launch-path evidence.

## Active Emergency Scope Freeze

The active `001` gate is the minimal stable suppressor server only:

- fast automatic hiding of new watched sensitive-page edits
- bounded catch-up from the last trusted hide anchor after downtime or failure
- randomized daytime last-24-hours rechecks and nightly full rechecks
- truthful degraded or blocked runtime status
- exact deployment proof for the running target-host binary

The following are out of scope until current-binary target-host smoke passes:

- TUI polish beyond truthful protection state
- broad reporting or diagnostic-surface growth
- repo-wide Spec Kit template or docs-workflow repair
- inactive-feature work such as `002-fix-git-commit`
- speculative architecture work not needed for live protection

Open work that matters for restoring protection now is T040, T041, and T052. T042 is follow-up
resource evidence only after those three prove the current binary on the target host.

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
  tracked baseline. The 2026-05-13 rsynced bundle shows reviewed `[realtime]` config plus
  `server-start` PID/runtime/log alignment, so T040 is now blocked only on logout-survival evidence
  and concise non-secret recording, not on another config policy decision.
- The operator-provided screenshot is failed T041 evidence. Use T040 only for the minimal non-secret
  server status needed to identify the running daemon; then fix T041 live hiding before
  spending time on T042 resource samples or broader close-out.
- A live server process with aligned launch-path, PID-file, runtime-status, and detached-log
  evidence can advance T040, but it does not prove T052 when the runtime status is `unhealthy` or
  lacks current lane/latency fields, or when the run is missing the safe artifact identity tuple
  and same-run current status shape required by the updated deployment proof. Do not stop a
  possibly protective daemon only to make evidence cleaner; deploy a rebuilt current binary before
  target-host smoke.
- T047 through T052 are the active live-hide hotfix slice that decomposes failed T041 evidence into
  immediate protection, regression, smallest code fix, rebuild, relaunch, and smoke proof. They
  block T042 resource sampling and production trust.
- T053 through T066 are the active live-priority latency slice. They must keep reconciliation,
  catch-up, verification, and one-shot work parallel to live recentchange processing inside the
  existing daemon, add timing tests, and remain code-only unless a separate human-reviewed config
  decision is opened. They must not introduce a fixed internal live-worker handoff SLA; the tests
  should prove live work does not wait for background drain and should record timing observations
  against SC-001 release evidence. They block T052 target-host smoke, T042 resource sampling, and
  production trust. After any T058 through T063 daemon-critical edit, previous T037, T038, or T051
  evidence is historical only; T064 and T065 become the fresh local test/build gate for the
  lane-aware tree.
- T067 through T077 are the rsynced crash-evidence and KISS recovery slice. They must remove
  process exit on classified RevDel auth/permission failure, keep stream cursor/state persistence
  failures from permanently killing live monitoring, add candidate-first recovery before ordinary
  full watched-set scans, and refresh local serial-test/server-build evidence.
- As of the 2026-05-14 local hotfix tree, authoritative live detection is recentchanges polling.
  Completed tasks that still reference `stream.rs`, EventStreams reopen behavior, or stream cursor
  compatibility are historical implementation slices or retained observer-compatibility work, not a
  requirement to restore EventStreams-first healthy-state truth.
- T052 and T042 remain blocked until T040 logout-survival evidence is recorded and T067 through
  T076 have produced a rebuilt current binary whose target-host launch can be tied to a safe
  artifact identity tuple and same-run current status shape, or an explicit human go/no-go
  exception records the accepted risk.
- A task does not count as production-trust evidence if it proves only process liveness, only
  receipt or PID alignment, or only a stale replayed hide while the daemon remains behind the
  current event head.

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
- [ ] T040 Record the rsynced partial T040 evidence from the Q001-approved target-host config migration: reviewed `[realtime]` config, `server-start` receipt plus expected binary path, PID/runtime/log alignment, daemon-owned status freshness, and no-secret safe fields, then finish the remaining SSH logout-survival check without raw logs, credentials, or sensitive incident identifiers in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`
- [ ] T041 Preserve protection for the operator-reported visible watched edit when a revision ID is known by manual hide or `emergency-catchup`, capture only the non-secret live-path facts needed to locate the failure boundary, keep any real revision identifier out of tracked files, and record the redacted incident target class, redacted outcome/status, processed-revid/cache observations, and immediate operator action in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`

## Phase 6a: Live-Hide Incident Hotfix

**Purpose**: Fix the active watched sensitive-edit live path before resource sampling or broader
close-out. Do not change config shape or deployment-required config keys in this phase, and do not
store real page, actor, revision, diff URL, comment, screenshot, or log identifiers in tracked docs,
tests, contracts, examples, fixtures, or code comments.

- [X] T047 [US1] Add a regression proving a synthetic watched sensitive-page recentchange by a synthetic operator-account actor dispatches as a live watched revision and is not filtered as own-account, bot, or non-watched noise in `suppressor/src/stream.rs` and `suppressor/src/recentchange.rs`
- [X] T048 [US1] Add a regression or diagnostic covering processed-revision and live-queue handoff for the visible incident revision so an unprocessed watched revid cannot be skipped silently and duplicate or already-processed skips are surfaced in `suppressor/src/stream.rs` and `suppressor/src/runtime.rs`
- [X] T049 [US1] Implement the smallest code fix for the first failing live-path boundary found by T041, T047, and T048 without changing config shape or deployment-required config keys in `suppressor/src/stream.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/worker.rs`
- [X] T050 [US1] Run the targeted live dispatch, queue handoff, and worker regression tests after T049 and record commands, pass/fail result, and any remaining blocker in `specs/001-real-time-suppression/quickstart.md`
- [X] T051 Rebuild the server artifact after the live-path code fix with `make -C suppressor build-server` using the `build-server` target in `suppressor/Makefile` and record the artifact path or local prerequisite blocker in `specs/001-real-time-suppression/quickstart.md`
- [ ] T052 After T040 logout-survival evidence is recorded and T053 through T076 are complete, restart or relaunch the target-host daemon from the rebuilt lane-aware and crash-resilient artifact, record the safe artifact identity tuple and same-run `server-start` receipt for that launch, rerun one controlled watched-page live or dry-run smoke for the operator-account case, and record daemon PID/status freshness, `status_shape=current-mvp`, lane/latency field presence, polling-backed current-head or bounded-lag proof under active edits, candidate-first recovery evidence when a recovery pass runs, crash-resilience status, outcome, and any rollback in `suppressor/docs/operations.md` and `specs/001-real-time-suppression/quickstart.md`. A stale replayed hide while the daemon remains hours behind fails this task.

---

## Phase 6b: Live-Priority Parallel Execution And Timing Evidence

**Purpose**: Keep live recentchange suppression independent from reconciliation, catch-up,
verification, and one-shot command work by adding explicit parallel live/background lanes, short
transactions, bounded concurrency, and timing evidence inside the existing daemon. Do not add a
fixed internal live-worker handoff SLA; measure timings and fail only when live work waits for
background drain or violates the external SC-001 hide targets.

- [X] T053 [P] [US1] Add bounded latency percentile tests for `queue-to-submit`, `submit-to-complete`, and `observed-to-hidden` snapshots alongside existing observed-to-queue coverage in `suppressor/src/metrics.rs`
- [X] T054 [P] [US1] Add runtime-status compatibility and serialization tests for additive live/background lane snapshots, queue depths, in-flight counts, saturation metadata, and latency fields in `suppressor/src/state.rs` and `suppressor/tests/config_and_state.rs`
- [X] T055 [US1] Add a deterministic live-priority test that blocks synthetic background reconciliation work, injects a synthetic watched live edit, records observed-to-queue and queue-to-submit timings, and fails if live queue-to-submit waits for background drain rather than asserting a fixed internal handoff SLA in `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, and `suppressor/src/reconcile.rs`
- [X] T056 [US1] Add live queue saturation, short live action deadline, deferred retry, and degraded-status tests for timeout, rate-limit, and full-queue paths in `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, and `suppressor/src/mw_api.rs`
- [X] T057 [US1] Add a burst test with at least 10 synthetic eligible watched edits that verifies bounded live queue behavior, duplicate protection, final outcomes, and p50/p95/p99 reporting in `suppressor/src/stream.rs`, `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, and `suppressor/src/metrics.rs`
- [X] T058 [US1] Extend the action, lane, status, and latency models with `live`/`background` lane kind, queue capacity/depth, in-flight count, saturation reason, action deadline, `queue-to-submit`, `submit-to-complete`, and `observed-to-hidden` fields without changing tracked config shape in `suppressor/src/runtime.rs`, `suppressor/src/state.rs`, and `suppressor/src/metrics.rs`
- [X] T059 [US1] Replace the single shared RevDel work channel with bounded live and background execution lanes, keeping recentchange-triggered hides on the live lane and preventing background work from occupying the only worker path in `suppressor/src/runtime.rs` and `suppressor/src/worker.rs`
- [X] T060 [US2] Route catch-up, reconciliation, rolling last-24h verification, nightly full recheck, manual coverage, and one-shot suppression work through the bounded background lane with concurrency no higher than the reviewed default API cap in `suppressor/src/catchup.rs`, `suppressor/src/reconcile.rs`, `suppressor/src/scheduler.rs`, `suppressor/src/commands.rs`, and `suppressor/src/runtime.rs`
- [X] T061 [US1] Implement short dispatcher transaction boundaries for duplicate protection, queued status/depth persistence, enqueue, submit status, completion status, and processed-revision persistence so no runtime-status, queue, or processed-state lock is held across MediaWiki API calls or retry sleeps in `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, and `suppressor/src/state.rs`
- [X] T062 [US1] Implement live action deadlines, full-live-queue degraded status, and deferred retry or recovery scheduling so a timed-out or rate-limited live attempt cannot block newer live edits behind the same wait in `suppressor/src/runtime.rs`, `suppressor/src/worker.rs`, and `suppressor/src/mw_api.rs`
- [X] T063 [US1] Surface lane-aware runtime evidence in operator status and TUI views, including live/background queue depth/cap, live/background in-flight count, latest saturation, and p50/p95/p99 live timing fields in `suppressor/src/tui_status.rs`, `suppressor/src/tui_view.rs`, `suppressor/src/state.rs`, and `suppressor/src/runtime.rs`
- [X] T064 [US1] Run targeted live-priority, blocked-background, burst, deadline, deferred-retry, transaction-ordering, and lane-status tests and record commands, pass/fail results, timing observations, no-fixed-internal-SLA confirmation, and any remaining blocker in `specs/001-real-time-suppression/quickstart.md`
- [X] T065 After T064 passes or records an explicit blocker, rerun `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` and `make -C suppressor build-server` for the lane-aware source tree and record the fresh serial-test and server-artifact evidence in `specs/001-real-time-suppression/quickstart.md`
- [X] T066 Update suppressor operator, runtime-boundary, implementation, and testing docs with the live/background lane model, transaction boundaries, live deadline behavior, latency evidence, and resource-sampling expectations in `suppressor/docs/operations.md`, `suppressor/docs/runtime-boundaries.md`, `suppressor/docs/implementation.md`, and `suppressor/docs/testing-strategy.md`

---

## Phase 6c: Crash-Resilient Runtime And Candidate-First Recovery

**Purpose**: Close the two rsynced crash signatures and the previous KISS recovery blocker before
target-host smoke. A rights/session failure must block protection without killing the daemon,
retained-observer or local state persistence failure must not permanently stop live monitoring, and ordinary startup or
emergency recovery must discover watched candidates before falling back to a full watched-set scan.

- [X] T067 [P] [US1] Add a regression proving a synthetic classified RevDel auth or permission failure records blocked or unhealthy live protection without calling `std::process::exit` in `suppressor/src/worker.rs` and `suppressor/src/runtime.rs`
- [X] T068 [P] [US2] Add a regression proving a synthetic `last_event_id` write or atomic replace failure records a `state-persistence` or retained-observer actionable issue and keeps realtime monitoring on a retry/reconnect path in `suppressor/src/stream.rs` and `suppressor/src/state.rs`
- [X] T069 [P] [US2] Add candidate-first recovery tests proving ordinary startup and emergency catch-up query a bounded recentchanges candidate window, filter by watched-title cache, record candidate counts, and require an explicit fallback reason before a full watched-set scan in `suppressor/src/catchup.rs` and `suppressor/src/runtime.rs`
- [X] T070 [US1] Replace process exit on classified RevDel auth or permission failure with a blocked or unhealthy action outcome, compact actionable issue, and preserved daemon status freshness in `suppressor/src/worker.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/state.rs`
- [X] T071 [US2] Make retained-observer cursor and local state persistence failures create parent directories where appropriate, classify remaining write or rename failures, and retry or reopen the retained observer with bounded backoff instead of letting the spawned compatibility task disappear in `suppressor/src/stream.rs`, `suppressor/src/state.rs`, and `suppressor/src/runtime.rs`
- [X] T072 [US2] Implement bounded candidate discovery before per-title recovery scans for startup, polling-gap or retained-observer-gap recovery, and emergency catch-up windows, including watched-title filtering and explicit full-scan fallback reasons in `suppressor/src/catchup.rs`, `suppressor/src/mw_api.rs`, `suppressor/src/runtime.rs`, and `suppressor/src/state.rs`
- [X] T073 [US2] Surface blocked permission, state-persistence, and candidate-first recovery evidence in runtime status and the primary TUI without false healthy output or raw sensitive identifiers in `suppressor/src/state.rs`, `suppressor/src/runtime.rs`, `suppressor/src/tui_status.rs`, and `suppressor/src/tui_view.rs`
- [X] T074 [US1] Run targeted crash-resilience and candidate-first tests after T070 through T073 and record commands, pass/fail results, and any remaining blocker in `specs/001-real-time-suppression/quickstart.md`
- [X] T075 After T074 passes or records an explicit blocker, rerun `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` for the crash-resilient source tree and record fresh serial-test evidence in `specs/001-real-time-suppression/quickstart.md`
- [X] T076 After T075 passes, rebuild the server artifact with `make -C suppressor build-server` and record the rebuilt crash-resilient artifact path or local prerequisite blocker in `specs/001-real-time-suppression/quickstart.md`
- [X] T077 Update suppressor operator, runtime-boundary, implementation, and testing docs with the no-process-exit permission policy, stream state-persistence retry policy, candidate-first recovery behavior, and raw-log privacy rule in `suppressor/docs/operations.md`, `suppressor/docs/runtime-boundaries.md`, `suppressor/docs/implementation.md`, and `suppressor/docs/testing-strategy.md`

---

## Phase 6d: Post-Hotfix Resource And Close-Out Evidence

**Purpose**: Run only after the live-hide hotfix and live-priority lane slice are proven or
explicitly blocked, and after Phase 6c produces the rebuilt current binary.

- [ ] T042 After T052 proves the rebuilt target-host artifact identity and `status_shape=current-mvp`, measure at least 10 minutes of idle daemon-alone and daemon-plus-TUI CPU/RSS, one active live/recovery/backoff sample, live lane and background lane queue depths versus caps, live/background in-flight counts, API concurrency at or below the reviewed default cap, state/report file sizes, detached log growth rate, coalesced-warning counts, and live timing p50/p95/p99 for observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden on the deployment host; record pass/fail against SC-011 bounds in `suppressor/docs/operations.md`
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
- **Live-Hide Hotfix (Phase 6a)**: Depends on T041 incident facts for the local live-path fix.
  T047 through T051 may stay closed as synthetic regression, code-fix, test, and rebuild evidence,
  but T052 target-host trust now depends on T040 logout-survival evidence plus the rebuilt binary
  from Phase 6c, recorded with same-run artifact identity and current-MVP status evidence. Phase
  6a blocks T052, T042 resource sampling, and production trust before any broader close-out.
- **Live-Priority Parallel Execution (Phase 6b)**: Depends on Phase 6a local hotfix evidence and
  the current performance plan. T053 through T057 are the failing-test/coverage front edge; T058
  through T063 implement the lane-aware runtime; T064 through T066 provide fresh local evidence and
  docs. This phase blocks T052 target-host smoke, T042 resource sampling, and production trust.
- **Crash-Resilient Runtime And Candidate-First Recovery (Phase 6c)**: Depends on Phase 6a and
  Phase 6b local code evidence. T067 through T077 block T052 and T042 because the rsynced server
  showed that a permission failure can still exit the daemon, stream state persistence can stop live
  monitoring, and ordinary recovery can still waste time on full watched-set scanning.
- **Post-Hotfix Evidence (Phase 6d)**: Depends on Phase 6a, Phase 6b, and Phase 6c unless a phase
  records an explicit blocker or human go/no-go exception; T042 resource evidence must not be used
  to hide a failed live-protection path, missing logout evidence, unproven target-host artifact
  identity, old deployed binary, crash-prone runtime, or missing lane-priority timing evidence.

### User Story Dependencies

- **US1 (P1)**: First daemon MVP slice; complete before deployment trust.
- **US2 (P2)**: Production-trust slice; complete before claiming stable daemon operation.
- **US3 (P3)**: Operator-command evidence slice; complete before relying on catch-up/coverage
  commands during incidents.

Emergency production note: until live-hide soak passes on the target host, deployment proof uses
the live-only profile with `daytime_verification.enabled=false` and `nightly_sweep.enabled=false`.
Manual `Last 24 hours`, full recheck, and emergency catch-up commands remain available, but
automatic verification is not part of the current target-host trust gate.

### Parallel Opportunities

- T005, T006, T007, and T008 can run in parallel across different foundational test surfaces.
- T012, T013, and T014 can run in parallel for US1 tests.
- T020, T021, T022, and T023 can run in parallel for US2 tests.
- T029, T030, and T031 can run in parallel for US3 tests.
- T047 and T048 may run in parallel only if ownership is split between the
  `suppressor/src/stream.rs` and `suppressor/src/recentchange.rs` test path versus the
  `suppressor/src/runtime.rs` and `suppressor/tests/config_and_state.rs` queue/processed-state
  path; otherwise keep the hotfix sequential.
- T053 and T054 can run in parallel because latency math and status compatibility touch different
  test surfaces.
- T055, T056, and T057 should be written before implementation but are not independent of each
  other once the runtime harness shape changes; keep ownership explicit if they are split.
- T060 can proceed in parallel with T063 only after T058 and T059 define the shared lane model and
  status fields.
- T066 can start in parallel with T064/T065 only as documentation of implemented behavior; do not
  document unverified lane timing as release evidence.
- T067, T068, and T069 can run in parallel because they cover worker failure, stream persistence,
  and catch-up candidate discovery test surfaces.
- T070 and T071 can run in parallel only if ownership is split between `worker.rs`/`runtime.rs` and
  `stream.rs`/`state.rs`; T073 should wait until both status-producing implementations are clear.
- T077 can start in parallel with T074/T075 only as documentation of implemented behavior; do not
  document unverified crash-resilience or candidate-first behavior as release evidence.
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

## Parallel Example: Live-Priority Lane Slice

```text
Task: "T053 [P] [US1] Add bounded latency percentile tests for queue-to-submit, submit-to-complete, and observed-to-hidden snapshots in suppressor/src/metrics.rs"
Task: "T054 [P] [US1] Add runtime-status compatibility and serialization tests for additive live/background lane snapshots in suppressor/src/state.rs and suppressor/tests/config_and_state.rs"
```

## Parallel Example: Crash-Resilient Runtime Slice

```text
Task: "T067 [P] [US1] Add a no-process-exit RevDel permission regression in suppressor/src/worker.rs and suppressor/src/runtime.rs"
Task: "T068 [P] [US2] Add a stream cursor persistence failure retry regression in suppressor/src/stream.rs and suppressor/src/state.rs"
Task: "T069 [P] [US2] Add candidate-first recovery tests in suppressor/src/catchup.rs and suppressor/src/runtime.rs"
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 live daemon path.
3. Complete US2 recovery/reconciliation/nightly truth.
4. Run the shortest suppressor test gate.
5. Build the server artifact with `make -C suppressor build-server`.
6. Treat the config-stability gate as Q001-approved path 1 and record the rsynced partial T040
   evidence, then finish the remaining logout-survival evidence. Do not mark T040 from process
   liveness alone, and do not stop a possibly protective daemon only to make evidence cleaner.
7. Complete the T053 through T066 live-priority lane slice before trusting new deployment evidence:
   add timing tests first, implement separate bounded live/background lanes, keep transactions short,
   avoid config-shape changes, and refresh local test/build evidence for the lane-aware tree.
8. Complete T067 through T077 before target-host smoke: no process exit on classified RevDel
   auth/permission failure, stream state-persistence retry/reconnect, candidate-first recovery,
   fresh serial test evidence, rebuilt server artifact, and updated operator docs.
9. Execute any remaining T041 and T052 evidence around the closed T047 through T051 hotfix slice:
   preserve the exposed revision when known through operator-local action only, keep real incident
   identifiers out of tracked files, validate or relaunch with T040 logout evidence or an approved
   fallback/exception, record the launched artifact identity plus same-run current status shape, and
   prove one controlled live or dry-run watched edit against the lane-aware crash-resilient binary.
10. Run T042 deployment-host resource sampling only after T052 passes, records an explicit blocker,
   or records a human go/no-go exception, and include lane depths, in-flight counts, and live
   latency p50/p95/p99.
11. Keep US3 command/report hardening and final docs evidence closed only if they remain consistent
   with the config-stability and deployment evidence.

### Suggested MVP Scope

The active safety-freeze MVP is Phase 1 + Phase 2 + US1 + US2 + T037 through T042 plus T047 through
T077. US3 and T043 through T046 are required before broader operator-command trust or feature
close-out.

### Guardrails

- Do not start unrelated `biblio`, inactive `002`, broad docs, new service, or cosmetic TUI work.
- Do not treat checked tasks or generated text as release evidence.
- Do not log sensitive article content, hidden text, cookies, tokens, credentials, or `.env`
  values.
- Do not commit real sensitive-edit incident identifiers in docs, tests, contracts, examples,
  fixtures, comments, screenshots, logs, or copied command output.
- Do not let reconciliation, catch-up, scheduled verification, or detached launch checks starve live
  hiding.
- Do not let background lane retries, page scans, or reconciliation sleeps hold runtime-status,
  queue, or processed-revision locks across MediaWiki API calls.
- Do not make further target-host or tracked config changes as a shortcut around T040 evidence.
- Do not treat process liveness, an old binary with missing lane/latency fields, fresh but
  mismatched status, stale PID evidence, or a launch receipt without same-run artifact identity and
  current-MVP status shape as T040 or T052 proof.
- Do not call `std::process::exit` for classified RevDel auth/permission failure in the daemon
  runtime.
- Do not let a retained observer cursor or local state persistence failure permanently remove live monitoring
  while the rest of the daemon appears idle or healthy.
