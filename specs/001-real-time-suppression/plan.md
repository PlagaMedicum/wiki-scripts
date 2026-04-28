---
docmeta:
  status: draft
  review: feature-local
  purpose: Implementation plan for restoring urgent real-time suppressor hiding.
  source: speckit-plan on 2026-04-28
---

# Implementation Plan: Real-Time Suppression Recovery


## Summary

Restore `suppressor` as a real-time safety service: eligible edits on watched sensitive pages must be detected, hidden, and reported without operator refreshes or nightly reconciliation. The first remediation slice already fixed MediaWiki timestamp serialization, source-list/request-page triggers, classified API error persistence, warning coalescing, and basic throttle metadata. Current operator evidence adds a third class of remaining work beyond throttled catch-up and mixed command status: the same classified rate-limit failures now clearly affect the live hide path, `startup` recovery is still being used or labeled too broadly, and the realtime state machine can remain stuck in `catching-up` after backoff or recovery has already ended. The updated feature spec also adds a compatibility obligation: operator-facing status or report surfaces and launch-path assumptions must remain backward-compatible where practical, or the release must emit an explicit migration-needed diagnostic instead of silently invalidating the previous setup. The remaining plan therefore shifts from broad incident discovery to authoritative daemon status, rate-aware recovery across live and catch-up paths, state-convergent operator surfaces, compatibility-safe operator diagnostics, and deployment verification on low-spec hardware.

## Technical Context

**Language/Version**: Rust edition 2024, using the existing `suppressor` crate  
**Primary Dependencies**: `tokio`, `reqwest`, `reqwest-eventsource`, `serde`, `chrono`, `metrics`, `tracing`, `ratatui`, `crossterm`, `wiremock` for tests  
**Storage**: Local state files under `suppressor/state/`: `last_event_id.txt`, `processed_revids.json`, `nightly_sweep_progress.json`, `runtime_status.json`, plus the suppression-list cache  
**Testing**: `cargo test` in `suppressor/`, focused unit/subsystem tests, mocked MediaWiki API tests with `wiremock`, targeted stream-stall/watchdog tests with controlled time or harnesses, compatibility fixtures for older state/status shapes and stale supervisor artifacts, and controlled dry-run/manual latency verification against production config. The current local baseline already includes passing serialized and full suppressor test runs plus the repo docs gate; the remaining work needs new failing-first tests around throttling, live-path rate-limit failures, state convergence after recovery/backoff, bounded state retention, compatibility-safe command/report surfaces, and restart/live verification. External live verification may use `Удзельнік:Plaga med Bot/suppressor/tests` for manual and automated benchmark edits, and every benchmark edit to that page must be explicitly marked as a bot edit.
**Target Platform**: Linux local daemon plus local TUI supervisor for be.wikipedia.org  
**Project Type**: Single Rust CLI/daemon/TUI tool inside `suppressor/`  
**Performance Goals**: 95% of eligible live edits hidden within 1 second, 99% within 5 seconds under normal wiki/account availability; stale realtime state visible within 10 seconds; 30-minute catch-up completed or reported within 2 minutes; publish-to-detect and detect-to-hide evidence recorded explicitly enough to distinguish daemon latency from unavoidable post-publication visibility
**Resource Goals**: run comfortably on a low-spec local host with one daemon and one TUI, bounded queues, bounded API concurrency, bounded state/log growth, no busy loops, and measured idle/active CPU and memory during release verification, without lowering latency/recovery targets or dropping durable documentation evidence
**Architecture Constraints**: preserve one local deployable daemon/TUI package, but keep internals microservice-like: EventStreams ingestion, source refresh, catch-up, RevDel worker, state persistence, metrics, and TUI status communicate through explicit structs, small traits/functions, and bounded channels rather than shared ad hoc coupling
**Minimalism Constraints**: prefer existing dependencies and module patterns; add no new runtime dependency, abstraction, task, command, or state file unless it directly improves correctness, resource economy, observability, testability, or boundary clarity for this incident
**Operational Constraints**: Keep scope narrow; hide only `user|comment`; do not log sensitive article content, hidden text, secrets, cookies, tokens, or session material; fail closed on unrecoverable auth/permission loss; avoid turning reconciliation into the primary live path; do not count manual cache reload or hour-scale current-day reconciliation as acceptable substitutes for live hiding; document clearly that an external EventStreams daemon minimizes post-publication exposure but cannot guarantee zero first-view prevention without a broader in-wiki control path
**Scale/Scope**: Current be.wiki production baseline with about 1.4k listed/watched sensitive titles, bursty RecentChanges input, one live stream connection, one local operator, one daemon process, and no new public network service for this feature

