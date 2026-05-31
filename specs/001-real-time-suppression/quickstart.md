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
  - live-hide incident update with sensitive identifiers redacted
  - server-running launch-path mismatch update on 2026-05-07
  - live-priority parallel execution update on 2026-05-09
  - live-latency clarification update on 2026-05-09
  - KISS/catch-up simplification update on 2026-05-10
  - rsynced crash evidence update on 2026-05-13
  - rsynced old-command deployment evidence update on 2026-05-14
---

# Quickstart: Real-Time Suppression Recovery


## Verification Goal

Prove that the running suppressor:

- hides eligible watched-page edits automatically in realtime
- recovers missed coverage from the last successful hide after downtime or failure
- keeps manual verification and manual full recheck available without confusing them with live
  protection
- shows truthful operator-first runtime status
- preserves or explicitly explains compatibility for the actual deployment path in use
- builds the aarch64 Linux musl server binary through the documented Makefile target before rsync
  deployment
- starts from the rsynced binary with one detached `server-start` command that survives closing the
  server terminal

Important architectural limit: the suppressor observes edits after MediaWiki publishes them.
Verification should minimize and measure publish-to-hide exposure, but it must not claim guaranteed
zero first-view prevention.

## Active Emergency Gate

Treat the current `001` verification gate as the minimal stable suppressor server only:

1. the target host is running the exact intended binary
2. the same PID survives logout and owns fresh daemon status
3. a new watched edit hides quickly
4. the daemon stays current or within bounded lag under active edits
5. auth-session, rate-limit, transport, and local-persistence failures stay visible without daemon
   exit

A stale replayed hide while the daemon remains hours behind is a failed smoke result, not partial
success. PID evidence, receipt evidence, or checklist completion without current-binary freshness
proof does not count as realtime protection proof.

For this emergency gate, the checked-in production baseline is live-only on the target host:
`daytime_verification.enabled=false` and `nightly_sweep.enabled=false`. Keep manual `Last 24
hours`, full watched-set recheck, and emergency catch-up available, but do not use automatic
verification as evidence that the live daemon is trustworthy.

## Out Of Scope Until Smoke Passes

Do not spend the active emergency pass on:

- TUI polish beyond truthful protection state
- broad reporting or diagnostic-surface growth
- repo-wide Spec Kit template or docs-workflow repair
- inactive-feature work such as `002-fix-git-commit`
- speculative architecture work not needed for live protection

Historical evidence sections below are kept to explain how the current gate was derived. They do
not expand the active scope.

## Active MVP Critical Path

During the active human-safety freeze, do not spend time on unrelated tools, broad refactors, or
cosmetic UI work. Verify this path first:

1. Short suppressor test gate passes.
2. Server binary builds with `make build-server`.
3. Actual launch path starts the daemon on the host being protected, preferably through the
   one-command detached `server-start` path for the rsynced binary.
4. Live or controlled dry-run hiding path updates `last_successful_hide_at` or the equivalent dry-run
   outcome without waiting for reconciliation.
5. Manual recovery or manual verification commands stay bounded and truthful, and disabled
   automatic verification does not mask live protection state.
6. RevDel auth/permission failure blocks or degrades protection without exiting the daemon.
7. Stream cursor and local state persistence failures do not permanently stop live monitoring or
   show false healthy status.
8. Rate-limit/backoff does not starve live hiding and does not show false healthy status.
9. The controlled live or dry-run smoke proves current head or bounded lag, not only a stale
   replayed hide.

## KISS Performance Reset

The current planning intent is deliberately small: make recent live edits react quickly, make
startup/recovery stop doing unnecessary full watched-set scans, and make the first TUI status pane
answer whether protection is working now. Do not add a new service, database, dashboard, generic
moderation framework, or broad refactor before these checks pass.

2026-05-14 local hotfix note: the current local source tree now treats MediaWiki `recentchanges`
polling as the authoritative live detector. Retained EventStreams code is not the healthy-state
truth path for this MVP hotfix tree.

The 2026-05-10 local TUI run showed the failure mode in aggregate: startup recovery selected a
multi-day window, scanned the full watched set of roughly 1.4k pages, found only a small number of
relevant edits, and took minutes while the operator saw `catching-up`. The fix is candidate-first
recovery:

