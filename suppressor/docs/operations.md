---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Operator setup and runtime contract for suppressor.
  source: .specify/doc-registry.json
---

# Suppressor Operations


## First Run

1. Copy `.env.example` to `.env`.
2. Review `config.toml`.
3. Run `make env-check`.
4. Run `make check-auth`.
5. Run `make dry-run`.
6. Move to `make run`, `make tui`, `systemd`, or the rsynced binary `server-start` path only after
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

- The normal local operator workflow is `make tui`, which starts and supervises a TUI-managed child
  daemon.
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

1. Start or attach through `make tui`.
2. Trust the primary status rows before the raw log pane.
3. Use one-shot commands only for bounded manual verification or catch-up.
4. Treat `command_report.json` and command log lines as separate evidence from daemon-owned
   realtime protection state.

The current MVP daemon trusts MediaWiki `recentchanges` polling as the authoritative live detector.
Retained EventStreams code is not the healthy-state source of truth for this hotfix tree.

## Emergency Live-Only Production Profile

Until the target-host daemon passes live-hide soak, keep automatic verification disabled in the
checked-in production baseline:

- `[daytime_verification].enabled = false`
- `[nightly_sweep].enabled = false`

Keep these manual operator tools available:

- `Emergency catch-up`
- `Coverage: Last 24 hours`
- `Run bounded recovery`

Those commands are bounded operator actions. They do not prove the daemon is currently protecting
live edits, and they must not be used to excuse a failing live path.

## 2026-05-31 Signal And RevDel Retry Lesson

The minimal daemon must install handlers for the operator signals before entering its main loop:

- `reload-cache` sends `SIGHUP` and means "force a watched-page cache reload"
- `nightly-sweep-now` sends `SIGUSR1` and now means "run bounded manual recovery"
- `SIGTERM` means graceful stop

Do not remove these handlers while the CLI and TUI still use signal delivery. The Unix default for
`SIGHUP` and `SIGUSR1` is process termination, so an unhandled operator command can look like a
random crash followed by supervisor restart.

Per-revision RevDel denials such as `permissiondenied` or `cantdelete` are terminal for that target.
The daemon quarantines them in `simple_daemon_state.json`, reports degraded status with a manual
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
The low-spec defaults are intentionally conservative: one daemon process, one TUI, queue capacity
100, sequential bounded catch-up, five safe title samples per repeated warning class, and no
unbounded warning output. These bounds are not a license to delay hiding; if a source-list edit adds
more titles than the planning threshold, the daemon still starts title-scoped catch-up and logs that
the source edit is large.

## 2026-05-06 Config-Stability Gate

Human review rule: config changes are operator-contract changes. Do not edit tracked config,
target-host config, config schema, defaults, environment variable names, loading semantics, or
deployment-required sections unless the change has a concrete motivation, explicit human review,
compatibility or migration evidence, rollback/fallback, and target-host verification.

Target-host evidence from `ubuntu@webtop:~/wiki-supressor/suppressor`:

```text
./suppressor server-start
Error: Failed to parse config file config.toml

Caused by:
    TOML parse error at line 1, column 1
      |
    1 | [wiki]
      | ^
    missing field `realtime`
```

Config-stability verdict: BLOCK production trust. The deployed server config diverges from the
reviewed tracked baseline because the current baseline has a `[realtime]` section, while the target
host config used by that command does not. This evidence is a config-load failure before daemon
trust, not a launch success.

No config edit was approved or performed by this T039 pass. Do not add `[realtime]` or any other
section to the server config as a quick background fix. The next valid path must be one of:

- a human-reviewed migration of the target-host config to the reviewed tracked baseline, with a
  backup/rollback path and post-migration `server-start` evidence
- a human-reviewed backward-compatible loader or migration-needed diagnostic, with tests and a new
  server build before deployment trust

The active approval packet is in
`specs/001-real-time-suppression/questions.md` and
`specs/001-real-time-suppression/review-queue.md`. Q001 must be answered before any T040 launch
evidence is accepted.

2026-05-07 update: Q001 is answered. Path 1 is approved: target-host config migration to the
reviewed tracked baseline. The human operator reports that the server config was updated and the
daemon was started. The next required evidence is T040: non-secret `server-start` receipt,
PID/runtime/log paths, daemon-owned status freshness, and terminal logout survival.

Later 2026-05-07 server-running evidence showed a live process, but the status remained
non-healthy because launch-path, PID-file, runtime-status, and detached-log evidence did not agree.
That is blocked T040 evidence, not a successful launch proof. Preserve a possibly protective daemon
while gathering evidence, but do not trust the deployment until the mismatch is resolved through a
matching receipt, safe fresh `server-start`, or rollback to the last trusted workflow.

