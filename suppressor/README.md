---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Operator entry points and current documented scope for suppressor.
  source: .specify/doc-registry.json
---

# Suppressor


`suppressor` is the Rust daemon for rapid public RevDel on matched wiki revisions. This tool stays
narrow on purpose: fast reaction, strict runtime behavior, and conservative handling of sensitive
data.

## Current Shape

- one daemon
- one local TUI / supervisor client
- one current production baseline aimed at be.wiki
- one local machine deployment model

Future multiwiki support is possible, but it is not the current runtime model.

## Quick Start

Run from `suppressor/`:

```bash
cp .env.example .env
make env-check
make check-auth
make dry-run
```

Example `.env`:

```dotenv
BEWIKI_BOT_USERNAME=YourBot@revdel-watch
BEWIKI_BOT_PASSWORD=REDACTED
```

`BEWIKI_BOT_USERNAME` uses the full BotPasswords login in the form `username@label`.

## Common Commands

- `make env-check`
- `make check-auth`
- `make dry-run`
- `make run`
- `make tui`
- `make reload-cache`
- `make emergency-catchup ARGS="--dry-run"`
- `make coverage-report ARGS="--start 2026-04-24T00:00:00Z --report-only"`
- `make nightly-sweep-now`
- `make build`
- `make release`
- `make check`

## Scope Boundary

Current scope:

- EventStreams ingestion
- watched-title matching
- immediate public RevDel for `user|comment`
- reconciliation and backfill
- local TUI supervision
- realtime health reporting
- bounded emergency catch-up and coverage reporting

Not current scope:

- broader moderation platform work
- remote multi-operator control
- public network service exposure

## Current Baseline

The checked-in config is the current working be.wiki production baseline. It is a real baseline,
not a promise that every other wiki is already supported.

## Realtime Health

The daemon now persists a dedicated realtime section in `runtime_status.json`. The TUI shows realtime
state separately from daemon process state and reconciliation state so "running" is not treated as
"hiding". Important states are:

- `healthy`: the stream is fresh and no catch-up is active
- `catching-up`: bounded recovery is checking recent watched-page edits
- `stale` or `reconnecting`: the stream is delayed or being reopened
- `unhealthy`: the realtime path could not prove protection
- `blocked`: rights, session, or wiki-side failures prevent hiding

Manual cache reload and nightly/current-day reconciliation remain diagnostic or fallback actions.
They are not the normal path for newly published sensitive edits.

## Further Reading

- [`docs/runtime-boundaries.md`](docs/runtime-boundaries.md)
- [`docs/testing-strategy.md`](docs/testing-strategy.md)
- [`docs/operations.md`](docs/operations.md)
- [`docs/implementation.md`](docs/implementation.md)
