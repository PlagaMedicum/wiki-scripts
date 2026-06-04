# Suppressor Operations


## First Run

1. Copy `.env.example` to `.env`.
2. Review `config.toml`.
3. Run `make env-check`.
4. Run `make check-auth`.
5. Run `make dry-run`.
6. Move to `make run`, `systemd`, or the rsynced binary `server-start` path only after
   the dry run is clean and the actual launch path has its own evidence.

## Emergency 001 Trust Gate

Treat the active suppressor recovery gate as the minimal stable server only:

1. prove the exact binary that is running on the target host
2. prove the same PID survives logout and owns fresh daemon status
3. prove a new watched edit hides quickly
4. prove the daemon stays current or within bounded lag under active edits
5. prove auth-session, rate-limit, transport, and local-persistence failures stay visible without
   daemon exit

A stale replayed hide while the daemon remains hours behind is a failed smoke result, not partial
success. PID evidence, receipt evidence, or checklist completion without same-run current-binary
freshness proof does not count as realtime protection proof.

## Authoritative Launch-Path Baseline

Treat the active supervisor path on this host as the source of truth for whether protection is
running.

- The normal local operator workflow is `make run` for an attached daemon, or `server-start` for
  detached server deployment.
- The rsync server workflow is `./suppressor --config ./config.toml server-start` from the deployed
  directory. It starts a detached supervisor, which starts and restarts the daemon child it
  verifies.
- `systemd` remains supported as an optional launch path, but it is not the default verification
  route unless this host is actually using it.
- `runtime_status.json` is daemon-owned realtime truth for the running daemon.
- `command_report.json` is only the bounded result of the last one-shot operator command. It does
  not prove that the daemon is healthy, current, or even running.
- A stale PID file or unreadable status/report surface must be treated as a warning or
  migration-needed condition, not as healthy protection.

## Current Operator Workflow

For day-to-day use:

1. Start through `make run`, `systemd`, or `server-start`.
2. Trust `make health` and `make status` before process lines or command reports.
3. Use one-shot commands only for bounded manual verification or catch-up.
4. Treat `command_report.json`, journal lines, and Prometheus metrics as separate evidence from daemon-owned
   realtime protection state.

The daemon trusts MediaWiki `recentchanges` polling as the authoritative live detector. Retained
EventStreams code is not the healthy-state source of truth.

## Emergency Live-Only Production Profile

Until the target-host daemon passes live-hide soak, keep automatic verification disabled in the
checked-in production baseline:

- `[daytime_verification].enabled = false`
- `[nightly_sweep].enabled = false`

Keep these manual operator tools available:

- `make catch-up-now`
- `make emergency-catchup ARGS="--dry-run"`
- `./suppressor --config ./config.toml coverage-last-24h --report-only`

Those commands are bounded operator actions. They do not prove the daemon is currently protecting
live edits, and they must not be used to excuse a failing live path.

## 2026-05-31 Signal And RevDel Retry Lesson

The daemon must install handlers for the operator signals before entering its main loop:

- `reload-cache` sends `SIGHUP` and means "force a watched-page cache reload"
- `catch-up-now` sends `SIGUSR1` and means "run bounded manual recovery"
- `nightly-sweep-now` remains a legacy alias for the same signal while old operator scripts are
  retired
- `SIGTERM` means graceful stop

Do not remove these handlers while the CLI uses signal delivery. The Unix default for `SIGHUP` and
`SIGUSR1` is process termination, so an unhandled operator command can look like a random crash
followed by supervisor restart.

Per-revision RevDel denials such as `permissiondenied` or `cantdelete` are terminal for that target.
The daemon quarantines them in `daemon_state.json`, reports degraded status with a manual
review next action, and keeps hiding new watched edits. It must not retry those responses forever:
that wastes API budget, triggers rate limiting, and can delay live polling. Transient transport,
decode, rate-limit, and server errors remain retryable through the pending queue.

## Auth Contract

Required variables:

```dotenv
BEWIKI_BOT_USERNAME=YourBot@revdel-watch
BEWIKI_BOT_PASSWORD=REDACTED
```

Notes:

- use the full BotPasswords login shown by MediaWiki, including the `@label` suffix
- do not commit `.env`
- current internal env names still use the `BEWIKI_` prefix

## Required Rights

Current startup enforcement expects:

- `bot`
- `deleterevision`
- `deletelogentry`

The current working deployment baseline is a be.wiki bot account with the rights and BotPasswords
grants needed for that setup.

## Current Config Baseline

The checked-in `config.toml` is the current be.wiki production baseline for:

- API URL
- EventStreams URL, retained only for non-authoritative observer/fallback code in this hotfix tree
- watched-list title
- request-page triggers, currently `Вікіпедыя:Запыты да схавальнікаў`
- RevDel reason
- realtime stale/read timeouts
- bounded catch-up window and maximum revisions per run
- catch-up warning sample retention
- disabled automatic daytime and nightly verification in the emergency production profile
- queue capacity
- metrics bind

