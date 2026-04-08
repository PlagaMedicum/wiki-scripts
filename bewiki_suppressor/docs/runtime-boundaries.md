# Runtime Boundaries

Navigation: [README](../README.md) | [Docs index](README.md) | [Architecture analysis](architecture-analysis.md) | [Operations spec](../specs/operations.md)

This document explains the post-refactor runtime shape. It is not a speculative design note. It describes the boundaries the crate currently tries to maintain.

## Architecture Map

- `app.rs`: CLI parse and top-level dispatch only.
- `commands.rs`: one-shot command handlers such as `check-auth`, `hide-revid`, and signal-posting commands.
- `effective_config.rs`: CLI-facing rendering for `print-effective-config`, including secret redaction.
- `daemon.rs`: top-level daemon lifecycle and shutdown.
- `runtime.rs`: shared runtime assembly, resolved paths, loaded state, the shared `ActionDispatcher`, the narrower `ReconciliationRuntime`, and `ReconcilePassContext` for one reconciliation pass.
- `cache.rs`: public cache façade.
- `cache/model.rs`: pure cache snapshot shaping and runtime projection.
- `cache/store.rs`: explicit cache persistence, bootstrap, and refresh policy orchestration.
- `cache/source.rs`: MediaWiki source-page and redirect fetch execution.
- `stream.rs`: EventStreams connection, resume/backoff behavior, and live-candidate submission.
- `scheduler.rs`: metadata refresh, nightly reconciliation scheduling, and current-day recheck scheduling.
- `signal_control.rs`: Unix-signal listeners and daemon-side manual control handling.
- `worker.rs`: queued `revisiondelete` execution and processed-revision persistence.
- `tui.rs`: supervisor event loop, action handling, managed child-process lifecycle, and supervisor state.
- `tui_status.rs`: supervisor reads of local state files.
- `tui_process.rs`: child-process command construction and captured log piping.
- `tui_view.rs`: terminal rendering only.

## State Categories

### Human-Owned Config

- `config.toml`
- non-secret runtime policy in `AppConfig`

This is operator-authored and should change rarely.

### Derived Runtime Paths

- `RuntimePaths`
- resolved path layout derived from `config.toml` plus the config file location

This is generated at bootstrap and should not be hand-authored.

### Secrets And Env

- local `.env`
- process env overrides
- loaded secret/runtime endpoint material in `EnvConfig`

This is never committed and never rendered without redaction.

### Durable Operational State

- `last_event_id.txt`
- `processed_revids.json`
- `nightly_sweep_progress.json`
- `runtime_status.json`

This is machine-managed state that affects daemon recovery or operator visibility across restarts.

### Derived Cache State

- `suppression_list_cache.json`
- redirect-derived watched-set material inside that cache

This is persisted for speed and continuity, but it is derived from source page data plus reconciliation.

### Ephemeral Coordination

- in-memory revision locks
- in-memory page locks
- in-memory work queue depth
- managed supervisor child-process handles
- `daemon.pid`

This coordinates live execution. Some of it is persisted only as a local coordination aid, not as business state.

## Current Rules

- Downstream runtime code should receive `RuntimePaths` instead of resolving file paths ad hoc.
- Reconciliation entry points should stay on `ReconciliationRuntime`, but each pass should execute against `ReconcilePassContext` plus explicit immutable inputs.
- Revision queueing rules should stay behind `ActionDispatcher` instead of being reimplemented at individual call sites.
- The TUI is a supervisor around the daemon, not an alternate daemon implementation.
- Cache reload and redirect-enrichment code may persist derived cache state, but they should not own operator config decisions.
- New daemon behavior should land in the dedicated runtime modules first, not back in `app.rs`.

## Remaining Debt

- `runtime.rs` is still a broad composition root and shared runtime bag, even after the pass-context extraction.
- `config.rs` still owns config parsing, env loading, and logging bootstrap.
- Effective-config rendering is a CLI-facing presentation concern and should not be treated as config-policy logic.
- `tui.rs` is correctly a supervisor client now, but it still centralizes the event loop and managed child-process lifecycle.

Those are the next cuts if the crate keeps growing, but they are not urgent enough to justify another large refactor immediately.

Next document: [Architecture analysis](architecture-analysis.md)
