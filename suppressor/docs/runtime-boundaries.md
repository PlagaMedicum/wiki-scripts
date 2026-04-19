---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current suppressor runtime boundaries and architectural constraints.
  source: .specify/doc-registry.json
---

# Suppressor Runtime Boundaries


## Current Reality

`suppressor` is a single Rust daemon with one local supervisor TUI.

That shape is intentional:

- one runtime for the automation logic
- one local control surface for the operator
- one current deployment target on one system

## Core Runtime Areas

- `app.rs` / `cli.rs` / `commands.rs`: CLI dispatch and one-shot commands
- `daemon.rs` / `runtime.rs`: daemon lifecycle and runtime assembly
- `auth.rs` / `mw_api.rs`: auth and MediaWiki transport
- `stream.rs`: EventStreams ingestion
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
- `runtime_status.json`

Derived cache state:

- `suppression_list_cache.json`

Ephemeral coordination:

- PID file
- locks
- in-memory queues

## Scope Rules

- keep `suppressor` narrow
- keep current deployment local-first
- keep the daemon and the TUI separate
- keep logs and metrics at the edges
- do not broaden the service unless there is a strong operational reason

## Future Direction

Possible future work, not current implementation:

- multiwiki support
- stronger process separation only if it improves failure isolation or safety

Remote control or broader moderation-platform ambitions are not the default path.
