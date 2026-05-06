---
docmeta:
  status: draft
  review: feature-local
  purpose: Verification quickstart for real-time suppression recovery.
  source:
  - speckit-plan on 2026-04-29
  - speckit-plan stabilization update on 2026-05-05
  - speckit-plan human-review queue update on 2026-05-06
  - user approval on 2026-05-07
---

# Quickstart: Real-Time Suppression Recovery


## Verification Goal

Prove that the running suppressor:

- hides eligible watched-page edits automatically in realtime
- recovers missed coverage from the last successful hide after downtime or failure
- performs randomized rolling last-24h daytime verification and randomized nightly full rechecks
- shows truthful operator-first runtime status
- preserves or explicitly explains compatibility for the actual deployment path in use
- builds the aarch64 Linux musl server binary through the documented Makefile target before rsync
  deployment
- starts from the rsynced binary with one detached `server-start` command that survives closing the
  server terminal

Important architectural limit: the suppressor observes edits after MediaWiki publishes them.
Verification should minimize and measure publish-to-hide exposure, but it must not claim guaranteed
zero first-view prevention.

## Active MVP Critical Path

During the active human-safety freeze, do not spend time on unrelated tools, broad refactors, or
cosmetic UI work. Verify this path first:

1. Short suppressor test gate passes.
2. Server binary builds with `make build-server`.
3. Actual launch path starts the daemon on the host being protected, preferably through the
   one-command detached `server-start` path for the rsynced binary.
4. Live or controlled dry-run hiding path updates `last_successful_hide_at` or the equivalent dry-run
   outcome without waiting for reconciliation.
5. Recovery/reconciliation and nightly fallback are scheduled or running with truthful non-healthy
   status when blocked.
6. Rate-limit/backoff does not starve live hiding and does not show false healthy status.

## Local Evidence Recorded On 2026-05-05

- Baseline warning: previously generated task completion remains provisional. The current
  suppressor code is not production-ready until the actual deployed launch path, live or controlled
  dry-run watched edit, recovery, reconciliation, and nightly evidence pass.
- Makefile dry-run check passed:

```bash
rtk make -C suppressor -n build-server
```

Observed command:

```text
cargo zigbuild --release --target "aarch64-unknown-linux-musl"
server binary: target/aarch64-unknown-linux-musl/release/suppressor
```

- Local build prerequisites are present: `cargo-zigbuild 0.22.3` and `zig 0.15.2`.
- Focused `server-start` and launch-path status tests passed:
  `7 passed, 183 filtered out` for `server_start`; `1 passed, 189 filtered out` for
  `launch_path`.
- Suppressor serial test gate passed:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

Observed result:

```text
190 passed (5 suites)
```

- The first local `make build-server` attempt failed only because the sandbox blocked Zig cache
  writes under `~/.cache/zig`. Re-running with normal user cache access passed:

```bash
rtk make -C suppressor build-server
```

Observed result:

```text
Finished release profile [optimized] target(s) in 1m 28s
server binary: target/aarch64-unknown-linux-musl/release/suppressor
```

Verified artifact:

```text
suppressor/target/aarch64-unknown-linux-musl/release/suppressor
ELF 64-bit LSB executable, ARM aarch64, statically linked, stripped
size: 9.5M
```

- `server-start` is implemented as an additive binary command with `--dry-run`,
  `--status-timeout-seconds`, and `--log-file`. It validates config and auth inputs without printing
  secrets, refuses a live duplicate PID, removes only proven-stale PID markers, detaches the child
  into a new session, redirects stdout/stderr to the selected log, and prints success only after
  PID and daemon-owned `runtime_status.json` agree on a fresh `launch_path=server-start`.
- Actual server logout-survival verification is still pending. Do not treat the new launch path as
  production-proven until T040 records that the rsynced binary survives terminal logout and keeps
  updating daemon-owned status on the deployment host.

## Evidence Freshness And Expiry

