---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current suppressor implementation contract at the documented scope.
  source: .specify/doc-registry.json
---

# Suppressor Implementation


## Purpose

The daemon:

- consumes Wikimedia EventStreams recent-change data
- matches revisions against the watched-title set
- performs public RevDel for `user|comment`
- maintains reconciliation and backfill state

## Current Non-Goals

- full suppression workflows
- broader moderation-platform behavior
- remote control as a product surface

## Current Behavior

- one daemon worker path for live and bounded catch-up handling
- EventStreams live handling with a silence watchdog
- bounded catch-up for startup, reconnect, stale-stream recovery, and operator commands
- source-list edits refresh the cache, diff watched titles, and start title-scoped catch-up for newly added titles
- request-page edits start immediate recent-window catch-up over the current watched set
- MediaWiki API timestamps are serialized through one UTC second-precision formatter
- repeated catch-up API failures are classified and coalesced by root cause
- runtime status with a dedicated realtime health section
- reconciliation and backfill support
- local cache and local state persistence
- strict right checks before live operation
- process same-account edits too

Realtime status records stream freshness, last observed target-wiki event, last watched-page match,
last queued action, last completed action, latest outcome, recovery trigger, and catch-up summary.
This keeps process liveness separate from realtime protection effectiveness.

## Current Deployment Model

- Linux-first
- one system
- one local operator TUI
- current production baseline aimed at be.wiki

## Safety Rules

- fail closed on unrecoverable auth or permission loss
- never log secrets or sensitive payloads
- keep RevDel requests limited to public `user|comment` metadata with `suppress=no`
- record skipped, already-hidden, failed, unresolved, and blocked outcomes distinctly
- keep current scope narrow unless a later approved spec changes it
- keep the reaction path fast enough that public metadata is hidden as quickly as possible

## Live And Recovery Boundaries

`stream.rs` owns EventStreams parsing, target-wiki filtering, watched-title matching, realtime
freshness updates, and watchdog-triggered reconnects. `catchup.rs` owns bounded window selection and
coverage accounting. `worker.rs` owns actual RevDel execution, retries, processed-revision
persistence, and fatal auth/permission blocking.

Nightly/current-day reconciliation remains a safety net. It must not be used as proof that the
sub-second realtime path is healthy.

## Internal Service Boundaries

- `stream.rs`: stream connection lifecycle, source-page/request-page trigger detection, source
  refresh orchestration, and live candidate routing.
- `cache/`: suppression-list parsing, redirect-enriched watched-title cache, and watched-title
  diffing.
- `catchup.rs`: bounded recovery windows, optional title scopes, per-revision accounting, and
  warning aggregation.
- `mw_api.rs`: MediaWiki transport, shared timestamp formatting, response parsing, retryability, and
  safe API failure classification.
- `runtime.rs` and `state.rs`: bounded queue status, source-refresh snapshots, latest classified
  errors, recovery summaries, and local JSON compatibility.
- `worker.rs`: RevDel submission, retry/relogin/token-refresh flow, final outcome recording, and
  blocked-state persistence.
- `tui_status.rs` and `tui_view.rs`: read-only local status collection and compact operator
  rendering.

These are internal ownership boundaries inside one local daemon/TUI deployment. They are the
intended microservice-style architecture for this tool; adding separate OS services would need a
separate justification because it increases overhead and deployment failure modes.

## API And Warning Contracts

MediaWiki API timestamp parameters must be formatted as UTC seconds, for example
`2026-04-25T08:58:18Z`. Do not call `to_rfc3339()` directly for API query parameters because it may
include fractional seconds.

API failures are reduced to `ApiFailureSnapshot`: class, API code, HTTP status, content type,
retryability, operation, safe sample title/revision, and a short redacted message. Response bodies,
cookies, tokens, hidden text, and raw comments are not persisted.

Catch-up does not log one warning per watched title for the same transport/API failure. It counts
failures by classified root cause and preserves only the configured number of safe sample titles.
