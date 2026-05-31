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

- one production daemon path: recentchanges polling, watched-title matching, RevDel, bounded catch-up
- one detached `server-start` supervisor that restarts the daemon child after exits
- one current production baseline aimed at be.wiki
- one rsync-ready aarch64 binary launch path for the server
- legacy TUI, reconciliation, and report commands retained for manual diagnostics

Future multiwiki support is possible, but it is not the current runtime model.

## Quick Start

Run from `suppressor/`:

```bash
cp .env.example .env
make env-check
make check-auth
make smoke-test
make dry-run
```

Example `.env`:

```dotenv
BEWIKI_BOT_USERNAME=YourBot@revdel-watch
BEWIKI_BOT_PASSWORD=REDACTED
```

`BEWIKI_BOT_USERNAME` uses the full BotPasswords login in the form `username@label`.

For the current rsync server path, build the aarch64 musl binary and start it on the server from
the deployed directory:

```bash
make build-server
./suppressor --config ./config.toml server-start
```

`server-start` starts the daemon detached from the SSH terminal, writes a PID/runtime-status/log
receipt, and is trusted only after the PID and `runtime_status.json` keep updating after reconnect.

## Common Commands

- `make env-check`
- `make check-auth`
- `make smoke-test`
- `make dry-run`
- `make run`
- `make tui`
- `make reload-cache`
- `make emergency-catchup ARGS="--dry-run"`
- `make coverage-report ARGS="--start 2026-04-24T00:00:00Z --report-only"`
- `make nightly-sweep-now`
- `make build`
- `make build-server`
- `make release`
- `make check`

## Scope Boundary

Current scope:

- MediaWiki recentchanges polling
- watched-title matching
- immediate public RevDel for `user|comment`
- bounded startup and gap catch-up
- supervisor restart after daemon exits
- truthful realtime health reporting
- bounded emergency catch-up and coverage reporting

Not current scope:

- EventStreams as the production live source
- TUI, reconciliation, and nightly verification as required live-hide paths
- broader moderation platform work
- remote multi-operator control
- public network service exposure

## Current Baseline

The checked-in config is the current working be.wiki production baseline. It is a real baseline,
not a promise that every other wiki is already supported.

## Realtime Health

The daemon persists a realtime section in `runtime_status.json`. Process state and protection state
are separate so "running" is not treated as "hiding". Important states are:

- `healthy`: recentchanges polling is fresh and no catch-up is active
- `catching-up`: bounded recovery is checking recent watched-page edits
- `degraded`: polling or hiding has failed but the daemon is alive and retrying
- `degraded` with a quarantined unresolved item: RevDel returned a non-retryable per-revision
  denial; the daemon keeps protecting new edits and does not hammer the API on that revision
- `blocked`: auth/session failures prevent hiding

Recovery starts from the persisted recentchanges poll cursor when that anchor exists; otherwise it
uses the bounded recent emergency window. Manual cache reload, TUI, reconciliation, and one-shot
reports remain diagnostic or fallback actions; they do not replace daemon-owned realtime truth.

## Further Reading

- [`docs/runtime-boundaries.md`](docs/runtime-boundaries.md)
- [`docs/testing-strategy.md`](docs/testing-strategy.md)
- [`docs/operations.md`](docs/operations.md)
- [`docs/implementation.md`](docs/implementation.md)
