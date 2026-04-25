---
docmeta:
  status: draft
  review: feature-local
  purpose: Design research decisions for real-time suppression recovery.
  source: speckit-plan on 2026-04-24
---

# Research: Real-Time Suppression Recovery


## Decision: Keep EventStreams as the primary live input, but add bounded API catch-up as a first-class recovery path

**Rationale**: The existing daemon already consumes Wikimedia recentchange EventStreams and can react fastest when that stream is healthy. The incident shows that a running process can still miss or delay live hiding, so the plan needs a bounded catch-up path that does not depend on nightly reconciliation timing. A recent bounded query over watched pages/recent changes can recover startup, reconnect, and stale-stream gaps while preserving the live stream as the fastest path.

**Alternatives considered**:

- Use nightly/current-day reconciliation as the only fallback. Rejected because the configured current-day interval is hours, not seconds, and the user observed a 24-minute exposure.
- Poll every watched page continuously. Rejected as too expensive and slower than the live feed for normal operation.
- Replace EventStreams entirely. Rejected because the stream remains the right low-latency source when healthy.

## Decision: Treat silent stream starvation as the primary suspected fault until controlled tests disprove it

**Rationale**: The current live loop waits on `stream.next().await` and reconnects only when the stream yields an explicit error or closes. That means a silent or wedged connection can leave the process alive with no new matched revisions handled. The current runtime status and TUI show daemon/reconciliation state and `last_event_id`, but not realtime freshness, last match, or last successful hide. That combination matches the observed incident much better than a simple daemon crash.

**Alternatives considered**:

- Assume the incident is only stale cache or watched-title mismatch. Rejected because the operator reported manual refreshes and a running daemon, while the system still did not react within 24 minutes.
- Assume hourly current-day reconciliation is sufficient mitigation. Rejected because the configured interval is far too slow for the required live response.

## Decision: Treat realtime health as a separate persisted status contract

**Rationale**: Current status can show "daemon running" and reconciliation progress while the realtime path is not obviously fresh. A separate realtime status section lets the TUI distinguish running-and-hiding, catching up, stale, unhealthy, and blocked states. Persisting it in `runtime_status.json` keeps the TUI simple and gives the operator a stable local state file for diagnostics.

**Alternatives considered**:

- Infer health from `last_event_id.txt`. Rejected because an event ID alone does not show freshness, matching, queueing, success, or failure.
- Rely on raw logs. Rejected because the operator needs immediate status in the TUI without reading log history.

## Decision: Refactor live-event handling into testable units before optimizing

**Rationale**: The urgent bug is in a safety-sensitive path. Extracting recentchange parsing, wiki filtering, watched-title matching, candidate dispatch, and outcome recording into testable functions makes it possible to prove that a controlled eligible event queues a hide immediately without a live EventSource dependency.

**Alternatives considered**:

- Patch only the visible EventSource loop. Rejected because it would not cover title matching, duplicate suppression, worker enqueue, or status updates.
- Add only manual commands. Rejected because manual action does not satisfy the sub-second automatic requirement.

## Decision: Use bounded freshness thresholds and watchdog recovery

**Rationale**: An open event stream can be ineffective if it stalls, disconnects without a useful error, or resumes with a gap. The daemon should update `last_observed_at` for relevant events, classify stale realtime state after the configured target window, and trigger bounded catch-up before reporting healthy again. This directly addresses the current code path, which otherwise waits indefinitely for the next stream item.

**Alternatives considered**:

- Wait only for EventSource errors. Rejected because a silent stream or stuck loop may not produce an immediate error.
- Mark stale only after minutes. Rejected because the operator requires near-immediate hiding and an unhealthy signal within seconds.

## Decision: Do not treat current-day reconciliation or manual cache reload as realtime recovery

**Rationale**: The current config schedules current-day reconciliation on an hour-scale random interval, and the manual reload signal only refreshes the suppression-list cache. Neither path is designed to satisfy the realtime hide SLO, and relying on them would hide the distinction between live protection and slower safety-net workflows.

**Alternatives considered**:

- Shorten the current-day interval and treat it as the live fallback. Rejected because it still couples recovery to page sweeps rather than direct live-event freshness, and it increases load while remaining slower than stream-driven hiding.
- Ask the operator to use cache reload as the first response. Rejected because it does not directly process newly published sensitive edits.

## Decision: Record revision-level outcomes, not just processed successes

**Rationale**: `processed_revids.json` currently represents successful processing but does not account for skipped, failed, retrying, unresolved, or already-hidden outcomes. The feature requires every observed watched-page edit to have a final or current outcome, especially for accident-window coverage.

