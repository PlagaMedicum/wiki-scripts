---
docmeta:
  status: draft
  review: feature-local
  purpose: Operator command contract for real-time suppression recovery.
  source:
  - speckit-plan on 2026-04-29
  - speckit-plan stabilization update on 2026-05-05
  - speckit-plan config-stability update on 2026-05-06
---

# Contract: Operator Commands


## Existing Surfaces To Preserve

The current CLI and TUI already expose these operator-facing actions and should keep them available
unless an explicit compatibility notice says otherwise:

- Start daemon
- Start dry-run
- Stop daemon
- Check auth
- Print config
- Reload watched pages or cache
- Emergency catch-up
- Coverage report
- Queue nightly reconciliation or full recheck
- Refresh status
- Hide one revision by ID
- Build server binary
- Start server daemon in background

CLI command names should stay backward-compatible where practical. TUI labels may become clearer
than the raw CLI name, but that relabeling must be plain-language and documented.

## Config Stability Contract

Config files, config schema, defaults, environment variable names, config loading semantics, and
deployment-required config sections are human-reviewed operator contracts.

Rules:

- Operator commands may validate config and print safe effective-config diagnostics, but they must
  not generate credentials, edit server config, or silently add required config sections.
- A config-affecting code or docs change must have a documented motivation, explicit human review,
  compatibility or migration behavior, rollback/fallback, and server verification before
  production trust.
- `server-start` must fail safely for missing or incompatible config. The failure should be
  operator-visible and migration-needed or blocked; it must not present a healthy or detached
  daemon receipt.
- `print-effective-config` must not expose secrets and must not normalize a missing required config
  into an unreviewed production contract.

## Action Semantics

### Start daemon

Purpose: Start the long-running daemon that owns realtime protection truth.

Operator meaning:

- This starts real live or live-dry-run protection work, not just a one-shot verification action.
- The authoritative status surface after start is the daemon-owned runtime status plus the active
  supervisor output for the current deployment path.

Required output:

- Whether the daemon started successfully.
- PID or authoritative launch-path confirmation.
- Whether the daemon is live or dry-run.

### Start dry-run

Purpose: Start the daemon in observation and reporting mode without issuing live RevDel writes.

Operator meaning:

- The daemon still watches the stream, performs recovery logic, and records what it would have
  hidden.
- The primary status view must clearly show `dry-run` so successful observation is not mistaken for
  actual hidden protection.

Required output:

- Dry-run status in both the action log and the primary status surface.
- Clear operator wording that no live hiding requests are being sent.

### Reload watched pages

Purpose: Refresh the suppression-list cache and any source-adjacent request pages.

Operator meaning:

- This is not a generic “signal” with opaque behavior. The action should state what changed and
  whether a follow-up catch-up started or was deferred.

Required output:

- Old and new source revision where known.
- Counts of added and removed watched titles.
- Whether immediate catch-up started, was unnecessary, or was deferred.
- If deferred, the backoff reason and next retry point.

### Refresh status

Purpose: Reread the current daemon-owned status and command-report surfaces from local state.

Operator meaning:

- This is a local UI reread only. It does not repair protection, reload the watched set, or trigger
  recovery on its own.

Required output:

- Freshly reread status from persisted state.
- No implication that recovery or verification was triggered.

### Emergency catch-up

Purpose: Manually cover the most relevant recent exposure window without waiting for the scheduler.

Inputs:

- Optional `start`
- Optional `end`
- Optional `allow_large_window`
- Optional `dry_run`
- Optional `report_only`

Default scope:

- If the daemon has an active or recent recovery anchor derived from `last_successful_hide_at`, use
  that anchor through `now`.
- Otherwise use a bounded recent emergency window defined by config.

Required output:

- Exact covered window and its label.
- Counts for checked, hidden, already hidden, skipped, failed, and unresolved.
- Bounded unresolved item list with revision links.
- Backoff or stopped-early reason when throttled.
- Standalone command output or bounded `command_report.json`, never daemon-owned realtime truth.