T040 may use an already-started daemon only if the operator evidence ties that process to the
Q001-approved config migration and the deployed binary's
`./suppressor --config ./config.toml server-start` command. If the original receipt is unavailable,
the safe replacement evidence is the same receipt fields from daemon-owned status and local process
inspection: mode, PID, binary path, config path, PID file, `runtime_status.json` path, detached log
path, and `launch_path=server-start`. Record a safe artifact identity tuple for that launched
binary, such as resolved path plus size/mtime from `stat`, and tie it to the same PID and
daemon-owned status file. `runtime_status.json` must match the live PID when present, have a daemon
timestamp or file mtime no older than 10 seconds at inspection, and remain fresh on a second
inspection within 10 seconds. After closing the SSH terminal and reconnecting, the same PID must be
alive and daemon-owned status must still be fresh. Do not record `.env` values, passwords, cookies,
tokens, session material, raw hidden text, sensitive article content, or full unredacted logs.

2026-05-13 rsynced update: the target-host bundle safely proved that the reviewed `[realtime]`
config is present and that one `server-start` run wrote aligned PID/status/log metadata. Safe facts
from that bundle include `launch_path.kind=server-start`, `launch_path.pid=28423`,
`launch_path.binary_path=/home/ubuntu/wiki-supressor/suppressor/suppressor`,
`launch_path.config_path=config.toml`, `launch_path.runtime_status_file=./state/runtime_status.json`,
`launch_path.log_path=./state/daemon.log`, and a `runtime_status.json` file mtime of
`2026-05-13 22:36:45 +0200`. Treat this as partial T040 launch evidence only; logout-survival and
current-binary proof are still missing.

2026-05-14 rsynced relaunch update: the follow-up bundle still lacked `live_lane`,
`background_lane`, and `latency`, and its recovery summary still showed the legacy shape rather
than current candidate-first evidence. Therefore the active blocker is deployment identity and
launch workflow trust, not another unresolved local crash-policy design.

Rollback or fallback until then: keep target-host deployment blocked, use the last trusted
binary/config/state workflow if one exists, or use manual emergency catch-up while a reviewed fix is
prepared. No T040 launch evidence counts until the launch evidence gate has a matching receipt or
explicit fallback path.

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
For T052 preflight, the same run must also prove current-MVP status shape: `runtime_status.json`
should include `live_lane`, `background_lane`, and `latency`, and if a recovery pass runs it should
surface candidate-first aggregate fields rather than only the older legacy recovery summary. Missing
receipt fields, missing config, missing secrets, unwritable state/log paths, duplicate daemon,
startup timeout, stale PID, stale runtime status, launch-path/PID mismatch, non-`server-start`
launch labels, missing logout-survival evidence, missing safe artifact identity, legacy-only status
shape, or unhealthy startup evidence blocks deployment trust. A running daemon may continue
protecting edits while evidence is incomplete, but T040 and MVP deployment trust stay blocked until
the missing or mismatched evidence is resolved and recorded.

## Active Live-Hide Incident

The operator reported a screenshot where a watched sensitive page still had a public hide action
after an operator-account edit. The concrete page, actor, and revision identifiers are intentionally
omitted from repository docs and tests. Treat this as failed T041 live-hide evidence. That page is
expected to be watched, and operator-account eligible edits must not be filtered out. If the exposed
revision ID is known, hide it manually or run emergency catch-up before waiting for code changes.

For the hotfix, collect only safe server facts: PID/binary, launch path, runtime-status freshness,
last observed event, last matching title/revision, latest outcome, latest actionable issue, queue
depth, processed-revision presence for the exposed revision if known, and whether the watched page is
in the server cache. Do not copy secrets or raw sensitive logs. Fix the first failed boundary in the
live path before spending time on resource samples or broader close-out.

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
fields to record for T042 are queue depth, queue capacity, in-flight count, concurrency limit, latest
saturation time, and latest saturation reason. The legacy `realtime.queue_depth` remains the live
queue depth for compatibility. Recent timing evidence is under `realtime.latency` for
observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden.

For deployment evidence, do not treat a quiet background lane as proof of live health. A good
target-host smoke check records a live or controlled dry-run edit while reconciliation, catch-up, or
verification is either active or queued, then confirms the live lane reacts without waiting for the
background lane to drain. This check has no fixed internal millisecond SLA; the release target is
still the external hide evidence in the feature spec.

## 2026-04-28 Baseline Evidence