**Alternatives considered**:

- Continue using only the processed ring. Rejected because it cannot report unresolved exposure or distinguish why a revision was not hidden.
- Store full revision content or comments. Rejected because logs and state must avoid sensitive payloads.

## Decision: Add operator-visible emergency catch-up and accident-window verification

**Rationale**: The operator needs a fast way to verify recent exposure after an incident and after rights/session disruptions. A command/TUI action that checks a bounded window and reports counts plus unresolved revision identifiers gives operational confidence without making the nightly workflow carry urgent recovery semantics.

**Alternatives considered**:

- Ask operators to manually inspect Special:RecentChanges. Rejected because it is slow and easy to miss watched-page edits.
- Hard-code the current accident window. Rejected because the same mechanism should handle future downtime windows.

## Decision: Use existing latency metrics as the base for benchmark evidence

**Rationale**: The worker already records queue submission latency and immediate hide latency. Extending that with a full event-observed-to-hide timing path and a small controlled manual publish-to-hide run gives both repeatable automated evidence and operator-meaningful wall-clock evidence. This is stronger than relying only on ad hoc observation.

**Alternatives considered**:

- Use only manual stopwatch-style validation. Rejected because it is not enough for regression detection or repeated comparison.
- Add a separate benchmark service. Rejected because the existing daemon metrics and controlled tests are sufficient for this feature's scope.

## Decision: Keep scope inside the existing daemon/TUI deployment

**Rationale**: The constitution marks `suppressor` as narrow, speed-sensitive, and safety-sensitive. The current local daemon plus local TUI can satisfy the feature without new public services or multi-operator coordination.

**Alternatives considered**:

- Add a separate monitoring service. Rejected for this urgent fix because it increases deployment and failure-surface complexity.
- Add a public dashboard. Rejected as outside current scope and unnecessary for one local operator.

## Decision: Use microservice-like internal boundaries, not extra deployed services

**Rationale**: The operator wants a good microservices architecture, but this repo's governance and the suppressor's low-spec deployment model favor one local daemon plus TUI. The right interpretation for this feature is a microservice-style internal architecture: stream ingestion, source refresh, catch-up, MediaWiki API transport, RevDel worker, runtime state, metrics, and TUI rendering stay independently testable and communicate through explicit typed contracts and bounded queues. This gives the maintenance and robustness benefits of service boundaries without adding processes, ports, supervisors, IPC, memory overhead, or deployment failure modes.

**Alternatives considered**:

- Split into multiple OS services. Rejected because it increases runtime overhead and operational complexity for one local operator and conflicts with the current narrow deployment model.
- Keep broad shared mutable state and patch locally. Rejected because it is exactly the kind of coupling that hides live-path failures.
- Introduce a public monitoring service or dashboard. Rejected as outside scope and too expensive for the current safety fix.

## Decision: Treat resource economy as a release constraint

**Rationale**: The daemon should run on the lowest reasonable local hardware without trading away realtime suppression. The design therefore prefers bounded channels, compact rolling state, low default catch-up concurrency, coalesced logs, no busy polling, and API calls scoped to deltas or bounded windows. Release evidence should record idle and active CPU/memory for daemon plus TUI, because a performance-sensitive safety service can fail operationally if it assumes a powerful workstation.

**Alternatives considered**:

- Optimize only after feature correctness. Rejected because catch-up, warning floods, and unbounded state can become correctness problems on low-spec machines.
- Maximize concurrency to finish catch-up fastest. Rejected because it risks API pressure, memory growth, and poor behavior during outage loops.
- Disable recovery work to save resources. Rejected because robustness and realtime safety are non-negotiable; economy must come from bounded design, not missing recovery.

## Decision: Prefer small targeted code over new framework layers

**Rationale**: The fastest robust fix is not a broad refactor. The existing crate already has workable modules for stream, cache, API, catch-up, runtime, worker, and TUI. The remediation should add narrow typed helpers, state fields, and tests where needed, while avoiding new dependencies and generalized frameworks unless they replace a fragile local implementation with a safer or cheaper primitive.

**Alternatives considered**:

- Introduce a full service framework or actor system. Rejected because it adds overhead and migration risk for little benefit in a single local daemon.
- Continue using ad hoc strings across boundaries. Rejected where stable status/error contracts matter.
- Refactor unrelated modules for style. Rejected because this is a safety incident and scope must stay narrow.

## Decision: Preserve lessons as tests, docs, and targeted comments

**Rationale**: The incident exposed specific failure modes: invalid MediaWiki timestamp formatting, refresh-only source hooks, non-actionable `api-error` status, warning floods, and insufficient benchmark evidence. These should not remain only in chat or temporary feature notes. Durable lessons belong in regression tests, operator docs, implementation/runtime docs, and short comments where the local rule is surprising.

