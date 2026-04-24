---
docmeta:
  status: draft
  review: feature-local
  purpose: Implementation plan for restoring urgent real-time suppressor hiding.
  source: speckit-plan on 2026-04-24
---

# Implementation Plan: Real-Time Suppression Recovery


## Summary

Restore `suppressor` as a real-time safety service: eligible edits on watched sensitive pages must be detected, hidden, and reported without operator refreshes or nightly reconciliation. The plan keeps the existing Rust daemon/TUI architecture, but is now grounded in the targeted code audit: the most likely current fault is a silently stale EventStreams loop that can leave the daemon "running" while no new edits are handled, with no operator-visible realtime freshness signal. The implementation therefore prioritizes watchdog-based live-path hardening, explicit bounded catch-up, durable realtime status, and repeatable latency evidence.

## Technical Context

**Language/Version**: Rust edition 2024, using the existing `suppressor` crate  
**Primary Dependencies**: `tokio`, `reqwest`, `reqwest-eventsource`, `serde`, `chrono`, `metrics`, `tracing`, `ratatui`, `crossterm`, `wiremock` for tests  
**Storage**: Local state files under `suppressor/state/`: `last_event_id.txt`, `processed_revids.json`, `nightly_sweep_progress.json`, `runtime_status.json`, plus the suppression-list cache  
**Testing**: `cargo test` in `suppressor/`, focused unit/subsystem tests, mocked MediaWiki API tests with `wiremock`, targeted stream-stall/watchdog tests with controlled time or harnesses, and controlled dry-run/manual latency verification against production config  
**Target Platform**: Linux local daemon plus local TUI supervisor for be.wikipedia.org  
**Project Type**: Single Rust CLI/daemon/TUI tool inside `suppressor/`  
**Performance Goals**: 95% of eligible live edits hidden within 1 second, 99% within 5 seconds under normal wiki/account availability; stale realtime state visible within 10 seconds; 30-minute catch-up completed or reported within 2 minutes  
**Constraints**: Keep scope narrow; hide only `user|comment`; do not log sensitive article content, hidden text, secrets, or session material; fail closed on unrecoverable auth/permission loss; avoid turning reconciliation into the primary live path; do not count manual cache reload or hour-scale current-day reconciliation as acceptable substitutes for live hiding  
**Scale/Scope**: Current be.wiki production baseline with about 1.4k listed/watched sensitive titles, bursty RecentChanges input, one live stream connection, one local operator, one daemon process

**Known Findings From Targeted Code Audit**:

- The current live loop waits on `stream.next().await` and only reconnects on explicit stream errors or EOF, so silent starvation can leave the process alive while no new edits are processed.
- The current runtime status and TUI show daemon/reconciliation state plus `last_event_id`, but do not show realtime freshness, last matched edit, last successful hide, or the current recovery trigger.
- The current `current_day_recheck` cadence is configured in hours, and manual reload only refreshes the suppression-list cache; neither path can satisfy the sub-second live-hiding requirement.
- Existing instrumentation already captures queue depth, `event_to_api_submit_latency_ms`, and `immediate_hide_latency_ms`; the plan should extend this into a complete event-observed-to-hide latency evidence path.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Gate status**: PASS before Phase 0; PASS after Phase 1 design.

- Separate Tools First: PASS. Work remains inside the existing `suppressor` tool, which clearly owns this incident.
- Explicit Boundaries, Minimal Coupling: PASS. Live event ingestion, catch-up, worker actions, local state, TUI display, and MediaWiki transport remain separate modules/contracts.
- Narrow, Risk-Based Scope: PASS. The feature restores rapid be.wiki public RevDel for watched sensitive pages and does not expand into general moderation or remote operation.
- Deterministic Documentation, Safe Writes, And Honest Status: PASS. New feature docs are feature-local draft docs; managed review labels are not edited. Durable operator docs will be updated during implementation.
- Spec Kit First For Non-Trivial Work: PASS. This plan follows the active `spec.md`; tasks and implementation will follow.
- Production Readiness Evidence: PASS with required follow-up. Implementation must include automated coverage for the live/catch-up/status failure modes and manual verification before claiming production readiness.

**Documentation impact**:

- Update `suppressor/README.md` with realtime health, emergency catch-up, and accident-window verification entry points.
- Update `suppressor/docs/operations.md` with expected realtime latency, stale-state response, and manual verification flow.
- Update `suppressor/docs/implementation.md` with the distinction between realtime stream handling, bounded catch-up, worker execution, and nightly reconciliation.
- Update `suppressor/docs/runtime-boundaries.md` if new state files, commands, or daemon loops are introduced.
- Update `suppressor/docs/testing-strategy.md` with controlled realtime/catch-up/status tests.
- Document clearly that manual cache reload and nightly/current-day reconciliation are diagnostic or fallback actions, not the primary remedy for live protection failures.
- No expected changes to `.specify/memory/constitution.md`, `.specify/doc-registry.json`, or standing governance docs.
- Final feature close-out must run `python3 tools/doc_workflow.py all` and the relevant `suppressor` Rust checks.
- No `questions.md` is needed at planning time; the accident-window bounds are operational input for a command/report, not a planning blocker.

## Project Structure

### Documentation (this feature)