1. Select the recovery anchor and window.
2. Query a bounded global candidate source for changes in that window.
3. Filter candidates by the normalized watched-title cache.
4. Verify or hide only watched candidate revisions.
5. Fall back to a full watched-set scan only with an explicit fallback reason or explicit full
   verification action.
6. Keep the live lane open before and during the background recovery scan.

Acceptance for this reset:

- ordinary startup or emergency recovery records candidate source, candidate counts, watched
  candidate counts, fallback reason when any, and candidate discovery time
- live synthetic watched edits still queue/submit while candidate recovery or full verification is
  active
- a fallback full scan is visible as slower background work, not as a reason for live edits to wait
- the primary TUI shows compact protection/current-work/lag/last-hide/latest-issue evidence first
- the log pane labels whether it is current-session output or a real daemon log tail

## Active Live-Hide Incident With Sensitive Identifiers Redacted

The operator provided a screenshot showing a watched sensitive page edit by an operator-controlled
account while the public hide action was still available. The concrete page, account, and revision
identifiers are intentionally omitted from tracked repository docs, tests, contracts, examples,
fixtures, and code comments. This is a failed T041
live-hide smoke result. The page is known to be in the relevant watched set, so the next
implementation pass must assume a live-path failure until target-server evidence proves otherwise.

Immediate handling:

1. If the exposed revision ID is known, hide it manually or run emergency catch-up before waiting for
   any code fix.
2. Collect only non-secret target-server facts needed to classify the failure: running PID/binary,
   `runtime_status.json` freshness, `launch_path`, last observed event, last matching title/revision,
   latest outcome, latest actionable issue, queue depth, whether the visible revision is in
   `processed_revids.json`, and whether the page title is in the server cache.
3. Do not use stale local repo state as server proof. The checked-in `suppressor/state/` snapshot is
   useful only as old baseline evidence.
4. Fix the first failing boundary in the live path before broad docs, resource sampling, or TUI
   polish: event observation, watched-title match, processed-revision skip, queue handoff, RevDel/auth
   result, or stale/wrong deployed binary.
5. Add a regression with a fully synthetic watched title and synthetic operator-account actor.
   Operator-account eligible edits must dispatch as live watched revisions and must not be silently
   skipped.

Until this incident is fixed and retested on the deployed path, the MVP is blocked even if T040
launch evidence or T042 resource evidence is later collected.

## Server Running But Launch Evidence Still Blocked

After the server was made to run again, the operator-visible status showed a live process, but it
also showed non-healthy protection because the launch path, PID file, daemon-owned runtime status,
and detached-log evidence did not agree. This is not a new config decision. It is blocked T040
evidence.

Treat this state as follows:

1. Do not stop a possibly protective daemon only to make the evidence cleaner.
2. Do not mark T040 complete from process liveness alone.
3. Capture only non-secret facts: whether the live process is the deployed suppressor binary, whether
   `runtime_status.json` is fresh, whether its launch-path PID matches the live process and PID file,
   whether the detached log path belongs to the same run, and whether the original `server-start`
   receipt exists.
4. If the evidence matches, record T040 and proceed to T052 controlled live or dry-run smoke.
5. If the evidence does not match, keep deployment trust blocked and either run a safe fresh
   `server-start` after duplicate-daemon risk is handled, or fall back to the last trusted workflow.

T052 and T042 remain blocked until the launch-path mismatch is resolved or an explicit human
go/no-go exception records the risk.

## Rsynced Server Crash Evidence Recorded On 2026-05-13

The operator rsynced a safe diagnostic bundle from the target host. Do not commit raw logs or raw
runtime files from that bundle: server logs can contain real sensitive page, actor, revision, diff,
or comment identifiers. Use only sanitized outcome classes, aggregate counts, and non-secret
runtime facts in tracked evidence.

Safe findings:

- The target-host config now contains the reviewed `[realtime]` section. The old
  `missing field realtime` failure is no longer the active crash signature.
- `daemon.pid`, fresh `runtime_status.json`, and detached log metadata point to one
  `server-start` daemon. Treat T040 as mostly aligned, pending logout-survival confirmation and
  concise non-secret evidence recording.
- Runtime status is still `unhealthy`.
- The deployed server binary is older than the current lane-aware MVP design because its status
  lacks `live_lane`, `background_lane`, and `latency` fields. Do not use this run for T052 smoke
  readiness.
- The server-observed hard crash was a classified RevDel permission failure followed by process
  exit.
