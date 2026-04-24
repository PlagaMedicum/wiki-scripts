---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current suppressor testing strategy and maintained test story.
  source: .specify/doc-registry.json
---

# Suppressor Testing Strategy


## Test Layers

### Unit And Subsystem Tests

- config loading
- auth and right checks
- cache shaping and persistence
- runtime assembly helpers
- queue and worker behavior
- realtime status serialization and backward compatibility
- stream resume and silent-starvation decisions
- catch-up summary formatting without sensitive payloads
- TUI support helpers

### Boundary Tests

- mocked MediaWiki API requests
- config and state persistence
- RevDel request safety for public `user|comment` only

## Strongest Coverage

`suppressor` is strongest at:

- deterministic config handling
- right verification
- API contract checks
- cache/state persistence
- local runtime helper behavior
- realtime runtime status persistence
- CLI parsing for emergency catch-up and coverage commands

## Known Gaps

- no full live EventStreams-to-RevDel CI path
- no full real-TUI integration automation
- no broad live-wiki production simulation in CI
- no automated percentile proof for the production EventStreams path; p95/p99 evidence still needs a
  controlled run with at least 100 observations before release claims

## Current Gate Evidence

- `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1`: passed with 64 tests.
- `rtk cargo test --manifest-path suppressor/Cargo.toml`: passed with 64 tests.
- `rtk cargo clippy --manifest-path suppressor/Cargo.toml --all-targets --all-features -- -D warnings`: passed.
- Wiremock-backed tests bind local loopback ports. In sandboxed agent runs they may fail with
  `Operation not permitted` unless the test command is allowed to bind local ports; rerun the same
  `rtk cargo test` gate with that permission before treating it as a code failure.

## Incident Grounding

The implementation was grounded in the code audit finding that the previous EventStreams loop could
wait indefinitely on `stream.next().await` and only reconnect on explicit stream errors or EOF. The
fix adds a configured silence watchdog and records stale/reconnecting/unhealthy realtime states.

Alternate incident causes were also inspected and covered in the implementation path:

- Last-Event-ID invalid/resume errors now mark recovery triggers and run bounded catch-up.
- watched-title/cache changes still refresh the source list, but cache reload is no longer treated
  as realtime recovery.
- queue dispatch and worker outcomes now update runtime status for queued, hidden, failed, and
  blocked states.
- rights/session failures persist a blocked realtime state before the worker exits fail-closed.

## Testing Rule

Add or update tests whenever a change affects:

- config or env parsing
- auth or rights expectations
- queueing or retry behavior
- reconciliation logic
- operator control flow
