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
**Testing**: `cargo test` in `suppressor/`, focused unit/subsystem tests, mocked MediaWiki API tests with `wiremock`, targeted stream-stall/watchdog tests with controlled time or harnesses, and controlled dry-run/manual latency verification against production config. External live verification may use `Удзельнік:Plaga med Bot/suppressor/tests` for manual and automated benchmark edits, and every benchmark edit to that page must be explicitly marked as a bot edit.
**Target Platform**: Linux local daemon plus local TUI supervisor for be.wikipedia.org  
**Project Type**: Single Rust CLI/daemon/TUI tool inside `suppressor/`  
**Performance Goals**: 95% of eligible live edits hidden within 1 second, 99% within 5 seconds under normal wiki/account availability; stale realtime state visible within 10 seconds; 30-minute catch-up completed or reported within 2 minutes
**Resource Goals**: run comfortably on a low-spec local host with one daemon and one TUI, bounded queues, bounded API concurrency, bounded state/log growth, no busy loops, and measured idle/active CPU and memory during release verification, without lowering latency/recovery targets or dropping durable documentation evidence
**Architecture Constraints**: preserve one local deployable daemon/TUI package, but keep internals microservice-like: EventStreams ingestion, source refresh, catch-up, RevDel worker, state persistence, metrics, and TUI status communicate through explicit structs, small traits/functions, and bounded channels rather than shared ad hoc coupling
**Minimalism Constraints**: prefer existing dependencies and module patterns; add no new runtime dependency, abstraction, task, command, or state file unless it directly improves correctness, resource economy, observability, testability, or boundary clarity for this incident
**Operational Constraints**: Keep scope narrow; hide only `user|comment`; do not log sensitive article content, hidden text, secrets, cookies, tokens, or session material; fail closed on unrecoverable auth/permission loss; avoid turning reconciliation into the primary live path; do not count manual cache reload or hour-scale current-day reconciliation as acceptable substitutes for live hiding
**Scale/Scope**: Current be.wiki production baseline with about 1.4k listed/watched sensitive titles, bursty RecentChanges input, one live stream connection, one local operator, one daemon process, and no new public network service for this feature

**Known Findings From Targeted Code Audit**:

- The current live loop waits on `stream.next().await` and only reconnects on explicit stream errors or EOF, so silent starvation can leave the process alive while no new edits are processed.
- The current runtime status and TUI show daemon/reconciliation state plus `last_event_id`, but do not show realtime freshness, last matched edit, last successful hide, or the current recovery trigger.
- The current `current_day_recheck` cadence is configured in hours, and manual reload only refreshes the suppression-list cache; neither path can satisfy the sub-second live-hiding requirement.
- Existing instrumentation already captures queue depth, `event_to_api_submit_latency_ms`, and `immediate_hide_latency_ms`; the plan should extend this into a complete event-observed-to-hide latency evidence path.

**Findings From 2026-04-25 Runtime Analysis**:

- Bounded catch-up is sending MediaWiki revision timestamps with fractional nanoseconds through `rvstart`; production API probing showed MediaWiki rejects that shape as `badtimestamp`, which explains all-pages catch-up failure and the warning storm.
- The source-list recentchange hook refreshes `Удзельнік:Wizardist/SuppressionList` and then returns; it does not immediately run a bounded catch-up for newly added pages, so new sensitive titles can wait for a slower fallback.
- Live RevDel failures are persisted only as `api-error`; the exact API error code, HTTP status, content type, and retryability are not durable enough for the TUI or post-incident diagnosis.
- Catch-up logs one warning per page for identical API failures, which floods the TUI and hides the root cause from the operator.
- `freshness_probe_seconds` exists in config and contracts, but no implemented API freshness probe was found, so stale-stream lag may still be based only on stream-observed events.
- The current code has useful module boundaries, but the remediation must tighten them into small internal service contracts instead of adding new processes or network services.
- Release evidence must include resource-economy checks on daemon plus TUI so performance improvements do not assume a powerful workstation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Gate status**: PASS before Phase 0; PASS after Phase 1 design.

- Separate Tools First: PASS. Work remains inside the existing `suppressor` tool, which clearly owns this incident.
- Explicit Boundaries, Minimal Coupling: PASS. Live event ingestion, catch-up, worker actions, local state, TUI display, and MediaWiki transport remain separate modules/contracts.
- Narrow, Risk-Based Scope: PASS. The feature restores rapid be.wiki public RevDel for watched sensitive pages and does not expand into general moderation or remote operation.
- Deterministic Documentation, Safe Writes, And Honest Status: PASS. New feature docs are feature-local draft docs; managed review labels are not edited. Durable operator docs will be updated during implementation.
- Spec Kit First For Non-Trivial Work: PASS. This plan follows the active `spec.md`; tasks and implementation will follow.
- Production Readiness Evidence: PASS with required follow-up. Implementation must include automated coverage for the live/catch-up/status failure modes and manual verification before claiming production readiness.
- Resource Economy, Robustness, And Durable Lessons: PASS with required follow-up. The requested "microservices architecture" is implemented as internal microservice-like boundaries inside the existing local daemon/TUI deployment, which satisfies minimal coupling without violating the single-tool, low-overhead deployment model. Resource economy must not lower the live latency/recovery targets or reduce documentation quality.