- An earlier retained-observer compatibility failure stopped live monitoring after a local
  `last_event_id` state write or atomic replace failure.

Immediate handling:

1. Keep the raw bundle untracked and use only sanitized counts and non-secret runtime facts in
   tracked evidence.
2. Treat the crash signatures as the historical reason T067 through T076 were implemented locally;
   do not treat the local build alone as proof that the server now runs those fixes.
3. Build the current server artifact, rsync it to the target host, and relaunch from the exact
   deployed binary with `./suppressor --config ./config.toml server-start`.
4. Record safe launch identity for that run: binary path plus a non-secret artifact identity tuple,
   tied to the same PID, receipt, and `runtime_status.json`.
5. Finish T040 with logout-survival evidence, then run T052 controlled live or dry-run smoke on the
   rebuilt lane-aware binary.

## Rsynced Target-Host Relaunch Evidence Recorded On 2026-05-14

The operator reported that the binary was updated and the logs were rsynced again after relaunching
with the old command. Treat this bundle as deployment-evidence refinement, not as smoke success.

Safe findings:

- The latest `runtime_status.json` still lacks `live_lane`, `background_lane`, and `latency`, so
  the target host is still not proving the current lane-aware binary is writing status.
- The same bundle still shows legacy recovery shape rather than the newer candidate-first recovery
  evidence expected from the current local source when that recovery path runs.
- After the latest daemon start, the rsynced log shows startup/open activity but no new
  `state-persistence` or blocked-protection evidence from the fixed crash-resilience paths.
- Therefore the remaining blocker is deployment identity and launch workflow trust, not another
  unresolved local crash-policy design.

Immediate handling:

1. Launch the target daemon from the exact rebuilt artifact path or verified deployed copy of it,
   not from an older wrapper, stale shell alias, or older copied binary.
2. Record a safe artifact identity tuple for that launch, tied to the same `server-start` receipt,
   PID file, and daemon-owned `runtime_status.json`.
3. Verify that the same run writes current `live_lane`, `background_lane`, and `latency` fields
   before treating T052 as unblocked.
4. If a recovery pass runs on that same launch, verify the recovery summary uses candidate-first
   fields rather than the older legacy-only shape.
5. Only after those checks pass should T040 logout-survival recording and T052 live/dry-run smoke
   be treated as current-binary evidence.

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

## Current MVP Go/No-Go Updated On 2026-05-13

Decision: BLOCK target-host deployment trust until the active T041 live-hide incident is fixed and
T040, T041, T052, and T042 evidence is recorded. T039 records the config-stability block and Q001
now approves path 1: target-host config migration to the reviewed tracked baseline. The rsynced
server bundle mostly resolves the earlier launch-path mismatch, but the running daemon is
`unhealthy`, lacks the current lane/latency status fields, and still demonstrates crash signatures
that must be fixed before smoke readiness.

Current human-review packet:

- Q001 in [questions.md](questions.md) is answered: approve path 1.
- Use [review-queue.md](review-queue.md) as the index of pending human and maintainer actions.
- The urgent next action is the crash-resilience implementation slice, followed by RQ002/T040
  logout-survival evidence and T052 smoke on the rebuilt binary.

- ACCEPT local test evidence: `rtk cargo test --manifest-path suppressor/Cargo.toml --
  --test-threads=1` passed with `206 passed` for the current local source tree after synthetic
  fixture cleanup.
- ACCEPT local server-build evidence: `rtk make -C suppressor build-server` produced the
  aarch64 Linux musl binary at `target/aarch64-unknown-linux-musl/release/suppressor`.
- ACCEPT local command/report evidence: emergency catch-up defaults, `Last 24 hours`,
  command-report compatibility, bounded unresolved samples, safe revision URLs, and daemon-vs-
  command status separation passed targeted tests.
- ACCEPT reviewed config path decision: Q001 approves path 1, and the human operator reports the
  server config was updated and the daemon was started.
- ACCEPT partial config-stability launch evidence: the rsynced target config contains `[realtime]`,
  and PID/runtime/log facts can be tied to a `server-start` daemon.
- BLOCK final T040 evidence only on the remaining launch-proof gap: SSH logout-survival evidence and
  concise non-secret recording still need to be captured.
- BLOCK current deployed-binary trust: the server status lacks current lane/latency fields, so the
  running binary is older than the current MVP design.
