# Suppressor Runtime Boundaries


## Current Reality

`suppressor` is a single Rust daemon with small local CLI control commands and one additive
detached binary launch path for rsync server deployment.

That shape is intentional:

- one runtime for the automation logic
- one local command surface for the operator
- one current deployment target on one system

## Core Runtime Areas

- `app.rs` / `cli.rs`: CLI parsing and dispatch
- `command_context.rs`: shared command config/path loading interface
- `commands.rs`: direct auth, hide, signal, and effective-config command controllers
- `coverage_command.rs`: bounded emergency catch-up, coverage, and command-report controller
- `server_start.rs`: detached supervisor controller and startup proof checks
- `status_command.rs`: read-only operator status, health, performance, and recent-edit inspection
- `daemon.rs`: production daemon lifecycle, recentchanges polling, priority gating, and launch-path
  snapshots
- `runtime.rs`: command/recovery runtime assembly used by coverage and one-shot service paths
- `daemon/background.rs`: bounded low-priority source refresh and history-sweep worker
- `daemon_backlog.rs`: production daemon pending/quarantine state and retry bookkeeping
- `daemon_windows.rs`: startup catch-up and live polling window selection
- `auth.rs` / `mw_api.rs`: auth and MediaWiki transport
- `catchup.rs`: candidate-first bounded recovery and accident-window accounting
- `reconcile.rs`: watched-set verification and reconciliation
- `worker.rs`: queued RevDel execution
- `cache/`: watched-title cache loading and persistence
- `state.rs`: local durable state
- status/control commands read state and send bounded operator signals; they do not own daemon
  logic

## Service Shape

The code is organized as small internal services inside one binary. This is the local version of
microservice architecture: each module owns a domain, communicates through typed interfaces, and
does not import presentation details from controllers.

- controllers: `app.rs`, `cli.rs`, `commands.rs`, `coverage_command.rs`, `server_start.rs`, and
  `status_command.rs`
- domain services: live detection, cache, catch-up, worker, scheduler, reconciliation, runtime state
- gateways: MediaWiki API, auth, local JSON state, signals, metrics, and logs

Controllers may call services and render operator output. Services may emit typed snapshots,
reports, logs, and metrics. Services must not call controller rendering code.

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
- bounded live and background in-memory queues

## Execution Lanes

The daemon remains one process, but RevDel work has two explicit internal lanes:

- `live` owns recentchange-triggered watched edits.
- `background` owns recovery catch-up, reconciliation, rolling last-24h verification, nightly full
  recheck, manual coverage, and one-shot command work.

The live lane must never wait for the background lane to drain before it can accept, submit, or
visibly reject a watched edit. The background lane is separately bounded and its concurrency stays at
or below the reviewed API cap. Runtime status exposes both lanes with queue depth, capacity,
in-flight count, concurrency limit, and latest saturation metadata.

Local transactions are intentionally short: duplicate/processed checks, queued status, submit
status, completion status, and processed-revision persistence are separate local transitions. No
runtime-status, queue, or processed-revision lock is held across MediaWiki API calls, retry sleeps,
page scans, or reconciliation sleeps.

## Scope Rules

- keep `suppressor` narrow
- keep current deployment local-first
- keep daemon/runtime logic separate from command rendering
- keep service interfaces small enough that one domain can be edited without loading the whole
  daemon
- keep logs and metrics at the edges
- keep realtime health separate from daemon process health and reconciliation progress
- keep daemon-owned `runtime_status.json` separate from one-shot `command_report.json`
- keep emergency catch-up bounded by configured windows and revision limits
- prefer `last_successful_hide_at` as the recovery anchor when it exists, and label any fallback
  recent emergency window explicitly
- keep source-list/request-page recovery inside the polling/cache/catch-up boundaries instead of
  routing it through nightly reconciliation
- keep rolling `Last 24 hours` verification distinct from nightly full watched-set recheck
- keep API errors compact and classified; do not persist response bodies or sensitive payloads
- keep classified auth/permission failures process-alive and operator-visible as blocked
  protection
- keep polling freshness authoritative for healthy realtime trust; retained stream observer evidence
  may help diagnose gaps, but it must not restore healthy status on its own
- keep retained observer cursor and local state persistence failures non-healthy until a retry
  succeeds or the operator fixes the state path
- query bounded recentchanges before ordinary recovery full scans, and record an explicit fallback
  reason whenever a full watched-set scan is used outside explicit full verification
- coalesce repeated warning causes before they reach the operator surface
- surface shared throttle/backoff as degraded or unhealthy protection until the affected live,
  recovery, command, or reconciliation path has later successful evidence
- surface live-lane saturation or deadline expiry as non-healthy live protection instead of a silent
  queue wait
- trust `server-start` only when the PID file, daemon-owned status, launch-path label, and detached
  log path agree for that detached child
- do not broaden the service unless there is a strong operational reason

Backlog and future slices live in the repo-level `docs/plan.md`; this file documents current
behavior.
