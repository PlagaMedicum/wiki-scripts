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

## Authoritative Launch-Path Baseline

Treat the active supervisor path on this host as the source of truth for whether protection is
running.

- The normal local operator workflow is `make tui`, which starts and supervises a TUI-managed child
  daemon.
- The rsync server workflow is `./suppressor --config ./config.toml server-start` from the deployed
  directory. It is authoritative only for the detached child it starts and verifies.
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
- EventStreams URL
- watched-list title
- request-page triggers, currently `Вікіпедыя:Запыты да схавальнікаў`
- RevDel reason
- realtime stale/read timeouts
- bounded catch-up window and maximum revisions per run
- catch-up warning sample retention
- reconciliation timing
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

Rollback or fallback until then: keep target-host deployment blocked, use the last trusted
binary/config/state workflow if one exists, or use manual emergency catch-up while a reviewed fix is
prepared. No T040 launch evidence counts until this config gate has a reviewed pass path.

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

After copying the binary, `config.toml`, and the operator-managed `.env` or equivalent secret input
to the server, start the daemon with one binary command:

```bash
./suppressor --config ./config.toml server-start
```

The receipt must include mode, PID, config path, PID file, `runtime_status.json` path, detached log
path, and `launch_path=server-start`. Trust this launch only after reconnecting to the server and
confirming the same PID is still alive, stdout/stderr are going to the printed log path, and
daemon-owned `runtime_status.json` continues updating. Missing config, missing secrets, unwritable
state/log paths, duplicate daemon, startup timeout, stale PID, stale runtime status, or unhealthy
startup evidence blocks deployment trust.

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
- `last_freshness_probe_at=null`
- `latest_outcome.mode="live"` and `latest_outcome.outcome="blocked"` with `reason_code="auth-session"`
- `latest_recovery_warnings=[]` and `latest_recovery_summary.unresolved_items=[]`
- `reconciliation.last_result="failed: non-json-response: Failed to decode JSON response: expected value at line 1 column 1"`

This means the persisted baseline currently shows a fresh stream event, no retained unresolved sample,
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
- treat a stale realtime stream as unhealthy after the configured 10-second threshold
- catch up the default 30-minute window within the configured recovery target where wiki/API health allows it
- recover from `last_successful_hide_at` when present instead of silently truncating to a newer
  arbitrary recent window
- record one rolling `Last 24 hours` verification and one nightly full watched-set recheck during
  each uninterrupted 24-hour daemon period
- stop the service on missing rights, broken auth, persistent API failure, or malformed
  suppression-list input

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