**Alternatives considered**:

- Keep lessons only in feature planning artifacts. Rejected because feature-local docs may later be removed after close-out.
- Add broad explanatory comments everywhere. Rejected because comments should be used only where they prevent a repeat bug or clarify a non-obvious protocol rule.
- Rely on commit history only. Rejected because operators and future maintainers need direct docs and tests.

## Decision: Serialize MediaWiki API timestamps without fractional precision

**Rationale**: Runtime analysis on 2026-04-25 showed bounded catch-up sending `rvstart` values with fractional nanoseconds, which MediaWiki rejects with `badtimestamp`. Recovery paths depend on timestamp parameters, so the daemon needs one shared serializer for MediaWiki API timestamps. The chosen shape is UTC second precision with no fractional component, suitable for `rvstart`, coverage windows, and similar API parameters.

**Alternatives considered**:

- Continue using `DateTime::to_rfc3339()`. Rejected because it can include fractional nanoseconds and has already failed against production.
- Format each API call locally. Rejected because one missed call site would reintroduce catch-up failure.
- Accept `badtimestamp` as a normal unresolved outcome. Rejected because it turns every page into a false unresolved exposure and floods the operator surface.

## Decision: Source-list edits trigger immediate bounded catch-up, not only cache refresh

**Rationale**: The current live hook sees edits to `Удзельнік:Wizardist/SuppressionList`, refreshes the cache, and returns. That updates the watched set eventually, but it does not inspect edits that already happened on pages newly added to the list. The fix should treat a successful source-list refresh as a recovery trigger: compute the newly added watched titles and run a bounded catch-up over those titles immediately. The same recovery semantics should apply when `Вікіпедыя:Запыты да схавальнікаў` changes and the configured window may contain newly requested pages.

**Alternatives considered**:

- Wait for the next live edit on each newly added page. Rejected because the exposed revision may already exist and require immediate hiding.
- Wait for current-day reconciliation. Rejected because its cadence is intentionally slower and cannot satisfy the live safety requirement.
- Always run a full catch-up over all watched pages after every source-list edit. Rejected as avoidable load; default should prioritize the delta while allowing a wider operator-triggered catch-up.

## Decision: Persist classified API failure evidence without sensitive payloads

**Rationale**: The TUI currently showed repeated decode warnings, and runtime status preserved only generic `api-error` for a failed live RevDel. Operators need to distinguish `badtimestamp`, JSON API errors, HTTP status failures, non-JSON responses, decode failures, auth/session blockers, and transient network errors. The persisted evidence should include compact error class, API code, HTTP status, content type, retryability, affected action, and a redacted short message, but not full response bodies, comments, hidden text, credentials, tokens, or cookies.

**Alternatives considered**:

- Persist raw API responses. Rejected because responses may include sensitive or high-volume payloads.
- Keep only `api-error`. Rejected because it is not actionable enough to diagnose live hiding failures.
- Log detailed errors only to stdout. Rejected because the TUI and state file are the operator's primary incident surface.

## Decision: Coalesce repeated catch-up warnings into summaries

**Rationale**: One root-cause failure can affect every watched page, producing thousands of nearly identical warnings in the terminal. The daemon should classify the first failure, count repeated failures by class, preserve a small sample of titles, and render a summary such as `1427 page queries failed: badtimestamp`. This keeps the operator surface readable while preserving enough detail for diagnosis.

**Alternatives considered**:

- Suppress warnings entirely. Rejected because failures must remain visible.
- Keep one warning per page. Rejected because the warning flood hides the actual issue and makes the TUI hard to use.
- Log only after catch-up finishes. Rejected because a long catch-up still needs progress and early failure visibility.

## Decision: Use the bot test page for external benchmark evidence

**Rationale**: The operator explicitly allowed `Удзельнік:Plaga med Bot/suppressor/tests` for manual and automated tests and benchmarks. This provides a safe production wiki surface for publish-to-hide timing evidence without using sensitive articles. Every automated edit to that page must be marked as a bot edit, and benchmark content/summaries must be clearly test-only.

**Alternatives considered**:

- Benchmark only with synthetic events. Rejected because it cannot prove end-to-end MediaWiki edit, stream, API, and RevDel behavior.
- Use arbitrary watched sensitive pages. Rejected because tests should avoid real sensitive subjects.
- Mutate `Удзельнік:Wizardist/SuppressionList` for every benchmark. Rejected because routine benchmarks should not churn the production source list; source-list behavior should be tested explicitly and separately.