The local test and server-build results above are useful snapshots, not permanent release evidence.
They expire for final MVP purposes after any daemon-critical edit to `suppressor/src/`,
`suppressor/tests/`, `suppressor/Cargo.toml`, `suppressor/Cargo.lock`, `suppressor/Makefile`, or
launch/build code.

T037 and T038 must be rerun after Phase 2, US1, and US2 daemon-critical changes are complete.
Rerunning only before those changes proves the earlier snapshot, not the final daemon. Docs-only
edits do not by themselves require the server binary to be rebuilt, but any docs change that alters
the authoritative command, config, launch, or release-evidence contract must be reflected before the
final go/no-go checklist is accepted.

## Phase 2 Local Evidence Recorded On 2026-05-06

- Shared backoff/status/server-start/reconciliation focused tests passed:
  `backoff` 11 passed, `stale_pid` 3 passed, `collect_status` 7 passed, `server_start` 9 passed,
  and `queued_reconciliation` 1 passed.
- Full serial suppressor test gate passed after the Phase 2 shared-backoff/status slice:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

Observed result:

```text
198 passed (5 suites)
```

- This is Phase 2 evidence only. It does not complete T037 because final T037/T038 evidence must be
  rerun after US1 and US2 daemon-critical changes are complete.

## US1 Local Evidence Recorded On 2026-05-06

- Watched recentchange and live-queue tests passed:
  `watched_revision` 5 passed and `live_queue` 2 passed.
- Live outcome and latency tests passed:
  `dispatch_action` 3 passed, `record_action_completed` 1 passed,
  `worker_marks_live_action` 1 passed, `last_successful_hide` 4 passed, `live_hide` 3 passed, and
  `latency` 2 passed.
- Source refresh and primary status rendering checks passed:
  `source_refresh` 4 passed, `populate_runtime_derivatives` 6 passed, and `status_lines` 3 passed.
- Full serial suppressor test gate passed after the US1 live-path slice:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

Observed result:

```text
201 passed (5 suites)
```

- This is local dry-run/unit evidence for US1. It does not replace the later deployment-host live or
  controlled dry-run smoke check required by T041.

## US2 And MVP Test/Build Evidence Recorded On 2026-05-06

- Recovery-anchor and stream-transition tests passed:
  `recovery` 14 passed, `stream` 30 passed, and `stream_open` 3 passed.
- Scheduler, verification, backoff, and status truth tests passed:
  `scheduler` 7 passed, `verification` 3 passed, `backoff` 12 passed, and `status` 30 passed.
- Reconciliation failure tests now prove repeated per-page verification failures are coalesced,
  preserve retry/backoff visibility, and mark last-24h verification as failed instead of completed:
  `reconciliation_failures` 1 passed and `current_day_page_failures` 1 passed.
- Stale full watched-set freshness evidence is preserved across stream reopen:
  `stale_full_recheck` 1 passed.
- Full serial suppressor test gate passed after Phase 2, US1, and US2 daemon-critical changes:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

Observed result:

```text
204 passed (5 suites)
```

- The first local `make build-server` attempt was blocked only by sandboxed Zig cache writes under
  `/home/plagamed/.cache/zig`. The approved normal-cache rerun passed:

```bash
rtk make -C suppressor build-server
```

Observed result:

```text
Finished release profile [optimized] target(s) in 1m 32s
server binary: target/aarch64-unknown-linux-musl/release/suppressor
```

Verified artifact:

```text
suppressor/target/aarch64-unknown-linux-musl/release/suppressor
ELF 64-bit LSB executable, ARM aarch64, statically linked, stripped
size: 10010264 bytes
```

- This completes local T037/T038 evidence for the current source tree. Any later daemon-critical
  edit to Rust source, tests, Cargo files, Makefile, or launch/build code expires this evidence.
- Config-stability review, deployment-host `server-start` logout survival, controlled watched-edit
  smoke evidence, and resource measurements remain pending for T039 through T042.

## US3 Local Evidence Recorded On 2026-05-06