- ACCEPT local crash-resilience code evidence: classified RevDel auth/permission failure now records
  blocked protection without process exit, stream cursor persistence failure records
  `state-persistence` and reconnects, and ordinary no-title-scope catch-up uses recentchanges
  candidate discovery before full-scan fallback.
- BLOCK target-host crash-resilience trust: the rebuilt binary with those fixes still needs to be
  rsynced, launched, and smoked through T040/T052 before deployment trust.
- BLOCK live-hide deployment trust: no target-host live or controlled dry-run watched-edit smoke
  result is recorded yet, and the operator-provided screenshot is a failed smoke result for a
  watched sensitive page.
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

## T040 Evidence Acceptance Contract

T040 is an evidence gate, not a new config decision. Q001 approved path 1: target-host config
migration to the reviewed tracked baseline. Do not make further config edits to satisfy T040 unless
a new human-reviewed config decision is recorded first.

An already-started daemon can satisfy T040 only when the evidence shows it was started after the
Q001-approved config migration by the deployed binary through
`./suppressor --config ./config.toml server-start`. The operator may provide the original
non-secret receipt, or the same receipt fields reconstructed from safe command output and
daemon-owned status. If that receipt cannot be shown, if `launch_path` is not `server-start`, or if
the PID/status/log evidence cannot be tied to the same process, keep T040 blocked until a fresh
`server-start` run can be performed safely or a duplicate-live-daemon diagnostic is recorded.

The current server-running screenshot falls into the blocked category when it shows a live process
but mismatched launch-path PID, PID file, runtime status, or detached log evidence. Record the
mismatch as negative T040 evidence; do not treat it as launch success.

The 2026-05-13 rsynced bundle supersedes that earlier mismatch diagnosis for launch-path evidence:
safe metadata shows a reviewed realtime config plus `server-start` PID/status/log alignment. This
can be recorded as partial T040 launch evidence, but it does not complete logout-survival evidence
and it does not satisfy T052 because the deployed binary is older than the current lane-aware MVP
runtime contract.

Acceptable T040 evidence is limited to:

- command line with config path, without environment values
- receipt fields: mode, PID, binary path, config path, PID file, runtime-status path, detached log
  path, and `launch_path=server-start`
- safe artifact identity tuple for the launched binary, such as resolved path plus size/mtime, tied
  to the same receipt and live PID
- PID liveness and expected suppressor binary path when available
- `runtime_status.json` metadata or safe excerpts showing `launch_path=server-start`, PID matching
  the live process, and daemon-owned status freshness
- detached log path plus evidence that stdout/stderr go there, without copying raw log payloads
- reconnect evidence after closing the SSH terminal: same PID alive and daemon-owned status still
  fresh after reconnect
- operator statement that the server config was backed up or can be rolled back to the last trusted
  config, plus the safe field names changed by the path 1 migration

Forbidden evidence includes `.env` values, passwords, cookies, tokens, session material, raw hidden
text, sensitive article content, real sensitive-edit incident page titles, actor names, revision
IDs, diff URLs, comments, screenshots, full unredacted logs, and any command output that embeds
secrets or identifies a real sensitive edit.

Daemon-owned status freshness for T040 means all of the following:

- the printed or recorded PID is alive at inspection time
- the PID in `runtime_status.json` or the launch-path object matches the live process when present
- `runtime_status.json` has a daemon timestamp, heartbeat, or file modification time no older than
  10 seconds at inspection
- a second inspection within 10 seconds shows the status timestamp, heartbeat, or file modification
  time still advancing or still inside the 10-second freshness window
- the status labels the launch path as `server-start` or equivalent detached-binary wording

Partial evidence outcomes:

- PID alive but stale or unrelated `runtime_status.json`: block T040 and record stale status.
- Fresh status but `launch_path` is not `server-start`: block T040 for the rsync `server-start`
  path and record the actual launch path separately.
- Receipt present but missing PID, binary path, runtime-status path, log path, config path, or
  safe artifact identity tuple: block T040 until the missing field is supplied or a fresh
  `server-start` receipt is captured.
- PID and status pass before logout but reconnect evidence is missing: keep the daemon running if it
  is protecting edits, but keep T040 and MVP deployment trust blocked.
- Target-host access interruption, duplicate live daemon, stale PID, missing receipt, or stale
  runtime status keeps RQ002 open; do not mark T040 complete by implication from T041 live-smoke or
  T042 resource evidence.
