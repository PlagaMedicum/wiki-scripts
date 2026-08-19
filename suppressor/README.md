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
cp config.example.toml my-wiki.toml
cp .env.example .env
make env-check CONFIG=./my-wiki.toml
```

Every invocation requires `CONFIG=/path/to/wiki.toml`. `config.bewiki.toml` is the existing
Belarusian production profile; `config.example.toml` is the starting point for another wiki.

The optional environment file includes:

```dotenv
WIKI_BOT_USERNAME=YourBot@revdel-watch
WIKI_BOT_PASSWORD=REDACTED
```

`WIKI_BOT_USERNAME` must use the full BotPasswords login in the form `username@label`.
Process environment values take precedence over `.env`; `.env` remains optional for Toolforge
and local deployments. Endpoint and user-agent overrides are optional `WIKI_API_URL`,
`WIKI_STREAM_URL`, and `WIKI_USER_AGENT` values.

Set the selected TOML profile's wiki URLs, wiki code, watched pages, RevDel reason, and user
agent before running against any real wiki.

## Basic Usage

Recommended first steps:

```bash
make check-auth CONFIG=./my-wiki.toml
make smoke-test CONFIG=./my-wiki.toml
make dry-run CONFIG=./my-wiki.toml
```

Common commands:

- `make run CONFIG=./my-wiki.toml`
- `make status CONFIG=./my-wiki.toml`
- `make health CONFIG=./my-wiki.toml`
- `make last-edits CONFIG=./my-wiki.toml ARGS="--limit 20"`
- `make perf CONFIG=./my-wiki.toml`
- `make reload-cache CONFIG=./my-wiki.toml`
- `make catch-up-now CONFIG=./my-wiki.toml`
- `make emergency-catchup CONFIG=./my-wiki.toml ARGS="--dry-run"`
- `make coverage-report CONFIG=./my-wiki.toml ARGS="--start 2026-04-24T00:00:00Z --report-only"`

Development and release commands:

- `make build`
- `make build-server`
- `make release`
- `make check`

## Server Deployment

For the current detached server deployment path:

```bash
make build-server
./suppressor --config ./config.bewiki.toml server-start
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