Treat that file as the current working baseline, not as a guarantee that every wiki already fits it.
The low-spec defaults are intentionally conservative: one daemon process, small CLI controls, queue
capacity 100, sequential bounded catch-up, five safe title samples per repeated warning class, and no
unbounded warning output. These bounds are not a license to delay hiding; if a source-list edit adds
more titles than the planning threshold, the daemon still starts title-scoped catch-up and logs that
the source edit is large.

## Config-Stability Gate

Config changes are operator-contract changes. Do not edit tracked config, target-host config,
config schema, defaults, environment variable names, loading semantics, or deployment-required
sections unless the change has a concrete motivation, human review, compatibility or migration
evidence, rollback/fallback, and target-host verification.

## State Files

Current runtime state lives under `state/`:

- `last_event_id.txt`
- `processed_revids.json`
- `suppression_list_cache.json`
- `nightly_sweep_progress.json`
- `runtime_status.json`
- `command_report.json`
- `daemon.pid`
- `daemon.log` for the detached `server-start` path unless a different log path is supplied

These are local machine files, not source-of-truth docs.

## Server Build And Detached Launch

Build the server artifact from `suppressor/`:

```bash
make build-server
```

This wraps:

```bash
cargo zigbuild --release --target aarch64-unknown-linux-musl
```

The rsync source is:

```text
target/aarch64-unknown-linux-musl/release/suppressor
```

For target-host proof, also record a safe artifact identity tuple for the exact deployed copy, such
as:

```bash
stat -c '%n %s %y' ./suppressor
```

That tuple is non-secret and should be recorded alongside the `server-start` receipt and live PID.

After copying the binary, `config.toml`, and the operator-managed `.env` or equivalent secret input
to the server, start the daemon with one binary command:

```bash
./suppressor --config ./config.toml server-start
```

The receipt must include mode, daemon PID, supervisor PID, binary path, config path, PID file,
`runtime_status.json` path, detached log path, and `launch_path=server-start`. Trust this launch
only after reconnecting to the server and confirming the supervisor PID is alive, the current
`daemon.pid` process is alive, stdout/stderr are going to the printed log path, and daemon-owned
`runtime_status.json` continues updating under the 10-second freshness rule above.
The same run must prove current status shape: `runtime_status.json` includes `live_lane`,
`background_lane`, and `latency`, and recovery work surfaces candidate-first aggregate fields.
Missing receipt fields, missing config, missing secrets, unwritable state/log paths, duplicate
daemon, startup timeout, stale PID, stale runtime status, launch-path/PID mismatch, non-`server-start`
launch labels, missing logout-survival evidence, missing safe artifact identity, old status shape,
or unhealthy startup evidence blocks deployment trust. A running daemon may continue protecting edits
while evidence is incomplete, but deployment trust stays blocked until the missing or mismatched
evidence is resolved and recorded.

## Crash-Resilience And Recovery Status

Do not interpret process liveness as healthy protection. If RevDel auth or wiki-side permission
fails, the daemon should stay alive but `runtime_status.json` must show blocked or unhealthy live
protection and a compact `live-hide` actionable issue. The operator action is to check bot session,
rights, and wiki-side permission state before trusting another smoke result.

If local state persistence fails, including `last_event_id` write or atomic replace errors,
`runtime_status.json` should show `state-persistence` and non-healthy realtime status while the
stream reopens through bounded backoff. Check state directory ownership, available disk, and the
configured state paths before relaunching.

For the rsync `server-start` path, a daemon process exit is no longer final. The detached supervisor
marks `runtime_status.json` unhealthy, waits with bounded backoff, and starts a new daemon child.
The current daemon PID may therefore change after a crash; use `daemon.pid` for the live child and
`state/supervisor.pid` only to identify or stop the restarter itself.

Ordinary startup, polling-gap or retained-observer-gap recovery, and emergency recovery should report aggregate candidate-first
evidence: candidate source, candidate count, watched candidate count, chunk count, discovery time,
and a fallback reason if the daemon uses a full watched-set scan. These aggregate counts are safe to
record. Do not paste raw logs, raw page titles, actor names, comments, revision IDs from real
incidents, cookies, tokens, or hidden content into tracked docs.

## Live And Background Lanes

The daemon now separates RevDel execution into two bounded in-process lanes:

- `live`: recentchange-triggered watched edits.
- `background`: catch-up, reconciliation, rolling last-24h verification, nightly full recheck, and
  command-driven coverage or recovery work.

Live admission is non-blocking. If the live lane is full, runtime status must become non-healthy and
show the saturation reason instead of silently waiting behind queued work. Live actions also carry a
short deadline; an expired live attempt records a retrying `deadline-exceeded` outcome so newer live
edits can still be accepted or visibly rejected.

In `runtime_status.json`, check `realtime.live_lane` and `realtime.background_lane` separately. The
fields to record are queue depth, queue capacity, in-flight count, concurrency limit, latest
saturation time, and latest saturation reason. The legacy `realtime.queue_depth` remains the live
queue depth for compatibility. Recent timing evidence is under `realtime.latency` for
observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden.

For deployment evidence, do not treat a quiet background lane as proof of live health. A good
target-host smoke check records a live or controlled dry-run edit while reconciliation, catch-up, or
verification is either active or queued, then confirms the live lane reacts without waiting for the
background lane to drain. This check has no fixed internal millisecond SLA; the release target is
still the external hide evidence in the feature spec.