- Live process plus launch-path/PID/runtime mismatch keeps T040 open even when the TUI can read a
  fresh status file. Resolve the mismatch before T052.
- PID/status/log alignment with missing lane/latency status fields can advance T040 launch
  evidence, but it blocks T052 until the rebuilt current binary is deployed and verified.
- A same-run receipt without artifact identity or without the current lane/latency status shape is
  only partial launch evidence. Do not treat it as rebuilt-binary proof for T052.

If the daemon is currently protecting edits but T040 evidence is incomplete, do not stop it only to
make documentation cleaner. Preserve protection, record the missing evidence, and keep deployment
trust blocked until the missing T040 evidence is collected or an explicit human go/no-go decision is
recorded.

The 2026-05-06 target-host failure `missing field realtime` blocked deployment trust until Q001 and
the reviewed path-1 config migration. The 2026-05-13 rsynced evidence shows that config gate is now
resolved for the current target host. Do not add `[realtime]` or any other section to the server
config as an unreviewed shortcut in future runs; either migrate through the reviewed evidence path
or run a binary that fails safely with a reviewed migration-needed diagnostic.

## T039 Config-Stability Evidence Recorded On 2026-05-06

Human review evidence: the human owner explicitly required that all config changes be motivated and
reviewed by a human before they are trusted. This became release-blocking governance in the
constitution and remains active in constitution v1.10.0.

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
- Documented divergence at the time: the target-host config used by the command did not satisfy the
  current config schema because `[realtime]` was absent.
- Compatibility or migration decision: Q001 approved path 1 on 2026-05-07. The human operator
  reports that the server config was updated to the reviewed tracked baseline and the daemon was
  started. The 2026-05-13 rsynced evidence confirms the target-host config now has `[realtime]`.
  Deployment trust still waits for crash-resilience fixes, T040 logout evidence, rebuilt-binary
  smoke, and resource evidence.
- No-background-edit confirmation: no tracked or target-host config edit is approved or performed
  as part of this evidence pass.
- Rollback/fallback: keep target-host deployment trust blocked; use the last trusted
  binary/config/state workflow if available or manual emergency catch-up while crash-resilience and
  rebuilt-binary verification are prepared.

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
4. Confirm `runtime_status.json` is daemon-owned and satisfies the T040 freshness contract above:
   matching PID when present, status timestamp or file mtime no older than 10 seconds, a second
   fresh inspection within 10 seconds, and `launch_path=server-start` or equivalent
   detached-binary wording.
