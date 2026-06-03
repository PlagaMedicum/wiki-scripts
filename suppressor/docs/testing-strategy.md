# Suppressor Testing Strategy


## Test Layers

### Unit And Subsystem Tests

- config loading
- auth and right checks
- cache shaping and persistence
- runtime assembly helpers
- live/background lane dispatch, queue saturation, deadline, and worker behavior
- process-alive RevDel auth/permission blocking
- local state persistence failure status, including retained cursor writes
- bounded latency snapshots for observed-to-queue, queue-to-submit, submit-to-complete, and
  observed-to-hidden
- realtime status serialization and backward compatibility
- recentchanges polling overlap, dedupe, and freshness decisions
- source-list and request-page trigger helpers
- MediaWiki timestamp serialization and API failure classification
- source-cache watched-title diffing
- catch-up summary formatting without sensitive payloads
- catch-up warning aggregation without per-page log spam
- candidate-first catch-up discovery and full-scan fallback reasons
- shared throttle/backoff status across live, catch-up, command, and reconciliation paths
- rolling `Last 24 hours` and nightly full-recheck scheduler semantics
- detached `server-start` parsing, preflight, duplicate PID refusal, startup timeout, and
  launch-path status checks
- command-report compatibility, bounded unresolved samples, and daemon-vs-command status separation
- status, health, performance, and signal command helpers

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
- MediaWiki API timestamp formatting for recovery query parameters
- compact runtime status fields for latest classified errors, source refresh, resource summaries,
  and coalesced warning summaries
- command-report isolation and CLI rendering for one-shot output
- recovery-anchor selection from `last_successful_hide_at`
- `server-start` startup evidence helpers
- live-priority local tests for blocked background work, synthetic bursts, deadline deferral, and
  lane-aware runtime status

## Known Gaps

- no full live recentchanges-polling-to-RevDel CI path
- no terminal UI integration automation because the operator surface is plain CLI
- no broad live-wiki production simulation in CI
- no automated percentile proof for the production recentchanges polling path; local tests prove
  bounded synthetic p50/p95/p99 snapshots, but target-host release claims still need controlled live
  or dry-run observations
- no automated proof that the rsynced binary survives SSH logout on the deployment host; T040 must
  record that manually
- no automated 10-minute deployment-host CPU/RSS/resource sample; T042 must record that manually

## Current Gate Evidence

- Before daemon refactors, preserve these behavior surfaces unless the operator explicitly approves
  a behavior change: recentchanges polling, public `user|comment` RevDel scope, pending retry,
  quarantine, bounded startup/manual catch-up windows, signal commands, supervisor restart evidence,
  runtime-status schema, and command-report isolation.
- In managed agent runs, use the direct `rtk` refactor gate: `rtk cargo fmt --check`,
  `rtk cargo clippy --all-targets --all-features -- -D warnings`,
  `rtk cargo test -- --test-threads=1`, and `rtk git diff --check`. Passing it proves local
  regression coverage only; deployment confidence still needs target-host evidence.
- `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1`: passed with
  223 tests on 2026-05-14 for the polling-first, crash-resilient source tree.
- `rtk cargo clippy --manifest-path suppressor/Cargo.toml --all-targets --all-features -- -D warnings`: passed.
- Wiremock-backed tests bind local loopback ports. In sandboxed agent runs they may fail with
  `Operation not permitted` unless the test command is allowed to bind local ports; rerun the same
  `rtk cargo test` gate with that permission before treating it as a code failure.
- `rtk make -C suppressor build-server`: passed on 2026-05-14 outside the sandboxed Zig cache
  restriction and produced `target/aarch64-unknown-linux-musl/release/suppressor`.

## Minimum Server Verification Path

Before deployment trust, rerun the serial suppressor test gate after daemon-critical edits, rerun
`make build-server` after build-input edits, rsync the resulting binary, start it with
`./suppressor --config ./config.toml server-start`, reconnect to prove terminal logout survival,
run one controlled live or dry-run watched-edit smoke check while background work is active or
queued, and record at least one 10-minute deployment-host resource sample. Missing target-host
evidence is a release blocker, not a CI substitute.

## Incident Grounding

The implementation was grounded in the code audit finding that the previous EventStreams-first loop
could wait indefinitely on `stream.next().await` and only reconnect on explicit stream errors or
EOF. The current MVP hotfix instead makes recentchanges polling authoritative for healthy-state
truth and keeps retained observer evidence secondary.

Alternate incident causes were also inspected and covered in the implementation path:

- Last-Event-ID invalid/resume errors now mark recovery triggers and run bounded catch-up.
- watched-title/cache changes still refresh the source list, but cache reload is no longer treated
  as realtime recovery.
- queue dispatch and worker outcomes now update runtime status for queued, hidden, failed, and
  blocked states.
- live/background lane tests prove live work can complete while synthetic background
  reconciliation remains queued, a full live lane records non-healthy status, an expired live
  deadline records retrying `deadline-exceeded`, and a burst of 10 synthetic watched edits produces
  bounded p50/p95/p99 live latency evidence.
- rights/session failures persist a blocked realtime state without exiting the daemon process.
- local state persistence failure, including retained cursor writes, records `state-persistence` and
  reuses the bounded retained-observer reconnect path instead of ending the compatibility task or
  falsely restoring healthy live protection.
- ordinary no-title-scope catch-up queries recentchanges first, filters by watched-title cache, and
  records candidate counts plus fallback reasons before any full watched-set scan.
- MediaWiki API timestamps now have a regression test for UTC second precision without fractional
  seconds.
- Repeated catch-up page-query failures now have a regression test proving root-cause aggregation
  and bounded safe title samples.
- Source-list cache diffing now has regression coverage for added, removed, unchanged, and
  redirect-derived watched-title sets.
- Reconciliation page failures now have regression coverage proving per-page failures coalesce into
  bounded warnings, set backoff evidence, and leave scheduled verification failed instead of
  falsely completed.
- Retained observer reopen now has regression coverage proving stale full-recheck freshness is not
  cleared by unrelated fresh transport evidence.
- Command report tests cover `Last 24 hours` preset wiring, bounded command reports,
  unresolved revision links, next actions, and command output that stays distinct from daemon-owned
  realtime status.

## Testing Rule

Add or update tests whenever a change affects:

- config or env parsing
- auth or rights expectations
- queueing or retry behavior
- reconciliation logic
- operator control flow