Failure behavior:

- Auth or permission failures produce a blocked operator result.
- Rate-limited or repeated-root-cause failures show backoff and may stop early.
- The command must not make the primary daemon status view pretend that the daemon itself entered
  manual catch-up unless it actually did.

### Coverage report

Purpose: Produce a bounded verification report over a specified window without changing the meaning
of daemon realtime status.

Inputs:

- Required explicit timestamps for arbitrary windows unless a preset is selected
- Optional `allow_large_window`
- Optional `dry_run`
- Optional `report_only`

Required output:

- Exact start and end timestamps.
- Per-outcome counts.
- Bounded unresolved items with revision links.
- Next action when unresolved or stopped-early items remain.

Validation:

- Invalid or inverted timestamps fail before any API calls.
- Arbitrary coverage reports remain visibly distinct from the `Last 24 hours` preset.

### Coverage: Last 24 hours

Purpose: Run or review the rolling last-24h verification path without requiring timestamp input.

Inputs:

- No custom timestamps in the TUI flow.
- Optional `report_only` if the operator wants verification without mutation.

Required output:

- Exact rolling window from `now-24h` to `now`.
- Explicit operator-visible label `Last 24 hours`.
- Per-outcome counts and bounded unresolved items with revision links.
- Clear distinction from arbitrary timestamped coverage reports.

Compatibility note:

- This may map to the existing `coverage-report` CLI internally, but the operator surface must show
  the preset label explicitly.

### Run full watched-set recheck now

Purpose: Trigger the full watched-set fallback path on demand.

Operator meaning:

- This is a deliberate full verification action, not the same thing as live recovery or the rolling
  last-24h daytime verification.

Required output:

- Label `Full watched-set recheck`.
- Progress and final counts.
- Updated full-recheck freshness evidence, including whether stale-page count returned to zero.
- Any backoff or stop-early reason.

### Check auth

Purpose: Confirm login, bot status, and required rights.

Required output:

- Authenticated username.
- Bot-flag status.
- Required rights summary.

### Print config

Purpose: Show the effective runtime configuration the binary is actually using.

Required output:

- Effective config path and resolved important runtime settings.
- Clear indication of live versus dry-run defaults.
- Whether the config loaded from the reviewed deployment path or failed before runtime trust.
- No credentials, tokens, cookies, or `.env` values.

### Hide one revision by ID

Purpose: Provide a direct manual escape hatch for a known revision ID.

Required output:

- Revision ID.
- Success or failure.
- Safe actionable failure summary when it did not hide.

### Build server binary

Purpose: Build the rsync-ready Linux server artifact for the current suppressor code.

Command:

```bash
cd suppressor
make build-server
```

Required behavior:

- Run `cargo zigbuild --release --target aarch64-unknown-linux-musl` by default.
- Produce `target/aarch64-unknown-linux-musl/release/suppressor`.
- Print the artifact path after a successful build so the operator can use it as the rsync source.
- Leave existing `make build` and `make release` behavior unchanged.

Compatibility:

- This is an additive Makefile target, not a replacement for local builds.
- The command must not embed server credentials, rsync destination, or deployment secrets.

### Start server daemon in background

Purpose: Let the operator rsync the binary to the server, run one command, and safely close the SSH
terminal while the daemon continues protecting edits.

Command:

```bash
./suppressor --config ./config.toml server-start
```

Optional inputs:

- `--dry-run` to start the background daemon in dry-run mode.
- `--status-timeout-seconds <n>` to override the bounded startup wait.
- `--log-file <path>` to choose the detached stdout/stderr log path.

Target server assumptions:

- The host is Linux and can execute the deployed `aarch64-unknown-linux-musl` suppressor binary, or
  the release evidence names a different explicitly built target.
- The operator can run one local shell command from the deployment directory, but the launch result
  must not depend on systemd, tmux, screen, shell backgrounding, or `nohup`.
