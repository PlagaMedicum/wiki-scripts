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
6. Move to `make run` or the systemd unit only after the dry run is clean.

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

## State Files

Current runtime state lives under `state/`:

- `last_event_id.txt`
- `processed_revids.json`
- `suppression_list_cache.json`
- `nightly_sweep_progress.json`
- `runtime_status.json`
- `daemon.pid`

These are local machine files, not source-of-truth docs.

## Operational Notes

- use `make tui` for local supervision
- keep logs free of secrets and suppressed payloads
- use `make reload-cache` only for watched-list cache diagnostics
- use `make emergency-catchup ARGS="--dry-run"` for a bounded recent recovery check
- use `make coverage-report ARGS="--start <RFC3339> --report-only"` for accident-window accounting
- use `make nightly-sweep-now` as a slower safety-net reconciliation action
- treat auth or rights loss as a stop-condition, not a soft warning
- treat generic repeated `Failed to decode JSON response` or per-page catch-up warnings as an
  incident symptom; the daemon should now show one classified warning summary with count, class/API
  code, HTTP status when known, retryability, and a few safe sample titles

## Operational Targets

- target 95% of controlled realtime hides under one second and 99% under five seconds
- report p95 and p99 from controlled runs before claiming release readiness
- prioritize newer edits first during recovery after disconnect or restart
- treat a stale realtime stream as unhealthy after the configured 10-second threshold
- catch up the default 30-minute window within the configured recovery target where wiki/API health allows it
- stop the service on missing rights, broken auth, persistent API failure, or malformed
  suppression-list input

## Incident Response Flow

1. Open `make tui` and check `Realtime`, lag, latest outcome, recovery trigger, and latest error.
2. If realtime is stale, reconnecting, unhealthy, or blocked, do not rely on the daemon process line
   alone.
3. Run `make emergency-catchup ARGS="--dry-run"` to inspect the recent default window without hiding.
4. If the report is correct and auth is healthy, run `make emergency-catchup` to queue unresolved
   eligible edits for hiding.
5. For a known accident window, run `make coverage-report ARGS="--start <RFC3339> --end <RFC3339> --report-only"`.
6. Treat unresolved items as open exposure until each one has a reason, owner, and next action.

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