```text
specs/001-real-time-suppression/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── checklists/
│   ├── requirements.md
│   ├── realtime.md
│   ├── recovery.md
│   ├── operator-safety.md
│   └── release-readiness.md
├── contracts/
│   ├── operator-commands.md
│   └── runtime-status.md
├── spec.md
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
suppressor/
├── Cargo.toml
├── config.toml
├── src/
│   ├── daemon.rs              # daemon lifecycle and loop startup
│   ├── stream.rs              # EventStreams ingestion and live candidate routing
│   ├── recentchange.rs        # recentchange event parsing and candidate extraction
│   ├── mw_api.rs              # MediaWiki API transport and revision queries
│   ├── runtime.rs             # shared runtime, action dispatcher, status persistence
│   ├── worker.rs              # queued RevDel execution and outcome recording
│   ├── reconcile.rs           # slower reconciliation/backfill paths
│   ├── scheduler.rs           # reconciliation scheduler loops
│   ├── state.rs               # local durable state schemas
│   ├── commands.rs            # one-shot CLI commands
│   ├── cli.rs                 # CLI command shape
│   ├── tui_status.rs          # TUI state collection
│   ├── tui_view.rs            # TUI status rendering
│   └── cache/                 # watched-title cache
├── tests/
│   ├── api_integration.rs
│   └── config_and_state.rs
└── docs/
    ├── implementation.md
    ├── operations.md
    ├── runtime-boundaries.md
    └── testing-strategy.md
```

**Structure Decision**: Use the existing `suppressor/` crate. Do not create a new service or shared top-level package. Add small internal modules only if they reduce live/catch-up/status coupling; otherwise extend the existing `stream.rs`, `runtime.rs`, `state.rs`, `worker.rs`, `mw_api.rs`, `commands.rs`, `tui_status.rs`, and `tui_view.rs` surfaces.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified.

## Implementation Phases

### Phase 0 - Incident Verification And Design Grounding

- Reproduce or disprove the silent-starvation hypothesis with a controlled harness that can open the stream and then stop delivering items without forcing an explicit stream error.
- Confirm the current live path can run while ineffective: running daemon, old or unchanging last event state, and no realtime freshness, last-match, or last-hide status for the operator.
- Identify whether the active incident is caused by silent EventStreams starvation, invalid Last-Event-ID recovery, title matching/cache state, queue/worker failure, or missing rights/session.
- Confirm from config and control paths that current-day reconciliation and manual cache reload cannot satisfy the P1 latency target and must remain diagnostic/fallback only.
- Preserve sensitive-data rules during investigation: inspect revision IDs, timestamps, titles, status, and outcomes, not hidden text.

### Phase 1 - Realtime Health And State Contract

- Extend runtime status with a dedicated realtime section, including state, last state change, stale threshold, last stream open, last event observed, last matching edit, last queued hide, last successful hide, lag, queue depth, current recovery trigger, last reconnect reason, catch-up state, and latest actionable error.
- Persist status transitions whenever the stream opens, receives a target-wiki event, matches a watched edit, queues an action, completes an action, encounters an error, or crosses a silence/watchdog threshold.
- Render realtime status in the TUI as healthy, catching up, stale, unhealthy, blocked, or stopped, and explicitly distinguish "process alive" from "realtime healthy".

### Phase 2 - Live Path Repair

- Refactor event handling so parsing, wiki filtering, watched-title matching, dispatch, and status updates can be tested without a live EventSource connection.
- Add an explicit silence watchdog or timeout-driven freshness mechanism so an open but silent stream cannot remain "running" forever if no new items arrive.
- Keep the live path independent from reconciliation and ensure queueing a live candidate does not wait for nightly/current-day sweeps or source-list refresh work.
- Use explicit recovery transitions for invalid Last-Event-ID, reconnect errors, and silent starvation instead of relying on hour-scale reconciliation as the first response.
- Record skipped, duplicate, and already-hidden outcomes distinctly instead of treating all non-success states as invisible.

### Phase 3 - Bounded Catch-Up And Accident Coverage

- Add an explicit bounded API catch-up path for startup, stream reconnect, silent-starvation recovery, and operator-triggered emergency catch-up; do not rely on `since_recovery_seconds` stream replay alone as proof of coverage.
- Prioritize newest eligible watched-page edits during catch-up while still accounting for every checked edit outcome.
- Add accident-window coverage reporting that accounts for hidden, already-hidden, skipped, failed, and unresolved revisions without exposing sensitive content.
- Surface recovery summary counts, unresolved identifiers, and recovery trigger information to runtime status and one-shot command output.

### Phase 4 - Worker Outcome And Failure Visibility

- Record outcomes at the revision level with queued, submitted, hidden, already-hidden, retrying, failed, unresolved, and blocked states instead of a success-only processed ring.
- Keep transient failures retryable and visible; classify rights/session/wiki-side blockers as urgent unhealthy states.
- Preserve fail-closed behavior for fatal auth/permission loss, but make the blocked state durable and operator-visible before exit or supervisor restart.
- Avoid duplicate hide attempts when events replay or another operator already hid the edit.

### Phase 5 - Verification, Docs, And Operational Release

- Add focused tests for live event classification and dispatch, silent-stream watchdog transitions, invalid-resume recovery, bounded catch-up selection, duplicate handling, revisiondelete success/failure outcomes, and TUI status rendering.
- Extend latency evidence using existing queue/hide histograms plus a new end-to-end event-observed-to-hide timing path, and capture p50/p95 from controlled runs.
- Run `cargo test` for `suppressor`; if the known parallel test issue still exists, document the isolated or single-thread command used as the release gate.
- Perform manual benchmark/verification against a watched test page or equivalent controlled production-safe flow, recording publish-to-hide wall clock and stale-recovery timing.
- Update suppressor operator/implementation/runtime/testing docs.
- Run `python3 tools/doc_workflow.py all`.
