---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current suppressor runtime boundaries and architectural constraints.
  source: .specify/doc-registry.json
---

# Suppressor Runtime Boundaries


## Current Reality

`suppressor` is a single Rust daemon with one local supervisor TUI and one additive detached binary
launch path for rsync server deployment.

That shape is intentional:

- one runtime for the automation logic
- one local control surface for the operator
- one current deployment target on one system

## Core Runtime Areas

- `app.rs` / `cli.rs` / `commands.rs`: CLI dispatch and one-shot commands
- `daemon.rs` / `runtime.rs`: daemon lifecycle, launch-path snapshots, and runtime assembly
- `auth.rs` / `mw_api.rs`: auth and MediaWiki transport
- `stream.rs`: EventStreams ingestion
- `catchup.rs`: bounded recovery and accident-window accounting
- `scheduler.rs` / `reconcile.rs`: scheduling and reconciliation
- `worker.rs`: queued RevDel execution
- `cache/`: watched-title cache loading and persistence
- `state.rs`: local durable state
- `tui*.rs`: local TUI supervision

## State Categories

Human-owned config:

- `config.toml`

Secrets and environment input:

- `.env`
- process env overrides

Durable operational state:

- `last_event_id.txt`
- `processed_revids.json`
- `nightly_sweep_progress.json`
- `runtime_status.json`, including daemon, realtime, latest outcome, latest classified error,
  source-refresh summary, coalesced warning summaries, resource-economy snapshot, catch-up summary,
  and reconciliation status
- `command_report.json` for the last bounded one-shot command result; it is not daemon realtime
  truth

Derived cache state:

- `suppression_list_cache.json`

Ephemeral coordination:

- PID file
- detached `server-start` log
- locks
- in-memory queues

## Scope Rules

- keep `suppressor` narrow
- keep current deployment local-first
- keep the daemon and the TUI separate
- keep logs and metrics at the edges
- keep realtime health separate from daemon process health and reconciliation progress
- keep daemon-owned `runtime_status.json` separate from one-shot `command_report.json`
- keep emergency catch-up bounded by configured windows and revision limits
- prefer `last_successful_hide_at` as the recovery anchor when it exists, and label any fallback
  recent emergency window explicitly
- keep source-list/request-page recovery inside the stream/cache/catch-up boundaries instead of
  routing it through nightly reconciliation
- keep rolling `Last 24 hours` verification distinct from nightly full watched-set recheck
- keep API errors compact and classified; do not persist response bodies or sensitive payloads
- coalesce repeated warning causes before they reach the operator surface
- surface shared throttle/backoff as degraded or unhealthy protection until the affected live,
  recovery, command, or reconciliation path has later successful evidence
- trust `server-start` only when the PID file, daemon-owned status, launch-path label, and detached
  log path agree for that detached child
- do not broaden the service unless there is a strong operational reason

## Future Direction

Possible future work, not current implementation:

- multiwiki support
- stronger process separation only if it improves failure isolation or safety

Remote control or broader moderation-platform ambitions are not the default path.