5. Confirm daemon stdout/stderr goes to the printed log path, not the SSH terminal.
6. Close the SSH terminal and reconnect.
7. Confirm the PID is still alive and the status file continues updating.
8. If config, auth secrets, state/log paths, stale PID, duplicate live daemon, startup status
   verification, receipt capture, or logout-survival evidence fail, treat T040 as blocked; do not
   trust a partial or orphaned background process.

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
- Target-host evidence may be supplied manually by the human operator because the repo-local agent
  may not have server access. Manual evidence must follow the no-secret evidence rules above and is
  accepted only for the listed safe receipt/status/path fields.

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
configured bot test page
```

2. Confirm benchmark edits are bot-marked and test-only.
3. Measure publish-to-detect, observed-to-queue, queue-to-submit, submit-to-complete, and
   publish-to-hidden timings.
4. While a synthetic or controlled background reconciliation/recovery job is active or intentionally
   delayed, publish or inject a watched live edit and confirm the live lane queues and submits it
   without waiting for the background lane to drain.
5. Confirm runtime lag uses truthful wall-clock calculation and is not pinned to `0s`.
6. Measure idle and active CPU, memory, queue depth, state size, and warning-summary counts for the
   daemon alone and daemon plus TUI.
7. Confirm bounded-state behavior under repeated failure storms.

Minimum timing evidence for the live-priority implementation:

- Deterministic tests must record observed-to-queue, queue-to-submit, submit-to-complete, and
  observed-to-hidden samples for synthetic live edits.
- A blocked or delayed background lane must not make live queue-to-submit wait for the background
  lane to drain; any test timeout is only a hang guard, not a fixed internal handoff SLA.
- A burst of at least 10 synthetic eligible watched edits must report p50, p95, and p99 for recent
  live samples and preserve final outcomes for every synthetic revision.
- Live queue saturation or deadline expiry must produce degraded or unhealthy status immediately
  instead of silent waiting.
- Target-host smoke evidence must still report publish-to-detect and publish-to-hidden because
  local tests do not include target-host polling delay or wiki-side publication delay.

Minimum resource evidence for T042:

- Measure at least 10 minutes idle for daemon alone and daemon plus TUI.
- Measure one active sample that includes live handling plus recovery, reconciliation, or backoff.
- Record CPU percentage, RSS memory, live queue depth/cap, recovery or reconciliation queue
  depth/cap, API concurrency, `runtime_status.json` size, `command_report.json` size,
  `processed_revids.json` size, detached log growth rate, coalesced-warning counts, live lane
  in-flight count, background lane in-flight count, and recent live latency p95/p99.
- Block release if API concurrency exceeds the default cap of 2 without documented approval, a queue
  reaches its cap without degraded status, `runtime_status.json` or `command_report.json` exceeds
  1 MiB, repeated-root-cause log growth exceeds 10 MiB/hour without mitigation, or any field keeps
  growing monotonically after the active sample returns idle.

## Live-Hide Hotfix Local Evidence

Recorded for T047 through T051 with sensitive identifiers redacted and only synthetic fixtures in
tracked tests, docs, contracts, examples, fixtures, and code comments:

- Code fix: live recentchange handling no longer exits early when a watched revision is already in
  the processed ring. It now hands the candidate to the shared action dispatcher so `queued`,
  `already-processed`, and duplicate outcomes all update runtime status consistently.
- Synthetic regression coverage: a watched synthetic title edited by a synthetic operator-account
  actor dispatches as a live watched revision and queues a live hide action instead of being
  filtered as own-account, bot, or non-watched noise.
- Processed-revision coverage: a watched processed revision is not requeued, but it records an
  `already-processed` outcome with the live mode instead of disappearing silently from operator
  status.
- Targeted test results:
  `rtk cargo test --manifest-path suppressor/Cargo.toml stream::tests -- --test-threads=1`
  passed with 23 tests.
- Targeted queue/dispatcher result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml dispatch_action -- --test-threads=1`
  passed with 3 tests.
- Targeted worker result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml worker::tests -- --test-threads=1`
  passed with 2 tests.
- Full serial suppressor result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` passed with 206 tests.
- Server artifact result: sandboxed `rtk make -C suppressor build-server` was blocked by Zig cache
  write permissions, then the approved escalated rerun completed successfully and printed
  `target/aarch64-unknown-linux-musl/release/suppressor`.

Remaining deployment evidence: T040, T041, T052, and T042 still require target-host non-secret
facts, target-host relaunch or restart, a controlled live or dry-run watched-page smoke result, and
deployment-host resource sampling. Do not treat the local hotfix evidence as target-host proof.

## Live-Priority Lane Local Evidence Recorded On 2026-05-09

Recorded for T053 through T065 with synthetic fixtures only:

- Runtime model change: recentchange-triggered hides now enter a bounded live lane. Catch-up,
  reconciliation, verification, and command-driven RevDel work enter a separate bounded background
  lane. The tracked config shape did not change.
- Timing model change: runtime metrics now keep bounded samples for observed-to-queue,
  queue-to-submit, submit-to-complete, and observed-to-hidden. The older observed-to-hide name
  remains as a compatibility alias for observed-to-hidden.
- Status model change: `runtime_status.json` now records live/background queue depth, queue cap,
  in-flight count, concurrency limit, latest saturation metadata, action lane, submitted time,
  deadline, and p50/p95/p99 live latency snapshots. Older runtime-status JSON still loads with
  defaults when these fields are absent.
- Transaction boundary change: dispatch records duplicate/processed checks, queued status, and
  enqueue without holding runtime-status or processed-state locks across MediaWiki API calls. Worker
  submission, completion, and processed-revision persistence are separate local transitions.
- Deadline/degraded behavior: live queue admission is non-blocking. A full live lane records
  unhealthy/degraded live-hide status with `live-queue-full`; expired or timed-out live actions
  record retrying `deadline-exceeded` instead of blocking newer live actions behind the same wait.
- Background isolation evidence: a deterministic test queued synthetic background reconciliation
  work without draining that lane, then injected a synthetic watched live edit. The live worker
  completed the live edit while the background lane still had queued work, and recorded
  observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden samples. The
  timeout in that test is a hang guard only, not a fixed internal live handoff SLA.
