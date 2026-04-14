# Suppressor Operations

Navigation: [README](../README.md) | [Docs index](../docs/README.md) | [Architecture analysis](../docs/architecture-analysis.md) | [Implementation spec](implementation.md)

## First Run

1. Create `suppressor/.env` from the auth variable list below.
2. Open `Special:BotPasswords` on the target wiki and create a bot password for the account you
   want to use.
3. Copy the full bot login, including the `@label` suffix from `Special:BotPasswords`, into
   `BEWIKI_BOT_USERNAME`.
4. Copy the generated bot password secret into `BEWIKI_BOT_PASSWORD`.
5. Verify `suppressor/config.toml` points at the local `state/` directory, carries the
   intended wiki endpoint defaults, and matches the right bot settings.
6. Run `make env-check` to confirm both files are present.
7. Run `make check-auth` to verify the bot login and rights.
8. Run `make dry-run` before the first live start.
9. Use `make run` for a local daemon, or install the systemd unit once the local flow is clean.

Public versus internal naming:

- prefer the public binary name `suppressor`
- keep the existing directory `suppressor/`
- keep the current `BEWIKI_*` environment variable names unless you also change `[auth]` in
  `config.toml`

## Required Access

Use a dedicated bewiki bot account.

Required local groups:

- `bot`
- `sysop`

Required bot-password grants:

- `basic`
- `delete`
- `highvolume`

Not required:

- `suppressrevision`

The daemon performs public-only hiding with `suppress=no`.

If you are adapting the daemon to another local wiki, the same `Special:BotPasswords` flow
applies. Update `config.toml` and `.env` together, then verify the local wiki's group rights and
event stream endpoint before you rely on the daemon for production use.

## `.env` Contract

The normal operator workflow uses a dedicated local `.env` file for auth.
The loader also accepts matching process env overrides for the same variable names.

Default path:

- `suppressor/.env`

Required auth variables:

```dotenv
BEWIKI_BOT_USERNAME=BOT_USERNAME_ONLY
BEWIKI_BOT_PASSWORD=BOT_PASSWORD_ONLY
```

Optional runtime overrides:

```dotenv
BEWIKI_API_URL=https://be.wikipedia.org/w/api.php
BEWIKI_STREAM_URL=https://stream.wikimedia.org/v2/stream/recentchange
BEWIKI_USER_AGENT="bewiki-revdel-daemon/1.0 (contact on-wiki)"
```

Rules:

- never commit `.env`
- never print or log secret values
- never include secrets in panic text, traces, metrics, or crash dumps
- fail fast if the required auth values are missing, without echoing the secret
- allow override paths operationally, but keep the suppressor-local env file as the documented default
- keep any optional API URL, stream URL, and user agent overrides aligned with `config.toml` unless there is an intentional deployment-specific override

BotPasswords reminder:

- `BEWIKI_BOT_USERNAME` should be the full login name shown by `Special:BotPasswords`, including
  the `@label` suffix
- `BEWIKI_BOT_PASSWORD` should be the generated bot password secret, not the label
- choose a clear suffix like `revdel-watch` so the active password is easy to identify later
- unlike Biblio, Suppressor does not split the account name and suffix into separate variables
- both `check-auth` and the live daemon hard-fail unless the authenticated session exposes the
  `bot`, `deleterevision`, and `deletelogentry` rights

## `config.toml` Contract

Use `config.toml` for non-secret runtime configuration.
The wiki API URL, stream URL, and user agent default from this file unless process env or `.env` overrides them.

Example:

```toml
[wiki]
api_url = "https://be.wikipedia.org/w/api.php"
stream_url = "https://stream.wikimedia.org/v2/stream/recentchange"
wiki_code = "bewiki"
server_name = "be.wikipedia.org"
user_agent = "bewiki-revdel-daemon/1.0 (contact on-wiki)"

[auth]
username_env = "BEWIKI_BOT_USERNAME"
password_env = "BEWIKI_BOT_PASSWORD"

[suppression_list]
title = "Удзельнік:Wizardist/SuppressionList"
cache_file = "./state/suppression_list_cache.json"
metadata_recheck_seconds = 600

[matching]
drop_canary = true
exact_title_match = true

[revdel]
hide = ["user", "comment"]
suppress = false
reason = "Emergency public RevDel on sensitive-list page; hide username and comment pending oversight resolution"

[queue]
capacity = 100

[state]
dir = "./state"
last_event_id_file = "./state/last_event_id.txt"
processed_revids_file = "./state/processed_revids.json"
nightly_sweep_progress_file = "./state/nightly_sweep_progress.json"
runtime_status_file = "./state/runtime_status.json"
pid_file = "./state/daemon.pid"

[retry]
stream_backoff_initial_ms = 1000
stream_backoff_max_ms = 30000
api_max_retries = 3
since_recovery_seconds = 60

[nightly_sweep]
enabled = true
timezone = "Europe/Minsk"
start_time = "02:00"
page_concurrency = 2
batch_sleep_ms = 250

[current_day_recheck]
enabled = true
min_delay_seconds = 3600
max_delay_seconds = 21600

[logging]
level = "info"
format = "json"

[metrics]
enabled = true
bind = "127.0.0.1:9808"
```

Fixed v1 behavior around that config:

- the suppression list is a plain newline-separated page list, not a mixed-markup input surface
- the wiki endpoint, stream URL, and user agent default from `config.toml`, with optional `BEWIKI_API_URL`, `BEWIKI_STREAM_URL`, and `BEWIKI_USER_AGENT` overrides
- redirect-derived watched titles are maintained by reconciliation, not by cache reload
- nightly reconciliation is checkpointed per page instead of re-scanning every page's full history on every run
- `reload-cache` refreshes listed-title source data only and leaves redirect-derived watched titles to reconciliation