- The configured `config.toml`, `.env` or equivalent environment secrets, state directory, PID file
  parent, runtime-status parent, cache parent, and detached log parent are readable or writable as
  required by the same user that runs the binary.
- The server can reach be.wikipedia.org and the operator account has the expected suppression
  rights for live mode; missing network, auth, or rights evidence is a blocked launch or smoke
  result, not a degraded-success result.

Required behavior:

- Resolve and validate the same config path used by `run`.
- Create required runtime directories and parent directories for PID, status, cache, and log files.
- Validate that auth inputs are available from the process environment or `.env`, but never print or
  persist their values.
- Refuse to start a duplicate daemon when the PID file points to a live process that matches the
  expected suppressor runtime.
- Treat stale PID or stale runtime-status evidence as non-healthy startup evidence unless the
  command can prove no live daemon is being replaced.
- Spawn the same binary as a detached child running `run` or `dry-run`, with stdin detached from the
  terminal, stdout/stderr redirected to the selected log path, and the child placed in a new session
  so SSH logout does not kill it.
- Wait for the child PID, PID file, and daemon-owned `runtime_status.json` to agree or fail within
  the startup timeout.
- Print a compact receipt containing mode, PID, config path, PID file, runtime status path, log
  path, and the launch path label `server-start`.

Failure behavior:

- Missing config, missing auth values, unwritable state/log paths, duplicate live daemon, spawn
  failure, startup timeout, and unhealthy runtime status all exit non-zero with a safe next action.
- The command must not leave a false healthy status, orphaned child, or unlabeled launch path when
  startup verification fails.
- The command must not require `systemd`, `tmux`, `screen`, shell backgrounding, or `nohup`.

Compatibility:

- This is additive. Existing `run`, `dry-run`, TUI-managed daemon start, and optional systemd unit
  behavior remain valid.
- `server-start` becomes authoritative only for runs it actually started and verified; it must not
  imply systemd authority or hide that the active launch path is detached-binary.

## TUI Action Presentation

- Keep the action list short and operator-focused.
- Prefer clear labels such as `Reload watched pages`, `Emergency catch-up`, `Coverage: Last 24
  hours`, and `Run full recheck now`.
- If both generic coverage and the preset are shown, the preset should be the clearer recommended
  routine verification option.
- Manual status reread must not be presented as if it repairs the daemon.
- Separate daemon log output from command log output, or label command-origin lines clearly.

## Command Report Surface

One-shot commands may emit a bounded `command_report.json` and stdout summary with fields such as:

```json
{
  "command": "coverage-last-24h",
  "generated_at": "2026-04-29T09:25:00Z",
  "report_only": true,
  "scope_label": "Last 24 hours",
  "window": {
    "start": "2026-04-28T09:25:00Z",
    "end": "2026-04-29T09:25:00Z"
  },
  "counts": {
    "checked": 9,
    "hidden": 2,
    "already_hidden": 6,
    "skipped": 0,
    "failed": 0,
    "unresolved": 1
  },
  "stopped_early_reason": null,
  "next_action": "review unresolved revision link and rerun after backoff if needed"
}
```

Rules:

- The report surface must stay bounded and machine-readable.
- Revision links should be included where safe.
- If an older command-report shape is incompatible, emit a compact compatibility notice rather than
  silently changing meaning.

## Compatibility And Migration

- Existing CLI entry points should remain backward-compatible where practical.
- If a TUI label changes for clarity, the meaning must be documented and remain easy to map back to
  the CLI command.
- If a command, report surface, or verification path changes incompatibly, the operator surface and
  release evidence must name:
  - the old assumption
  - the new authoritative surface
  - the required human approval checkpoint
  - the required operator migration steps
  - the fallback or rollback path to the last trusted workflow
- One-shot commands must never silently replace daemon realtime truth with an incompatible or
  unlabeled new surface.