- Command/report hardening was verified without Rust source edits in this pass, so the prior local
  T037/T038 source-tree evidence remained fresh at the time of this US3 check. Later maintained-doc
  edits still do not change the built binary, but any later Rust, Cargo, Makefile, or launch/build
  code edit expires T037/T038 again.
- Emergency catch-up default-window behavior passed:
  `default_recovery_window` 2 passed and `default_catchup` 2 passed.
- Command surface and command-report tests passed:
  `command` 38 passed, `catchup` 19 passed, `report` 20 passed, `unresolved` 4 passed, and
  `collect_status` 7 passed.
- `Last 24 hours` preset and TUI separation tests passed:
  `last_24` 5 passed, `tui` 24 passed, and `status_lines` 3 passed.
- This completes local US3 evidence for bounded emergency catch-up defaults, explicit
  `Last 24 hours` labeling without timestamp input, command-report compatibility, bounded
  unresolved samples, safe revision URLs, next-action rendering, and daemon-vs-command status
  separation.

## Maintained Docs Evidence Recorded On 2026-05-06

- Operator docs now name the current MVP launch path: build with `make build-server`, rsync
  `target/aarch64-unknown-linux-musl/release/suppressor`, then start on the server with
  `./suppressor --config ./config.toml server-start`.
- Runtime-boundary docs now distinguish daemon-owned `runtime_status.json` from one-shot
  `command_report.json`, name `server-start` PID/status/log evidence, and keep rolling
  `Last 24 hours` verification distinct from nightly full watched-set recheck.
- Implementation/testing docs now preserve the shared backoff contract, scheduler semantics,
  timestamp-formatting lesson, detached launch checks, command-report isolation, and the minimum
  server verification path.
- Docs workflow result:

```bash
rtk python3 tools/doc_workflow.py all
```

Observed result:

```text
Doc metadata lint failed:
  specs/002-fix-git-commit/checklists/requirements.md: missing YAML frontmatter
Doc metadata already in sync.
```

The blocker is the known inactive `002` metadata issue. It was not fixed during the active
suppressor freeze because it is outside `001-real-time-suppression`.

## Current MVP Go/No-Go Recorded On 2026-05-06

Decision: BLOCK target-host deployment trust until T040, T041, and T042 evidence is recorded.
T039 records the config-stability block and Q001 now approves path 1: target-host config migration
to the reviewed tracked baseline.

Current human-review packet:

- Q001 in [questions.md](questions.md) is answered: approve path 1.
- Use [review-queue.md](review-queue.md) as the index of pending human and maintainer actions.
- The urgent next action is RQ002/T040 evidence collection.

- ACCEPT local test evidence: `rtk cargo test --manifest-path suppressor/Cargo.toml --
  --test-threads=1` passed with `204 passed`.
- ACCEPT local server-build evidence: `rtk make -C suppressor build-server` produced the
  aarch64 Linux musl binary at `target/aarch64-unknown-linux-musl/release/suppressor`.
- ACCEPT local command/report evidence: emergency catch-up defaults, `Last 24 hours`,
  command-report compatibility, bounded unresolved samples, safe revision URLs, and daemon-vs-
  command status separation passed targeted tests.
- ACCEPT reviewed config path decision: Q001 approves path 1, and the human operator reports the
  server config was updated and the daemon was started.
- BLOCK config-stability launch evidence: non-secret `server-start` receipt, PID/runtime/log paths,
  daemon-owned status freshness, and terminal logout survival still need to be recorded before T040
  can be checked.
- BLOCK detached server-start deployment trust: target-host PID/runtime/log evidence and SSH
  logout-survival evidence are still missing.
- BLOCK live-hide deployment trust: no target-host live or controlled dry-run watched-edit smoke
  result is recorded yet.
- BLOCK recovery/reconciliation/nightly deployment trust: local scheduler and status tests pass,
  but target-host recovery, rolling last-24h verification, and nightly full-recheck evidence remain
  pending.