The current local state footprint is:

- `runtime_status.json`: `3780` bytes
- `nightly_sweep_progress.json`: `393436` bytes
- `processed_revids.json`: `24116` bytes
- `suppression_list_cache.json`: `168984` bytes
- `last_event_id.txt`: `149` bytes
- `daemon.pid`: `6` bytes

The measured total for `state/` is `590471` bytes. `nightly_sweep_progress.json` and
`suppression_list_cache.json` are the dominant files; `runtime_status.json` is small by comparison.
The current `resource_economy.state_bytes_recent` field is still `0`, so resource-byte accounting is
not yet reflecting the real on-disk total.

The current runtime snapshot on disk shows the remaining status-integrity problems that the recovery
work is closing:

- `realtime.state="catching-up"` with `catchup_active=true` and `backoff_until=null`
- `last_event_observed_at="2026-04-28T19:00:45.173840784Z"` with `current_lag_seconds=0`
- `last_freshness_probe_at="2026-04-28T19:00:45.500000000Z"`
- `latest_outcome.mode="live"` and `latest_outcome.outcome="blocked"` with `reason_code="auth-session"`
- `latest_recovery_warnings=[]` and `latest_recovery_summary.unresolved_items=[]`
- `reconciliation.last_result="failed: non-json-response: Failed to decode JSON response: expected value at line 1 column 1"`

This means the persisted baseline currently shows a fresh polling cycle, no retained unresolved sample,
no persisted warning summary growth, and a still-mixed operational picture where the realtime state can
remain in `catching-up` while the latest actionable live outcome is already blocked for another reason.

Older runtime-status artifacts currently load safely when new fields are missing. The regression test in
`src/state.rs` proves that older JSON without the newer realtime fields falls back to
`realtime.state="unknown"`, `stale_threshold_seconds=10`, empty recovery warnings, and no backoff
instead of failing to deserialize.

The TUI runs one-shot operator actions as their own commands:

- `Emergency catch-up` runs `emergency-catchup`
- `Coverage: Last 24 hours` runs `coverage-last-24h --report-only`
- control-center messages are labeled with the `[control]` prefix

One-shot command results are written to bounded `command_report.json` and rendered as command output.
They do not overwrite daemon-owned `runtime_status.json` and must not be treated as proof that the
daemon is healthy or running.

The live-output pane now avoids the wrapped-row follow bug by not wrapping log lines at all. Follow mode
tracks raw logical lines, so the newest visible entry stays aligned with the newest stored entry. The
tradeoff is that long log lines are clipped by terminal width instead of reflowing; only the status
panes still use wrapped paragraph rendering.

## Operational Notes

- use `make tui` for local supervision
- use the binary command `coverage-last-24h --report-only` or the TUI `Coverage: Last 24 hours`
  action for the rolling daily verification preset
- keep logs free of secrets and suppressed payloads
- use `make reload-cache` only for watched-list cache diagnostics
- use `make emergency-catchup ARGS="--dry-run"` for a bounded recent recovery check
- use `make coverage-report ARGS="--start <RFC3339> --report-only"` for accident-window accounting
- use `make nightly-sweep-now` as a slower safety-net reconciliation action
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

1. Open `make tui` and check `Realtime`, lag, latest outcome, recovery trigger, and latest error.
2. If realtime is stale, reconnecting, unhealthy, or blocked, do not rely on the daemon process line
   alone.
3. Run `make emergency-catchup ARGS="--dry-run"` to inspect the recent default window without hiding.
4. If the report is correct and auth is healthy, run `make emergency-catchup` to queue unresolved
   eligible edits for hiding.
5. For a known accident window, run `make coverage-report ARGS="--start <RFC3339> --end <RFC3339> --report-only"`.
6. For the routine rolling window, use `./suppressor --config ./config.toml coverage-last-24h --report-only`
   or the TUI `Coverage: Last 24 hours` action.
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

Runtime status and the TUI show the latest source-refresh outcome, added/removed counts, catch-up
scope, classified refresh errors, and the latest catch-up summary.

## 2026-04-25 Warning-Storm Lesson

The terminal warning storm was consistent with one root cause repeated across many watched pages:
catch-up revision queries failed and logged once per title. The specific timestamp lesson is that
MediaWiki API timestamp parameters must use UTC second precision with no fractional part; fractional
`rvstart` values can be rejected as `badtimestamp`, causing every page query in a catch-up run to
fail. The code now uses a shared MediaWiki timestamp formatter for revision queries and EventStreams
`since` values, and catch-up coalesces repeated query failures into a compact summary.
