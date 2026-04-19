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
- use `make reload-cache` and `make nightly-sweep-now` against a running daemon
- treat auth or rights loss as a stop-condition, not a soft warning

## Operational Targets

- target hide latency under one second when possible
- prioritize newer edits first during recovery after disconnect or restart
- treat recovery within a few minutes as the working target
- stop the service on missing rights, broken auth, persistent API failure, or malformed
  suppression-list input