- BLOCK deployment-host resource trust: the required 10-minute daemon-alone and daemon-plus-TUI
  resource samples are not recorded yet.
- ROLLBACK/FALLBACK decision: if `server-start` creates a duplicate daemon, orphaned child, false
  healthy status, failed live-hide evidence, failed recovery evidence, or unacceptable resource
  growth, stop the newly started daemon when it can be identified safely, restore the last trusted
  binary/config/state workflow, and use the last trusted launch path or manual emergency catch-up
  until a corrected build passes this gate.

## Primary Status Questions

During verification, the primary status view should let a human answer these questions immediately:

- Is protection working now?
- What exact work is active right now?
- What is the truthful lag right now?
- When was the last successful hide, and for which revision?
- What is the latest actionable issue?
- How long has this daemon been running continuously?

If the TUI instead makes the operator infer that from resume-cursor JSON, checkpoint counters, or
ambiguous status jargon, the verification run should be treated as failed even if hiding still
works underneath.

## Local Development Checks

Run from the repository root unless noted.

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

If parallel instability is resolved during implementation, also run:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml
```

Run the repo docs gate before close-out:

```bash
rtk python3 tools/doc_workflow.py all
```

## Server Build Check

From the repository root:

```bash
rtk make -C suppressor build-server
```

The target wraps the previously used deployment build:

```bash
cargo zigbuild --release --target aarch64-unknown-linux-musl
```

Expected artifact:

```text
suppressor/target/aarch64-unknown-linux-musl/release/suppressor
```

Use that path as the rsync source after the test gate passes. Do not record server credentials,
tokens, cookies, or `.env` values in release evidence.

## Config Stability And Human Review Gate

Config is a stable operator contract. Do not change server config, tracked config, config schema,
defaults, environment variable names, config loading semantics, or deployment-required sections as
a background workaround.

Before accepting T040 launch evidence, record:

1. The config path used by the deployed binary.
2. Whether the server config matches the reviewed tracked baseline or is an operator-managed
   deployment config with a documented divergence.
3. The non-secret result of `./suppressor --config ./config.toml print-effective-config`, or the
   exact config/migration-needed diagnostic if config loading fails.
4. For any config-affecting change, the concrete motivation, explicit human review evidence,
   compatibility fixture or migration diagnostic, exact migration steps, rollback/fallback to the
   last trusted config, and post-change `server-start` verification.
5. The resolved Q001 answer from [questions.md](questions.md) and the matching
   [review-queue.md](review-queue.md) status update.
6. For approved path 1, the non-secret post-migration launch evidence: `server-start` receipt,
   PID/runtime/log paths, daemon-owned status freshness, and terminal logout survival.

The 2026-05-06 target-host failure `missing field realtime` blocks deployment trust until this gate
is resolved. Do not add `[realtime]` or any other section to the server config as an unreviewed
shortcut; either migrate through the reviewed evidence path or run a binary that fails safely with a
reviewed migration-needed diagnostic.

## T039 Config-Stability Evidence Recorded On 2026-05-06

Human review evidence: the human owner explicitly required that all config changes be motivated and
reviewed by a human before they are trusted. This is now a release-blocking rule from constitution
v1.8.0.

Target-host command and diagnostic:

```text
ubuntu@webtop:~/wiki-supressor/suppressor$ ./suppressor server-start
Error: Failed to parse config file config.toml

Caused by:
    TOML parse error at line 1, column 1
      |
    1 | [wiki]
      | ^
    missing field `realtime`