**Known Findings From Targeted Code Audit**:

- The current live loop waits on `stream.next().await` and only reconnects on explicit stream errors or EOF, so silent starvation can leave the process alive while no new edits are processed.
- The current runtime status and TUI show daemon/reconciliation state plus `last_event_id`, but do not show realtime freshness, last matched edit, last successful hide, or the current recovery trigger.
- The current `current_day_recheck` cadence is configured in hours, and manual reload only refreshes the suppression-list cache; neither path can satisfy the sub-second live-hiding requirement.
- Existing instrumentation already captures queue depth, `event_to_api_submit_latency_ms`, and `immediate_hide_latency_ms`; the plan should extend this into a complete event-observed-to-hide latency evidence path.
- One-shot operator commands can bootstrap a fresh runtime and currently share the daemon's runtime-status surface, which risks mixing manual command state with daemon truth.
- The TUI live-output pane follows logical input lines while rendering wrapped rows, so the newest visible rows can lag behind the actual newest messages.

**Status After Initial Remediation (must remain covered by regression tests)**:

- MediaWiki API timestamps are serialized through one UTC second-precision helper, removing fractional `rvstart` values.
- Source-list and request-page recentchange hooks can refresh cache state and start immediate bounded catch-up.
- Runtime status and the TUI can now persist classified API failure details and aggregate repeated warning causes instead of emitting one warning per page.

**Residual Findings From 2026-04-26 Through 2026-04-28 Runtime And Operator Evidence**:

