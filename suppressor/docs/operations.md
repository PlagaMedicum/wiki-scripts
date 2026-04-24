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
- RevDel reason
- reconciliation timing
- metrics bind

Treat that file as the current working baseline, not as a guarantee that every wiki already fits it.

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