```

Recorded verdict:

- Config path: `config.toml` in the target-host deployment directory.
- Reviewed baseline: the tracked suppressor `config.toml` includes the current `[realtime]`
  timeout section.
- Documented divergence: the target-host config used by the command does not satisfy the current
  config schema because `[realtime]` is absent.
- Compatibility or migration decision: Q001 approved path 1 on 2026-05-07. The human operator
  reports that the server config was updated to the reviewed tracked baseline and the daemon was
  started. Deployment trust still waits for T040 launch evidence.
- No-background-edit confirmation: no tracked or target-host config edit is approved or performed
  as part of this evidence pass.
- Rollback/fallback: keep target-host deployment blocked; use the last trusted binary/config/state
  workflow if available or manual emergency catch-up while a reviewed fix is prepared.

Allowed next paths:

- Human-reviewed target-host config migration to the reviewed tracked baseline, including backup,
  exact changed fields, rollback/fallback, and post-migration `server-start` evidence.
- Human-reviewed backward-compatible loader or migration-needed diagnostic, including tests,
  rebuilt server binary, and target-host evidence before T040 launch trust.

Approved path and next evidence:

1. Q001 is answered: approve path 1.
2. Record the `server-start` receipt.
3. Record PID file, runtime-status path, and detached log path.
4. Confirm the runtime status is daemon-owned and fresh.
5. Confirm the daemon survives terminal logout.
6. Do not include credentials, `.env` values, cookies, tokens, or sensitive page content.

## Detached Server Start Check

After copying the binary to the server and placing `config.toml` plus `.env` or equivalent
environment secrets through the operator-controlled secret path, start the background daemon with one
binary command:

```bash
./suppressor --config ./config.toml server-start
```

Expected receipt:

```text
server-start.ok mode=live pid=<pid>
config=./config.toml
pid_file=./state/daemon.pid
runtime_status=./state/runtime_status.json
log=./state/daemon.log
launch_path=server-start
```

Verification:

1. Confirm Q001 in [questions.md](questions.md) is answered as approved path 1 and
   [review-queue.md](review-queue.md) has only T040 evidence pending.
2. Confirm the command creates required runtime directories but does not create, print, or persist
   credentials.
3. Confirm the printed PID is alive and matches the expected suppressor binary.
4. Confirm `runtime_status.json` is daemon-owned, updates within 10 seconds, and records
   `launch_path=server-start` or equivalent detached-binary wording.
5. Confirm daemon stdout/stderr goes to the printed log path, not the SSH terminal.
6. Close the SSH terminal and reconnect.
7. Confirm the PID is still alive and the status file continues updating.
8. If config, auth secrets, state/log paths, stale PID, duplicate live daemon, or startup status
   verification fail, treat the launch as failed; do not trust a partial or orphaned background
   process.

## Target Server Environment Assumptions

The documented MVP deployment assumes:

- A Linux host that can execute the rsynced
  `target/aarch64-unknown-linux-musl/release/suppressor` binary.
- A deployment directory containing the binary, `config.toml`, and an operator-controlled `.env` or
  equivalent environment source.
- Writable configured parents for the state directory, `daemon.pid`, `runtime_status.json`, cache
  files, and detached log path.
- Network access to be.wikipedia.org and an operator account with suppressor rights for live mode.
- A local shell is available to invoke `./suppressor --config ./config.toml server-start`, but
  systemd, tmux, screen, shell `&`, and `nohup` are not required and are not authoritative evidence
  for this path.

If any assumption is false, deployment evidence must either name the substitute target and
verification path explicitly or block production trust.

## Compatibility Approval Check

Before trusting a new version in the operator environment:

1. Confirm release evidence states whether the previously documented setup is still valid.
2. If not, confirm the evidence names the new authoritative verification path, the required human
   approval checkpoint, the operator migration steps, and the fallback or rollback path to the last
   trusted workflow.
3. Confirm stale or incompatible prior artifacts produce migration-needed or non-healthy diagnostics
   rather than a false healthy reading.

## Actual Launch-Path Check

1. Confirm whether this host is using:
   - a TUI-managed daemon child
   - a `systemd`-managed daemon
   - a `server-start` detached binary daemon
   - another explicit supervisor path
2. Treat only the actual launch path in use as authoritative for this run.
3. If the daemon is not running under `systemd`, do not treat `journalctl -u suppressor.service` as
   authoritative evidence.
4. Confirm `runtime_status.json` is the daemon-owned realtime surface and `command_report.json` is
   only the last bounded one-shot command result.
5. Confirm the PID named by the active runtime surface actually exists, and when possible confirm it
   matches the expected suppressor binary path for this workspace.
6. If the PID is gone or the runtime file clearly predates the last process exit, treat the status
   evidence as stale and fail verification immediately.

## Realtime Protection Check

1. Start the daemon in live or dry-run mode.
2. Confirm the primary status view shows one clear protection state row with PID and uptime.
3. Feed or simulate a watched-page recentchange event.
4. Confirm the status view updates:
   - current work
   - lag
   - last observed watched edit
   - last successful hide
   - latest actionable issue
5. Confirm a successful path hides the revision or, in dry-run mode, records exactly what would
   have been hidden.
6. Confirm the revision ID is rendered as a direct browser-openable link or URL.

## Recovery Anchor Check

1. Record the current `last_successful_hide_at`.
2. Simulate downtime, stream failure, or missed events after that point.
3. Restart or recover the daemon.
4. Confirm automatic recovery labels its scope as `since last successful hide` or another explicit
   trusted fallback anchor if the primary timestamp is unavailable.
5. Confirm the daemon does not declare healthy until edits in that scope are hidden or reported
   unresolved.
6. Confirm a reconnect without a real missed gap does not get mislabeled as full startup recovery.

## Daytime Rolling Last-24h Verification Check

1. Keep the daemon running through a randomized daytime scheduler interval.
2. Confirm a verification run occurs for a rolling `now-24h .. now` window, not a calendar-day
   window from midnight.
3. Confirm the operator surface records the exact covered window and distinguishes it from other
   recovery work.
4. Confirm the run remains bounded under repeated throttling and preserves compact warning summaries.
5. If the run fails or stops early, confirm the primary status view keeps that failure visible as a
   current issue instead of clearing back to `healthy` after an unrelated stream reopen.

## Nightly Full Recheck Check

1. Keep the daemon running through the configured night window.
2. Confirm a full watched-set recheck runs at a randomized night hour.
3. Confirm the operator surface names it as a full watched-set recheck, not as last-24h
   verification.
4. Confirm compatibility remains intact if new scheduler fields were added; otherwise confirm a
   migration notice exists.

## Reconciliation Freshness Truth Check

1. Inspect the operator surface after startup and after any scheduled verification attempt.
2. Confirm it exposes:
   - the latest daytime verification result
   - the latest full watched-set recheck result
   - oldest full-check age
   - stale-page count against the nightly target
3. Confirm a checkpoint map with stale pages does not read as “fully covered” merely because the
   daemon is currently idle or the stream is fresh.
4. Confirm a failed scheduled verification remains operator-visible until a later successful run
   clears it.

## Emergency Catch-Up Check

1. Trigger `Emergency catch-up`.
2. If a recovery anchor exists, confirm the command defaults to the anchor-to-now window.
3. Otherwise confirm it uses the bounded recent emergency window documented by config.
4. Confirm the command emits a bounded command report and does not overwrite daemon realtime truth.
5. Confirm unresolved items carry safe revision links and next actions.

## Coverage: Last 24 Hours Check

1. Trigger the `Last 24 hours` preset from the TUI or equivalent command path.
2. Confirm the report label is exactly `Last 24 hours`.
3. Confirm the output shows the exact rolling start and end timestamps.
4. Confirm the action does not crash because of missing timestamp input.
5. Confirm the result remains visibly distinct from an arbitrary timestamped coverage report.

## Source Refresh Check

1. Simulate an edit to `Удзельнік:Wizardist/SuppressionList`.
2. Confirm the operator surface shows:
   - whether the watched set changed
   - added and removed title counts
   - whether immediate catch-up started or was deferred
3. Simulate a request-page change for `Вікіпедыя:Запыты да схавальнікаў`.
4. Confirm the source-refresh outcome is visible and actionable, not a silent cache reload.

## Throttle And Backoff Check

1. Run mocked or controlled `HTTP 429` cases with and without `Retry-After`.
2. Confirm live, recovery, and verification paths classify the error consistently.
3. Confirm the primary status view shows degraded protection or backoff instead of a false healthy
   state.
4. Confirm repeated-root-cause failures stop or pause early and keep unresolved samples bounded.

## TUI Truthfulness Check

1. Open the TUI while the daemon is running.
2. Trigger a one-shot command such as emergency catch-up or last-24h coverage.
3. Confirm the primary status view still reflects daemon-owned realtime truth.
4. Confirm command logs and daemon logs are visibly distinct.
5. Confirm latest-follow mode shows the newest rendered rows even when log lines wrap.
6. Confirm secondary diagnostics do not push current protection state out of the primary view.

## Benchmark And Resource Check

1. Use the approved test page:

```text
Удзельнік:Plaga med Bot/suppressor/tests
```

2. Confirm benchmark edits are bot-marked and test-only.
3. Measure publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings.
4. Confirm runtime lag uses truthful wall-clock calculation and is not pinned to `0s`.
5. Measure idle and active CPU, memory, queue depth, state size, and warning-summary counts for the
   daemon alone and daemon plus TUI.
6. Confirm bounded-state behavior under repeated failure storms.

Minimum resource evidence for T042:

- Measure at least 10 minutes idle for daemon alone and daemon plus TUI.
- Measure one active sample that includes live handling plus recovery, reconciliation, or backoff.
- Record CPU percentage, RSS memory, live queue depth/cap, recovery or reconciliation queue
  depth/cap, API concurrency, `runtime_status.json` size, `command_report.json` size,
  `processed_revids.json` size, detached log growth rate, and coalesced-warning counts.
- Block release if API concurrency exceeds the default cap of 2 without documented approval, a queue
  reaches its cap without degraded status, `runtime_status.json` or `command_report.json` exceeds
  1 MiB, repeated-root-cause log growth exceeds 10 MiB/hour without mitigation, or any field keeps
  growing monotonically after the active sample returns idle.

## Deployment Go/No-Go And Rollback Gate

Accept the MVP deployment only when the final evidence bundle includes fresh T037 and T038 results,
passing `server-start` logout-survival evidence on the target host, one live or controlled dry-run
watched-edit smoke result, recovery-from-anchor evidence, rolling last-24h verification evidence,
nightly full-recheck evidence or a documented scheduled wait with non-healthy status while pending,
shared backoff evidence, T039 config-stability evidence, and T042 resource evidence within bounds.

Block the deployment if any of those checks fail, are stale, are local-only when deployment-host
evidence is required, or leave the daemon looking healthy while live hiding, recovery,
reconciliation, nightly, launch-path, or resource evidence is missing or failed.

Rollback or fall back when the new binary, config, state shape, or launch path creates a duplicate
daemon, orphaned child, false healthy status, missing live-hide evidence, failed recovery evidence,
unreviewed config requirement, config migration failure, or unacceptable resource growth. The
rollback path is to stop the newly started daemon when it can be identified safely, restore the last
trusted binary/config/state workflow, and use the last trusted launch path or manual emergency
catch-up until a corrected build passes this gate. If no last trusted workflow is available, keep
the deployment blocked and record the human go/no-go decision explicitly instead of treating
degraded evidence as success.

## Production Readiness Gate

Do not treat the fix as production-ready until all of the following are true:

- live protection checks pass
- recovery-from-last-successful-hide checks pass
- rolling last-24h daytime verification checks pass
- randomized nightly full recheck checks pass
- reconciliation freshness truth checks pass
- emergency catch-up and `Last 24 hours` preset checks pass
- source-refresh checks pass
- throttle and backoff checks pass
- TUI truthfulness checks pass
- compatibility approval and launch-path checks pass
- detached `server-start` check passes for rsync-based server deployment
- suppressor tests pass
- docs workflow passes
- maintained docs describe the new operator workflow, compatibility expectations, and architectural
  limit honestly
