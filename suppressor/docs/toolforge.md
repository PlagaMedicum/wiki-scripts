# Toolforge deployment

Run one independent `suppressor` instance per wiki configuration. The deployment contract is the
compiled executable, a per-wiki TOML file, and credentials supplied by Toolforge environment
variables. It runs in the foreground: Toolforge Kubernetes restarts the continuous job; do not use
`server-start` there.

## Prerequisites

Create or join a [Toolforge Tool Account](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Quickstart),
and ensure the bot account has the required MediaWiki revision-deletion rights for the target wiki.
Use a dedicated Wikimedia BotPassword, preferably scoped to this service, rather than an account's
ordinary password.

Build on a machine with Rust, Zig, and `cargo-zigbuild`:

```bash
make build-toolforge
```

This produces `target/x86_64-unknown-linux-musl/release/suppressor`. Upload it from the build
machine, then log in as the Tool Account:

```bash
ssh <tool>@login.toolforge.org 'mkdir -p "$HOME/bin" "$HOME/config" "$HOME/state"'
scp target/x86_64-unknown-linux-musl/release/suppressor \
  <tool>@login.toolforge.org:/data/project/<tool>/bin/suppressor
ssh <tool>@login.toolforge.org
chmod 0755 "$HOME/bin/suppressor"
```

The intended shared-storage layout is:

```text
/data/project/<tool>/
├── bin/suppressor
├── config/wiki.toml
└── state/
```

## Configure and authenticate

Copy `config.example.toml` to `$HOME/config/wiki.toml`, then replace every example wiki URL,
hostname, wiki code, User-Agent, suppression-list title, request-page title, and RevDel reason.
Set every state path in `[state]` and `suppression_list.cache_file` to an absolute shared path (TOML
does not expand `$HOME`), for example:

```toml
cache_file = "/data/project/<tool>/state/suppression_list_cache.json"

[state]
dir = "/data/project/<tool>/state"
last_event_id_file = "/data/project/<tool>/state/last_event_id.txt"
processed_revids_file = "/data/project/<tool>/state/processed_revids.json"
nightly_sweep_progress_file = "/data/project/<tool>/state/nightly_sweep_progress.json"
runtime_status_file = "/data/project/<tool>/state/runtime_status.json"
pid_file = "/data/project/<tool>/state/daemon.pid"
```

This shared directory is how the daemon and one-off operator jobs communicate.

Create credentials as Toolforge environment variables. Enter values interactively; never place a
password in TOML, Git, `.env`, shell history, or a job command:

```bash
toolforge envvars create WIKI_BOT_USERNAME
toolforge envvars create WIKI_BOT_PASSWORD
toolforge envvars list
```

The names must match `[auth]` in the TOML. Confirm current options with `toolforge envvars create
--help` if the CLI version differs. Test configuration and authentication in a one-off job first:

```bash
toolforge jobs run suppressor-auth-check \
  --image bookworm \
  --command "$HOME/bin/suppressor --config $HOME/config/wiki.toml check-auth" \
  --wait
```

For an end-to-end test, use a bot-owned sandbox page:

```bash
toolforge jobs run suppressor-smoke-test \
  --image bookworm \
  --command "$HOME/bin/suppressor --config $HOME/config/wiki.toml smoke-test --page User:ExampleBot/SuppressorTest" \
  --wait
```

## Run and operate

Start exactly one continuous replica. `run` remains foreground work under Kubernetes supervision:

```bash
toolforge jobs run suppressor \
  --image bookworm \
  --command "$HOME/bin/suppressor --config $HOME/config/wiki.toml run" \
  --continuous
```

Inspect it with `toolforge jobs show suppressor`, `toolforge jobs list`, and the job's
`suppressor.out` and `suppressor.err` files in the Tool Account home. The daemon also writes
`$HOME/state/runtime_status.json`. Stop it with `toolforge jobs delete suppressor`; restart its
current deployment with `toolforge jobs restart suppressor`.

`reload-cache` and `catch-up-now` write atomic requests under `$HOME/state/commands/`. The daemon
polls and acknowledges them, so they work from a bastion or separate Toolforge job even though they
cannot signal the pod directly:

```bash
$HOME/bin/suppressor --config "$HOME/config/wiki.toml" reload-cache
$HOME/bin/suppressor --config "$HOME/config/wiki.toml" catch-up-now
```

Requests are idempotent coalescing signals: repeated cache reloads are safe, and repeated manual
catch-up requests queue bounded recovery work. Wait for a runtime-status or log entry before treating
a request as completed.

To upgrade, build and upload a replacement binary, make it executable, then run
`toolforge jobs restart suppressor`. Keep the previous binary outside `bin/suppressor` until the new
job has passed `check-auth` and reports healthy. Do not run more than one continuous daemon against
the same state directory and wiki configuration.

Toolforge mounts shared storage into jobs, while pod-local PIDs and Unix signals are isolated. The
file-control protocol covers cache reload and manual catch-up; it is intentionally not a network
control service. It cannot make a failed or permission-blocked MediaWiki action succeed: monitor
runtime status and logs, then fix credentials or wiki-side rights.
