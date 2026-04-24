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
