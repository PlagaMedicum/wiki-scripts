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