Operator actions run as plain commands:

- `catch-up-now` sends bounded manual recovery to the running daemon
- `emergency-catchup` runs a bounded recovery command
- `coverage-last-24h --report-only` runs the rolling daily verification preset

One-shot command results are written to bounded `command_report.json` and rendered as command output.
They do not overwrite daemon-owned `runtime_status.json` and must not be treated as proof that the
daemon is healthy or running.

## Operational Notes

- use `make status`, `make health`, `make perf`, and Prometheus metrics for local supervision
- use the binary command `coverage-last-24h --report-only` for the rolling daily verification preset
- keep logs free of secrets and suppressed payloads
- use `make reload-cache` only for watched-list cache diagnostics
- use `make catch-up-now` to ask the running daemon for bounded manual recovery
- use `make emergency-catchup ARGS="--dry-run"` for a bounded recent recovery check
- use `make coverage-report ARGS="--start <RFC3339> --report-only"` for accident-window accounting
- keep `make nightly-sweep-now` only as the old alias for bounded manual recovery
- treat auth or rights loss as a stop-condition, not a soft warning
- treat active shared backoff, stale full-recheck evidence, failed scheduled verification, or stale
  launch-path evidence as non-healthy until later successful evidence clears it
- treat generic repeated `Failed to decode JSON response` or per-page catch-up warnings as an
  incident symptom; the daemon should now show one classified warning summary with count, class/API
  code, HTTP status when known, retryability, and a few safe sample titles

## Operational Targets

- target 95% of controlled realtime hides under one second and 99% under five seconds
- report p95 and p99 from controlled runs before claiming release readiness
- prioritize newer edits first during recovery after disconnect or restart
- treat a stale authoritative polling path as unhealthy after the configured 10-second threshold
- catch up the default 30-minute window within the configured recovery target where wiki/API health allows it
- recover from `last_successful_hide_at` when present instead of silently truncating to a newer
  arbitrary recent window
- record one rolling `Last 24 hours` verification and one nightly full watched-set recheck during
  each uninterrupted 24-hour daemon period
- keep the service running in blocked or unhealthy state on missing rights, broken auth, persistent
  API failure, or malformed suppression-list input so runtime evidence stays fresh while the
  operator fixes the root cause

## Primary Status Questions

The first status rows must answer these questions without making the operator decode internal
bookkeeping:

- Is protection working now, and which PID or supervisor path is carrying it?
- What exact work is active right now: idle, live recovery, `Last 24 hours` verification, nightly
  full watched-set recheck, watched-page reload follow-up, or backoff?
- What is the truthful wall-clock lag right now?
- When was the last successful hide, and which revision was it?
- What is the latest actionable issue and the next operator step?
- How long has this daemon session been continuously protecting edits?

Rows such as raw resume cursors, processed-revision ring sizes, checkpoint counts, or vague
verification-path wording are secondary diagnostics only. They should never displace the primary
protection rows.

## Incident Response Flow

1. Run `make health` and `make status`; check realtime state, lag, latest outcome, recovery trigger,
   and latest error.
2. If realtime is stale, reconnecting, unhealthy, or blocked, do not rely on the daemon process line
   alone.
3. Run `make emergency-catchup ARGS="--dry-run"` to inspect the recent default window without hiding.
4. If the report is correct and auth is healthy, run `make emergency-catchup` to queue unresolved
   eligible edits for hiding.
5. For a known accident window, run `make coverage-report ARGS="--start <RFC3339> --end <RFC3339> --report-only"`.
6. For the routine rolling window, use `./suppressor --config ./config.toml coverage-last-24h --report-only`.
7. Treat unresolved items as open exposure until each one has a reason, owner, and next action.

Reports include page title, revision ID, age, reason, and next action. They must not include hidden
text, raw comments, credentials, tokens, or session material.

## Source-List And Request-Page Hooks

Edits to `Удзельнік:Wizardist/SuppressionList` are realtime triggers. After the cache refresh
succeeds, the daemon diffs the old and new watched-title sets and immediately starts bounded
catch-up for newly added watched titles. Removed titles are recorded in status but not checked.

Edits to configured request pages, including `Вікіпедыя:Запыты да схавальнікаў`, start an immediate
recent-window catch-up over the current watched set. This is a recovery hook, not a replacement for
keeping the source list current.

Runtime status shows the latest source-refresh outcome, added/removed counts, catch-up scope,
classified refresh errors, and the latest catch-up summary.

## 2026-04-25 Warning-Storm Lesson

The terminal warning storm was consistent with one root cause repeated across many watched pages:
catch-up revision queries failed and logged once per title. The specific timestamp lesson is that
MediaWiki API timestamp parameters must use UTC second precision with no fractional part; fractional
`rvstart` values can be rejected as `badtimestamp`, causing every page query in a catch-up run to
fail. The code now uses a shared MediaWiki timestamp formatter for revision queries and EventStreams
`since` values, and catch-up coalesces repeated query failures into a compact summary.