- Catch-up and reconciliation still hit repeated `fetch-revisions` failures classified as `non-json-response` with `http_status=429`; the response shape now includes `text/plain` as well as earlier HTML/non-JSON cases, so the remaining production fault is throttling or rate limiting rather than timestamp shape.
- Recovery can still scan too far under one repeated root cause, which turns a transient throttle event into large unresolved sets or oversized persisted reports instead of a compact actionable summary.
- The bounded API freshness probe promised by the status contract still needs implementation or proof so the operator can distinguish a quiet wiki from a stale stream without relying only on stream-observed events.
- Current live evidence can show good observed-to-hide latency for a matched edit, but the operator can still see the published edit before the daemon reacts; this is an architectural limit of a post-publication EventStreams consumer and must be documented honestly.
- Current stream behavior still launches, labels, or reports full watched-set `startup` catch-up too broadly on EventStreams reopen or reconnect-error cases, which keeps the daemon in `catching-up` too often and materially harms the 2-minute recovery target.
- One-shot TUI commands such as emergency catch-up and coverage report can currently contaminate daemon runtime truth because they write the same `runtime_status.json`.
- The feature now also needs an explicit compatibility or migration strategy for operator-facing machine-readable status/report surfaces and launch-path assumptions, because the updated spec no longer allows silent invalidation of the previously documented setup.
- Host-level checks show the real current launch path is a TUI-managed child process started through `make tui`, with `target/debug/suppressor --config ./config.toml tui` launching a child `... run` daemon; no installed system or user `suppressor.service` unit exists, so systemd journal evidence is not the authoritative default in this deployment.
- Compact-terminal status should prioritize the active realtime failure or throttle-backoff state over older reconciliation noise when both are present, and live-output rendering should not hide the newest rows under wrapped-line lag.
- The latest runtime evidence on 2026-04-28 shows the same classified `non-json-response`/`429` fault on a `live` suppression outcome, not only on catch-up or reconciliation, so live protection and recovery must share the same actionable throttle semantics.
- The realtime state machine can remain in `catching-up` even when `catchup_active=false`, `backoff_until=null`, fresh target-wiki events are still arriving, and the latest notice is only `observed target-wiki event`; this is a state-convergence bug, not just a presentation issue.

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
- Update `suppressor/docs/operations.md` to distinguish daemon-owned realtime state from one-shot command reports and to document the actual launch path used for verification.
- Update `suppressor/docs/operations.md` to distinguish stream freshness from successful live hiding so a fresh stream plus a failed latest live action does not read as healthy.
- Update `suppressor/docs/operations.md` and feature quickstart evidence to state whether the previously documented operator setup remains valid and, if not, the exact migration actions and new authoritative diagnostics path.
- Update `suppressor/docs/implementation.md` with the distinction between realtime stream handling, bounded catch-up, worker execution, and nightly reconciliation.
- Update `suppressor/docs/runtime-boundaries.md` if new state files, commands, or daemon loops are introduced.
- Update `suppressor/docs/testing-strategy.md` with controlled realtime/catch-up/status tests.
- Update suppressor docs with resource-economy defaults, bounded concurrency/state/logging behavior, and low-spec verification evidence.
- Preserve incident lessons in targeted tests, durable docs, and concise code comments where the rule is non-obvious, especially MediaWiki timestamp serialization and source-triggered catch-up.
- Document the architectural limit that current external realtime hiding cannot guarantee zero first-view prevention, and state what broader mechanism would be needed to change that claim.
- Document clearly that manual cache reload and nightly/current-day reconciliation are diagnostic or fallback actions, not the primary remedy for live protection failures.
- If the compatibility or migration-warning pattern becomes reusable outside `suppressor`, copy the generalized rule into `specs/000-repo-governance/research.md` rather than leaving it only in feature-local notes.
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
│   ├── operator-safety.md
│   ├── realtime.md
│   ├── recovery.md
│   ├── release-readiness.md
│   ├── requirements.md
│   ├── resource-economy.md
│   └── runtime-truth.md
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
- `runtime.rs` and `state.rs`: bounded queues, status persistence, outcome/error/source-refresh state, compatibility diagnostics for older artifacts or invalid launch-path assumptions, and explicit cross-module contracts.
- `commands.rs`: one-shot operator commands and reports that must not overwrite daemon realtime truth and must emit explicit migration guidance if a documented report surface changes.
- `tui_status.rs` and `tui_view.rs`: read-only status snapshot collection and compact operator rendering.

Cross-boundary data must use typed structs and compact enums rather than stringly-typed ad hoc messages where a stable contract matters. Channels and local state must remain bounded so catch-up, benchmark runs, or warning storms cannot exhaust low-spec machines. Daemon-owned realtime status must remain authoritative and must not be overwritten by one-shot command/report boundaries. If an operator-facing machine-readable surface cannot stay backward-compatible, the new surface must carry explicit migration guidance rather than silently breaking the prior workflow.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified.

## Implementation Phases

### Phase 0 - Runtime Evidence And Deployment Grounding

- Recheck the managed daemon, runtime state files, and journal or supervisor output after a restart so the investigation is tied to the binary that is actually running, not only local build output.
- Confirm the actual launch path in use: systemd-managed daemon, TUI-managed child process, or another operator path. The plan and docs must verify the real authority instead of assuming one unit name.
- Compare that actual launch path and its operator surfaces with the previously documented setup, and record whether compatibility is preserved or a migration notice is required before release.
- Confirm whether one-shot commands currently overwrite daemon runtime status and identify the smallest bounded surface for command-only reports.
- Confirm which live or recovery paths still emit classified `non-json-response` `HTTP 429` failures, whether `Retry-After` headers are present, and which loops currently ignore them.
- Confirm whether the same `fetch-revisions` or related revision-query failure class appears in the live path before or during worker submission, and capture that separately from catch-up or reconciliation failures.
- Measure which persisted artifacts grow materially during repeated failure storms, especially `runtime_status.json`, `nightly_sweep_progress.json`, and retained unresolved item lists.
- Preserve sensitive-data rules during investigation: inspect revision IDs, timestamps, titles, status, headers, and compact messages, not hidden text.
- Record the actual publish-to-observe and observe-to-hide timings for at least one controlled live edit so operator-visible latency is separated from architecture-level post-publication exposure.