**Documentation impact**:

- Update `suppressor/README.md` with realtime health, emergency catch-up, and accident-window verification entry points.
- Update `suppressor/docs/operations.md` with expected realtime latency, stale-state response, and manual verification flow.
- Update `suppressor/docs/implementation.md` with the distinction between realtime stream handling, bounded catch-up, worker execution, and nightly reconciliation.
- Update `suppressor/docs/runtime-boundaries.md` if new state files, commands, or daemon loops are introduced.
- Update `suppressor/docs/testing-strategy.md` with controlled realtime/catch-up/status tests.
- Update suppressor docs with resource-economy defaults, bounded concurrency/state/logging behavior, and low-spec verification evidence.
- Preserve incident lessons in targeted tests, durable docs, and concise code comments where the rule is non-obvious, especially MediaWiki timestamp serialization and source-triggered catch-up.
- Document clearly that manual cache reload and nightly/current-day reconciliation are diagnostic or fallback actions, not the primary remedy for live protection failures.
- Standing governance has been amended through constitution v1.5.0 to encode low-spec economy without performance, robustness, or documentation compromise. No `.specify/doc-registry.json` change is expected.
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

### Internal Service Boundaries

The implementation should behave like a set of small internal services while remaining one deployable binary:

- `stream.rs`: target-wiki EventStreams ingestion, source-page detection, and live candidate routing.
- `cache/`: source-list fetch, parse, diff, redirect expansion, and persistence.
- `catchup.rs`: bounded recovery windows, title-scoped catch-up, summary aggregation, and unresolved exposure reporting.
- `mw_api.rs`: MediaWiki transport, timestamp serialization, response parsing, and classified non-sensitive error snapshots.
- `worker.rs`: RevDel submission, retry/relogin/token refresh, final outcome recording, and fatal blocked-state handling.
- `runtime.rs` and `state.rs`: bounded queues, status persistence, outcome/error/source-refresh state, and explicit cross-module contracts.
- `tui_status.rs` and `tui_view.rs`: read-only status snapshot collection and compact operator rendering.

Cross-boundary data must use typed structs and compact enums rather than stringly-typed ad hoc messages where a stable contract matters. Channels and local state must remain bounded so catch-up, benchmark runs, or warning storms cannot exhaust low-spec machines.

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

### Phase 6 - Remediation For 2026-04-25 Findings

- Add a single MediaWiki timestamp serialization helper for API query parameters that emits UTC seconds without fractional precision, and use it for `rvstart`, coverage windows, stream `since` values where applicable, and any future MediaWiki timestamp parameter.
- Extend API transport error handling so JSON API errors, non-JSON responses, HTTP status failures, and decode failures are classified separately; persist compact non-sensitive error evidence in runtime status and worker outcomes.
- Change bounded catch-up warning behavior from per-page log spam to root-cause summaries: record the first few affected titles, aggregate repeated failures by classified reason, and surface the aggregate in the TUI.
- Replace the source-list hook's refresh-only behavior with refresh-plus-immediate-catch-up: after a successful source cache refresh, compute newly added watched titles and run a short bounded catch-up for those titles before declaring the list update handled.
- Treat `Вікіпедыя:Запыты да схавальнікаў` as a source-adjacent trigger: when it changes, refresh the source cache if needed and run immediate bounded catch-up over watched titles affected by the request page or the configured recent window.
- Implement the bounded API freshness probe promised by the runtime-status contract, using a low-cost recentchanges query for the target wiki to distinguish a quiet stream from stale monitoring.
- Add a production-safe benchmark path using `Удзельнік:Plaga med Bot/suppressor/tests`: the benchmark may create controlled test edits only on that page, must set the MediaWiki `bot` edit marker, and must record publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings.
- Keep the benchmark path separate from production source-list mutations unless the operator explicitly asks to test source-list reload behavior; routine automated benchmark writes must not edit `Удзельнік:Wizardist/SuppressionList`.
- Enforce resource-economy defaults while implementing the remediation: low catch-up concurrency by default, no unbounded queues or vectors for watched-page scans, no per-page warning spam, no hot-loop freshness probing, and compact rolling state for outcomes and benchmark samples, while preserving the performance targets and documentation evidence.
- Keep the code small and direct: reuse existing runtime/cache/API/worker patterns, prefer simple typed helpers over framework-like abstractions, and reject new dependencies unless they replace fragile custom logic with a clearly safer or cheaper primitive.
- Document every non-obvious incident lesson in the smallest durable place that will prevent recurrence: regression tests for behavior, operator docs for response, implementation docs for architecture, and concise code comments only where the code would otherwise invite a repeat bug.
