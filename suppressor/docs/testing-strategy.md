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
- source-list and request-page trigger helpers
- MediaWiki timestamp serialization and API failure classification
- source-cache watched-title diffing
- catch-up summary formatting without sensitive payloads
- catch-up warning aggregation without per-page log spam
- shared throttle/backoff status across live, catch-up, command, and reconciliation paths
- rolling `Last 24 hours` and nightly full-recheck scheduler semantics
- detached `server-start` parsing, preflight, duplicate PID refusal, startup timeout, and
  launch-path status checks
- command-report compatibility, bounded unresolved samples, and daemon-vs-command status separation
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
- MediaWiki API timestamp formatting for recovery query parameters
- compact runtime status fields for latest classified errors, source refresh, resource summaries,
  and coalesced warning summaries
- command-report isolation and TUI rendering for one-shot output
- recovery-anchor selection from `last_successful_hide_at`
- `server-start` startup evidence helpers

## Known Gaps

- no full live EventStreams-to-RevDel CI path
- no full real-TUI integration automation
- no broad live-wiki production simulation in CI
- no automated percentile proof for the production EventStreams path; p95/p99 evidence still needs a
  controlled run with at least 100 observations before release claims
- no automated proof that the rsynced binary survives SSH logout on the deployment host; T040 must
  record that manually
- no automated 10-minute deployment-host CPU/RSS/resource sample; T042 must record that manually

## Current Gate Evidence

- `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1`: passed with
  204 tests on 2026-05-06.
- `rtk cargo clippy --manifest-path suppressor/Cargo.toml --all-targets --all-features -- -D warnings`: passed.
- Wiremock-backed tests bind local loopback ports. In sandboxed agent runs they may fail with
  `Operation not permitted` unless the test command is allowed to bind local ports; rerun the same
  `rtk cargo test` gate with that permission before treating it as a code failure.
- `rtk make -C suppressor build-server`: passed on 2026-05-06 outside the sandboxed Zig cache
  restriction and produced `target/aarch64-unknown-linux-musl/release/suppressor`.

## Minimum Server Verification Path

Before deployment trust, rerun the serial suppressor test gate after daemon-critical edits, rerun
`make build-server` after build-input edits, rsync the resulting binary, start it with
`./suppressor --config ./config.toml server-start`, reconnect to prove terminal logout survival,
run one controlled live or dry-run watched-edit smoke check, and record at least one 10-minute
deployment-host resource sample. Missing target-host evidence is a release blocker, not a CI
substitute.

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
- MediaWiki API timestamps now have a regression test for UTC second precision without fractional
  seconds.
- Repeated catch-up page-query failures now have a regression test proving root-cause aggregation
  and bounded safe title samples.
- Source-list cache diffing now has regression coverage for added, removed, unchanged, and
  redirect-derived watched-title sets.
- Reconciliation page failures now have regression coverage proving per-page failures coalesce into
  bounded warnings, set backoff evidence, and leave scheduled verification failed instead of
  falsely completed.
- Stream reopen now has regression coverage proving stale full-recheck freshness is not cleared by
  unrelated fresh stream evidence.
- Command and TUI report tests cover `Last 24 hours` preset wiring, bounded command reports,
  unresolved revision links, next actions, and command output that stays distinct from daemon-owned
  realtime status.

## Testing Rule

Add or update tests whenever a change affects:

- config or env parsing
- auth or rights expectations
- queueing or retry behavior
- reconciliation logic
- operator control flow
