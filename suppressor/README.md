# Suppressor

`suppressor` is a Rust daemon for fast public RevDel on matched wiki revisions. It is intentionally
narrow: watch the configured workflow pages, detect relevant edits quickly, and hide public
`user|comment` metadata without trying to become a general moderation platform.

It is currently running 24/7 on `be.wikipedia.org`, supporting suppressor workflow with faster
reaction time, but it should be easy to adapt it for other wikis.

## What It Does

- polls MediaWiki `recentchanges`
- matches revisions against a watched-title set
- sends public RevDel for `user|comment`
- performs bounded startup and recovery catch-up
- exposes operator commands for status, health, cache reload, and manual recovery
- supports detached `server-start` deployment for the current server workflow

The checked-in config and docs describe the current be.wiki production baseline. They are not a
promise that every wiki is supported out of the box.

## Install Dependencies

Base requirements:

- Rust toolchain
- `make`
- `cargo-deny` for `make audit` and `make check`
- `cargo-zigbuild` plus Zig when building the server binary with `make build-server`

Typical setup:

```bash
rustup toolchain install stable
cargo install cargo-deny cargo-zigbuild
```

For local development and normal builds, the standard Rust toolchain is enough. The extra
cross-build tooling is only needed for the current server artifact flow.

## Configure

Run from `suppressor/`:

```bash
cp .env.example .env
make env-check
```

The example environment file includes:

```dotenv
BEWIKI_API_URL=https://be.wikipedia.org/w/api.php
BEWIKI_STREAM_URL=https://stream.wikimedia.org/v2/stream/recentchange
BEWIKI_BOT_USERNAME=YourBot@revdel-watch
BEWIKI_BOT_PASSWORD=REDACTED
BEWIKI_USER_AGENT="bewiki-revdel-daemon/1.0 (contact on-wiki)"
```

`BEWIKI_BOT_USERNAME` must use the full BotPasswords login in the form `username@label`.

Review `config.toml` before running against any real wiki.

## Basic Usage

Recommended first steps:

```bash
make check-auth
make smoke-test
make dry-run
```

Common commands:

- `make run`
- `make status`
- `make health`
- `make last-edits ARGS="--limit 20"`
- `make perf`
- `make reload-cache`
- `make catch-up-now`
- `make emergency-catchup ARGS="--dry-run"`
- `make coverage-report ARGS="--start 2026-04-24T00:00:00Z --report-only"`

Development and release commands:

- `make build`
- `make build-server`
- `make release`
- `make check`

## Server Deployment

For the current detached server deployment path:

```bash
make build-server
./suppressor --config ./config.toml server-start
```

`server-start` launches the daemon detached from the terminal, writes a PID/runtime-status/log
receipt, and restarts the daemon child after exits. Trust the launch only after reconnecting and
confirming that the PID and `runtime_status.json` continue updating.

## Health Model

The daemon writes realtime state to `state/runtime_status.json`. Process liveness and protection
health are separate.

Important states:

- `healthy`: polling is fresh and no catch-up is active
- `catching-up`: bounded recovery is running
- `degraded`: polling or hiding failed, but the daemon is still running and retrying
- `blocked`: auth or session problems prevent hiding

One-shot command output in `command_report.json` is useful diagnostic evidence, but it is not the
same thing as daemon-owned realtime health.

## Further Reading

- [`docs/runtime-boundaries.md`](docs/runtime-boundaries.md)
- [`docs/testing-strategy.md`](docs/testing-strategy.md)
- [`docs/operations.md`](docs/operations.md)
- [`docs/implementation.md`](docs/implementation.md)