- Burst evidence: a burst test dispatched 10 synthetic eligible watched edits plus a duplicate. The
  duplicate did not increase live queue depth, all 10 synthetic revisions reached final dry-run
  hidden outcomes, and observed-to-hidden p50/p95/p99 snapshots were present.
- Targeted live-priority result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml live_ -- --nocapture` passed with 25 tests.
- Targeted deadline result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml worker_defers_expired_live_action_deadline_without_api_wait -- --nocapture`
  passed with 1 test.
- Targeted status and latency compatibility results:
  `runtime_status_round_trips_lane_and_latency_fields`,
  `runtime_status_accepts_additive_lane_latency_and_outcome_fields`, and
  `runtime_latency_snapshot_reports_live_path_percentiles` each passed with 1 test.
- Fresh full serial suppressor result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` passed with 214 tests.
- Fresh server artifact result: sandboxed `rtk make -C suppressor build-server` was blocked by Zig
  cache write permissions, then the approved normal-cache rerun completed successfully in 1m 22s
  and printed `target/aarch64-unknown-linux-musl/release/suppressor`.
- Verified artifact:

```text
suppressor/target/aarch64-unknown-linux-musl/release/suppressor
ELF 64-bit LSB executable, ARM aarch64, statically linked, stripped
size: 9.7M
```

Remaining deployment evidence: this is still local dry-run/unit/build evidence. T040 launch-path
alignment, T052 controlled target-host live or dry-run smoke with the rebuilt lane-aware binary, and
T042 deployment-host resource sampling remain blocked until target-host facts are recorded.

## Crash-Resilient Runtime Local Evidence Recorded On 2026-05-13

Recorded for T067 through T076 with synthetic fixtures only:

- RevDel auth/permission policy: a classified permission failure now records a blocked live-hide
  outcome and `live-hide` actionable issue, returns the worker completion error, and keeps the
  daemon process alive. The worker no longer contains a `std::process::exit` path.
- Retained observer cursor policy: `last_event_id` persistence failure now records
  `state-persistence`, keeps realtime status non-healthy, and breaks back to the existing bounded
  retained-observer reconnect path instead of letting the spawned compatibility task disappear.
- State persistence policy: atomic text/JSON state writes create parent directories before writing
  temp files and renaming them into place; remaining write or rename failures are classified through
  runtime status rather than hidden by a later healthy stream event.
- Candidate-first recovery policy: ordinary no-title-scope catch-up queries bounded
  recentchanges, filters candidates by the watched-title cache, records candidate source, candidate
  count, watched candidate count, chunk count, discovery elapsed time, and requires
  `fallback_reason` before the older full watched-set scan is used.
- Primary TUI evidence: recovery candidate source/count/fallback metadata is rendered as aggregate
  status, and `state-persistence` remains a blocking issue for healthy realtime status.
- Targeted crash-resilience and candidate-first results:
  `worker_blocks_permission_failure_without_exiting_process`,
  `cursor_persistence_failure_records_state_issue_and_keeps_retry_path`,
  `ordinary_catchup_uses_recentchanges_candidates_before_full_scan`,
  `full_scan_fallback_requires_candidate_failure_reason`, and
  `fetches_recentchanges_window_candidates` each passed with 1 test.
- Fresh full serial suppressor result:
  `rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1` passed with 219 tests.
- Fresh server artifact result: sandboxed `rtk make -C suppressor build-server` was blocked by Zig
  cache write permissions under `~/.cache/zig`, then the approved normal-cache rerun completed
  successfully in 1m 47s and printed `target/aarch64-unknown-linux-musl/release/suppressor`.
- Verified artifact:

```text
suppressor/target/aarch64-unknown-linux-musl/release/suppressor
ELF 64-bit LSB executable, ARM aarch64, statically linked, stripped
size: 9.8M
```

Remaining deployment evidence: this is local code/test/build evidence only. T040 still needs
logout-survival evidence for the target-host `server-start` daemon, T052 needs a controlled
target-host live or dry-run smoke on the rebuilt crash-resilient binary, and T042 still needs
deployment-host resource sampling.

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
- live-priority lane checks pass while reconciliation or recovery is active
- timing tests report p95/p99 for observed-to-queue, queue-to-submit, submit-to-complete, and
  observed-to-hidden
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