Operational commands:

- `run --config /path/to/config.toml`
- `check-auth --config /path/to/config.toml`
- `reload-cache --config /path/to/config.toml`
- `dry-run --config /path/to/config.toml`
- `hide-revid <id> --config /path/to/config.toml`
- `nightly-sweep-now --config /path/to/config.toml`
- `print-effective-config --config /path/to/config.toml`

Preferred installed command:

- `suppressor`

`print-effective-config` must redact secrets.

Local deployment helpers:

- `make check`
- `make lint`
- `make fmt`
- `make build`
- `make release`
- `make check-auth`
- `make dry-run`
- `make run`

## State Directory

Expected files:

- `last_event_id.txt`
- `processed_revids.json`
- `suppression_list_cache.json`
- `nightly_sweep_progress.json`
- `runtime_status.json`
- `daemon.pid`

State handling rules:

- writes are atomic
- missing files are rebuilt on startup
- `nightly_sweep_progress.json` stores per-page checkpoints for reconciliation
- `runtime_status.json` stores the current daemon state, last operator notice, and live reconciliation progress for the local supervisor TUI
- `suppression_list_cache.json` stores listed titles plus the reconciliation-maintained watched set and redirect map
- page and revision transaction locks are RAM-only runtime state
- cache and progress files are local machine state, not tracked source files

Operational boundary summary:

- `config.toml` is human-owned non-secret policy and the default wiki endpoint/user-agent source
- `.env` is secret/operator-local input plus optional runtime overrides
- `last_event_id.txt`, `processed_revids.json`, `nightly_sweep_progress.json`, and `runtime_status.json` are durable operational state
- `suppression_list_cache.json` is derived cache state
- `daemon.pid` and in-memory locks/queues are ephemeral coordination state

## Logging And Metrics

Structured log fields per action:

- timestamp
- page title
- revision ID
- EventStreams event ID
- RC username
- action mode: immediate or nightly
- result
- retry count
- latency in milliseconds
- error code on failure

Metrics surface:

- Prometheus endpoint

Minimum metrics:

- `events_received_total`
- `events_bewiki_total`
- `events_matched_total`
- `revdel_attempt_total`
- `revdel_success_total`
- `revdel_failure_total`
- `cache_reload_total`
- `nightly_sweep_pages_total`
- `nightly_sweep_revisions_checked_total`
- `nightly_sweep_revisions_hidden_total`
- `current_day_recheck_run_total`
- `event_reconnect_total`
- `queue_depth`
- `immediate_hide_latency_ms`
- `event_to_api_submit_latency_ms`

## Service Operation

Recommended `systemd` unit:

```ini
[Unit]
Description=suppressor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/repo/suppressor
EnvironmentFile=/path/to/repo/suppressor/.env
ExecStart=/path/to/daemon run --config /path/to/config.toml
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/path/to/repo/suppressor/state

[Install]
WantedBy=multi-user.target
```

Recommended live control:

- `reload-cache` targets the running daemon via the PID file and a Unix signal
- `nightly-sweep-now` targets the running daemon via the PID file and a Unix signal
- if a sweep is already active, `nightly-sweep-now` queues one pending rerun instead of starting parallel work

## Runbook Notes

- use `check-auth` before first production run
- use `dry-run` to validate stream matching without calling `revisiondelete`
- use `make check` before deployment to verify formatting, linting, and tests
- use `make release` when you need the optimized daemon binary
- use the first real dry runs to measure runtime and publish an initial supported scale envelope
- `dry-run` does not advance stream position, processed revision state, or sweep checkpoints
- same-account edits are still subject to hiding
- the source list should contain plain page titles separated by newlines
- redirect-derived watched titles are refreshed during nightly and current-day reconciliation
- immediate live coverage is best-effort across short outages; longer gaps are repaired by the reconciliation passes
- the daemon performs randomized current-day reconciliation between 1 and 6 hours in addition to the nightly run
- monitor `revdel_failure_total`, `event_reconnect_total`, and queue depth
- treat permission loss or repeated unrecoverable auth failures as a service-stop condition
- `action=revisiondelete` does not provide a minor-edit switch; these actions cannot be marked minor by the daemon
- `action=revisiondelete` also does not provide a separate bot flag parameter; bot-marked log
  entries depend on the authenticated account exposing the `bot` right, and the daemon now
  treats that as a startup requirement
- the daemon was first developed for be.wiki, so be especially careful when changing the wiki endpoint or rights model for another local wiki

## Deployment Checklist

1. Run `make check` in `suppressor/`.
2. Run `make check-auth` with the production `.env`.
3. Run `make dry-run` and confirm the daemon authenticates, connects to EventStreams, and matches expected titles without calling `revisiondelete`.
4. Build the release binary with `make release`.
5. Install the sample `systemd` unit with the real repo path, release binary path, config path, and `.env` path.
6. Start the service and confirm `state/daemon.pid`, `state/runtime_status.json`, and `state/suppression_list_cache.json` are created.
7. Trigger `make nightly-sweep-now` from another terminal and confirm the status pane or logs show the queued reconciliation run.
8. After bot rights are granted, verify the service account’s log entries are hidden in the default RecentChanges view.

## References

- [bewiki group rights](https://be.wikipedia.org/wiki/%D0%90%D0%B4%D0%BC%D1%8B%D1%81%D0%BB%D0%BE%D0%B2%D0%B0%D0%B5%3AListGroupRights)
- [MediaWiki bot passwords](https://www.mediawiki.org/wiki/Manual%3ABot_passwords)
- [MediaWiki revisiondelete API](https://www.mediawiki.org/wiki/API%3ARevisiondelete)
