# Suppressor Implementation


## Purpose

The daemon:

- polls MediaWiki recentchanges as the authoritative live detector
- matches revisions against the watched-title set
- performs public RevDel for `user|comment`
- maintains reconciliation and backfill state

## Current Non-Goals

- full suppression workflows
- broader moderation-platform behavior
- remote control as a product surface

## Current Behavior

- separate bounded live and background RevDel execution lanes inside one daemon process
- recentchanges live polling with overlap dedupe and watched-title filtering
- retained EventStreams observer compatibility kept out of healthy-state truth
- bounded catch-up for startup, reconnect, stale-poll recovery, and operator commands
- source-list edits refresh the cache, diff watched titles, and start title-scoped catch-up for newly added titles
- request-page edits start immediate recent-window catch-up over the current watched set
- recovery defaults to `last_successful_hide_at` when present and labels fallback recent windows
  explicitly
- rolling `Last 24 hours` verification and nightly full watched-set recheck are separate scheduler
  scopes with separate operator evidence
- MediaWiki API timestamps are serialized through one UTC second-precision formatter
- repeated live, catch-up, command, and reconciliation API failures are classified and coalesced by
  root cause
- shared throttle/backoff state feeds runtime status so blocked recovery or verification cannot
  appear healthy while live protection or operator commands are affected
- one-shot command reports persist to bounded `command_report.json` instead of overwriting
  daemon-owned realtime truth
- `server-start` launches the deployed binary as a detached child and verifies PID/runtime/log
  evidence before printing success
- runtime status with a dedicated realtime health section
- lane-aware runtime status for live/background queue depth, queue cap, in-flight count, saturation
  metadata, action deadlines, submitted timestamps, and recent p50/p95/p99 live timing samples
- reconciliation and backfill support
- local cache and local state persistence
- strict right checks before live operation
- process operator-account edits too

Realtime status records polling-backed freshness, last observed target-wiki event, last watched-page
match, last queued action, last completed action, latest outcome, recovery trigger, and catch-up
summary. This keeps process liveness separate from realtime protection effectiveness.

## Current Deployment Model

- Linux-first
- one system
- one local operator CLI
- current production baseline aimed at be.wiki

## Safety Rules

- fail closed on unrecoverable auth or permission loss by blocking protection in status while the
  daemon stays alive for operator evidence
- never log secrets or sensitive payloads
- keep RevDel requests limited to public `user|comment` metadata with `suppress=no`
- record skipped, already-hidden, failed, unresolved, and blocked outcomes distinctly
- keep current scope narrow unless a later approved spec changes it
- keep the reaction path fast enough that public metadata is hidden as quickly as possible

## Live And Recovery Boundaries

`daemon.rs` owns production recentchanges polling, overlap dedupe, target-wiki filtering,
watched-title matching, source-page/request-page trigger detection, priority gating, and realtime
freshness updates. `daemon/background.rs` owns low-priority source refresh, request-page recovery,
and newly added title history sweeps. `catchup.rs` owns bounded command recovery and coverage
accounting. `worker.rs` owns queued RevDel execution for the command/runtime service path.

Nightly/current-day reconciliation remains a safety net. It must not be used as proof that the
sub-second realtime path is healthy.

Live recentchange candidates enter the `live` lane. Catch-up, reconciliation, rolling verification,
nightly full recheck, manual coverage, and one-shot command work enter the `background` lane. Live
enqueue uses immediate bounded admission: when the live lane is full, the daemon records unhealthy
live protection with a saturation reason instead of waiting behind queued work. Live actions carry a
short deadline and record retrying `deadline-exceeded` when the current attempt should no longer
hold the lane.

Classified RevDel auth or permission failures are blocked protection, not process-fatal runtime
events. The worker records the compact failure snapshot, blocked action outcome, and actionable
issue, then keeps the daemon alive so `runtime_status.json` and logs remain fresh.

Local live-detector state persistence is also treated as runtime evidence. Retained `last_event_id`
writes create parent directories where possible; remaining write or rename failures record
`state-persistence`, keep realtime status non-healthy, and reopen the retained observer through
bounded backoff. This is compatibility evidence only: authoritative polling remains the live path
that determines whether protection is healthy now.