### Phase 1 - Rate-Limit-Aware Recovery And Catch-Up

- Add first-class throttle handling for `HTTP 429` and similar rate-limit signals in `mw_api` and all catch-up or reconciliation callers: capture retryability, `Retry-After`, backoff-until time, and next operator-visible action.
- Apply the same throttle classification and retry semantics to live-path revision lookups or pre-hide fetches so a rate-limited live edit is surfaced as an actionable degraded protection state rather than only as a stale latest outcome.
- Add a bounded backoff or circuit-breaker stop condition so one repeated root cause pauses or stops recovery early instead of scanning the full watched set into the same unresolved failure.
- Prioritize newest or most recent eligible edits during catch-up so limited API budget protects the newest exposure first while still accounting for partial progress.
- Share rate-limit state across startup catch-up, operator manual catch-up, source-triggered catch-up, and reconciliation so one recovery path cannot starve or confuse another.
- Stop treating every EventStreams `Open` as a fresh `startup` catch-up trigger; restrict full watched-set catch-up to true bootstrap, proven gap recovery, or explicit operator actions.

### Phase 2 - Freshness Probe And Trigger Hardening

- Implement or finish the low-cost bounded API freshness probe promised by the realtime status contract, using it only when stream silence makes freshness ambiguous.
- Ensure source-list and request-page triggers can start immediate catch-up when healthy, or defer it visibly with a backoff reason and retry point when throttled.
- Keep realtime state transitions honest: `healthy` only after stream freshness, pending recovery, active backoff conditions, and latest live protection failures are all clear.
- Make `catching-up` a convergent state: once no catch-up is active, no backoff remains, and fresh events resume, the daemon must leave `catching-up` for `healthy`, `unhealthy`, or `reconnecting` according to the remaining evidence.
- Make daemon-owned realtime status authoritative even while one-shot verification commands are running.
- Detect stale or incompatible prior state, stale PID files, and invalid launch-path assumptions early enough to surface a non-healthy or migration-needed diagnostic instead of a false healthy state.

### Phase 3 - Compact Durable State And Operator Surfaces

- Bound unresolved-item retention and persist counts plus sampled items rather than the full repeated-failure set.
- Extend recovery-summary state with aggregate warning summaries, stop-early reasons, retry-after data, and sampled affected titles or revisions.
- Prioritize active realtime failures and throttle-backoff notices over older reconciliation text in the TUI, especially on compact terminals.
- Show whether the latest actionable failure came from `live`, `catchup`, `reconciliation`, or `source-refresh` context so stream freshness cannot mask an ineffective live hide path.
- Keep backward-compatible loading rules so older state files, stale pid files, and missing new fields degrade to non-healthy diagnostics instead of false healthy status.
- Keep previously documented machine-readable status/report surfaces backward-compatible where practical, and if a change is unavoidable, emit a compact compatibility or migration notice with the required operator action and new authoritative path.
- Separate daemon logs from one-shot command logs in the TUI, or label them clearly enough that operators cannot confuse them.
- Make the TUI latest-follow behavior row-accurate under wrapped output, or disable wrap in the live-output pane so the newest messages are actually visible.

### Phase 4 - Verification, Docs, And Release Evidence

- Add failing-first tests for `429` HTML/non-JSON responses, `Retry-After` handling, repeated-root-cause stop conditions, bounded unresolved retention, freshness probing, source-triggered deferred catch-up, command/runtime-state isolation, and TUI compact-priority plus latest-log rendering.
- Re-run `cargo test` and the repo docs gate, then restart the managed daemon and verify the live TUI, runtime status file, and journal or supervisor output reflect the new fields and behavior.
- Prove either that the previously documented operator setup still works unchanged or that release evidence and operator docs declare the incompatibility, the new authoritative diagnostics path, and the exact migration steps before production use.
- Run controlled benchmark and low-spec resource scenarios, including the approved bot test page with bot edits only, and capture latency plus CPU, memory, queue, state-size, and log-volume evidence.
- Update maintained operator, implementation, runtime-boundary, and testing docs with rate-limit handling, recovery stop conditions, daemon-vs-command status authority, launch-path verification, TUI log behavior, and the architectural limit of post-publication hiding.