Ordinary startup and emergency catch-up are candidate-first. The recovery path queries bounded
recentchanges for the selected window, filters by the normalized watched-title cache, and records
candidate source/counts/chunks/elapsed time. The older full watched-set scan is allowed only with an
explicit fallback reason or for explicit full verification work.

Report-only coverage must not classify recentchanges candidates as unresolved from recentchanges
alone. Recentchanges does not include RevDel hidden-state flags, so report-only mode must verify the
revision by id before counting it as visible exposure. Already-hidden revisions belong in
`already_hidden`, not in unresolved samples.

## Internal Service Boundaries

- `daemon.rs`: production daemon lifecycle, recentchanges polling, priority gating, and live
  candidate routing.
- `daemon/background.rs`: low-priority source refresh, request-page recovery, and history sweeps.
- `status_command.rs`: read-only status, health, performance, and recent-edit command controller.
- `cache/`: suppression-list parsing, redirect-enriched watched-title cache, and watched-title
  diffing.
- `command_context.rs`: shared config/path loading for command controllers.
- `server_start.rs`: detached supervisor launch, startup verification, and non-secret launch
  receipt rendering.
- `coverage_command.rs`: bounded coverage and emergency catch-up command orchestration plus
  `command_report.json` persistence.
- `commands.rs`: direct operator commands for auth, one-revision hiding, shared control requests, and
  effective config rendering.
- `daemon_backlog.rs`: production daemon pending/quarantine state, retry timing, unresolved
  summaries, and processed-revision defaults.
- `catchup.rs`: bounded recovery windows, optional title scopes, per-revision accounting, safe
  unresolved revision links, next-action text, and warning aggregation.
- `mw_api.rs`: MediaWiki transport, shared timestamp formatting, response parsing, retryability, and
  safe API failure classification.
- `runtime.rs` and `state.rs`: lane dispatch, bounded queue status, shared backoff, source-refresh
  snapshots, latest classified errors, recovery summaries, command-report contracts, latency
  snapshots, and local JSON compatibility.
- `worker.rs`: RevDel submission, retry/relogin/token-refresh flow, final outcome recording, and
  blocked-state persistence.

These are internal ownership boundaries inside one local daemon deployment. They are the intended
microservice-style architecture for this tool; adding separate OS services would need a separate
justification because it increases overhead and deployment failure modes.

## API And Warning Contracts

MediaWiki API timestamp parameters must be formatted as UTC seconds, for example
`2026-04-25T08:58:18Z`. Do not call `to_rfc3339()` directly for API query parameters because it may
include fractional seconds.

API failures are reduced to `ApiFailureSnapshot`: class, API code, HTTP status, content type,
retryability, operation, safe sample title/revision, and a short redacted message. Response bodies,
cookies, tokens, hidden text, and raw comments are not persisted.

Catch-up and reconciliation do not log one warning per watched title for the same transport/API
failure. They count failures by classified root cause and preserve only the configured number of
safe sample titles. Repeated failures set shared backoff evidence and keep scheduled verification
failed or degraded until a later successful run clears it.

The runtime latency sample window is bounded. It records observed-to-queue, queue-to-submit,
submit-to-complete, and observed-to-hidden paths for live evidence. The older observed-to-hide
metric remains as a compatibility alias for observed-to-hidden.

## Scheduler And Launch Contracts

The daytime scheduler uses a rolling `now-24h .. now` window, not a calendar-day-from-midnight
window. The nightly scheduler is a full watched-set recheck and must stay labeled separately from
the rolling verification path. Retained observer reopen, idle status, or one fresh polled event
must not clear failed scheduled verification, stale full-recheck freshness, or shared backoff
evidence on their own.

The minimal polling daemon reports current lag from the latest successful poll. Operator status code
must preserve that polling lag instead of recomputing lag from the last watched edit timestamp; a
quiet wiki with no watched-page edits is not stale by itself. Launch-path compatibility checks must
also compare normalized paths so harmless spellings such as `././state/daemon.pid` and
`./state/daemon.pid` do not create false unhealthy status.

`server-start` is additive. It keeps `run`, `dry-run`, and optional systemd starts available, but
it provides the current detached server deployment path: prepare runtime parents, validate auth inputs without
printing secrets, refuse duplicate live daemons, detach stdout/stderr to a log, start a new
session, and wait until PID file plus daemon-owned `runtime_status.json` agree on a fresh
`launch_path=server-start`.
