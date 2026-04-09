# Suppressor

`suppressor` is the preferred human-facing command for the Rust daemon that performs rapid public
revision deletion. The daemon was first developed for be.wikipedia.org, so the current defaults
and examples target be.wiki, but the config is intended to be retargeted to another local wiki.

It watches Wikimedia EventStreams, keeps a local cache of strict newline-separated titles from
`Удзельнік:Wizardist/SuppressionList`, maintains a reconciliation-derived redirect-aware watched
set, immediately hides `user` and `comment` on matching new revisions, and runs checkpointed
reconciliation with nightly plus randomized same-day rechecks.

## Navigation

- [Docs index](docs/README.md)
- [Operations spec](specs/operations.md)
- [Runtime boundaries](docs/runtime-boundaries.md)
- [Architecture analysis](docs/architecture-analysis.md)
- [Implementation spec](specs/implementation.md)
- [systemd unit](systemd/suppressor.service)

## Quick Local Setup

1. Install Rust stable with `cargo`.
2. Copy `.env.example` to `.env`.
3. Open `Special:BotPasswords` on the target wiki and create a new bot password for the account
   you want to use.
4. Put the full bot login, including the `@label` suffix shown on `Special:BotPasswords`, into
   `BEWIKI_BOT_USERNAME`.
5. Put the generated bot password secret into `BEWIKI_BOT_PASSWORD`.
6. Adjust `config.toml` if you are not targeting be.wiki.
7. Run `make env-check`, `make check-auth`, and then `make dry-run`.

Example mapping:

```dotenv
BEWIKI_BOT_USERNAME=ExampleBot@revdel-watch
BEWIKI_BOT_PASSWORD=REDACTED
```

## Status

- This directory now contains the current Rust implementation of the daemon.
- The current target is a Linux-first single-binary daemon with a default `suppressor/.env` file and local state files.
- The tracked config and specs document the current defaults, but they still reflect live operator inputs rather than frozen policy.

## Next Step

- [Docs index](docs/README.md) for navigation.
- [Operations spec](specs/operations.md) for setup and day-to-day use.
- [Runtime boundaries](docs/runtime-boundaries.md) for the current architecture map and state categories.
- [Architecture analysis](docs/architecture-analysis.md) for the critical refactor notes.

## Common Commands

- `suppressor --help`
- `make help`
- `make env-check`
- `make check-auth`
- `make dry-run`
- `make run`
- `make tui`
- `make check`
- `make build`
- `make release`
- `make lint`
- `make fmt`

## Operator Notes

- Use the local `config.toml` and `.env` in this directory.
- The preferred binary name is `suppressor`, but the directory, crate, and current env vars still
  keep the older `bewiki_` prefix.
- Runtime state belongs under `state/` and is not hand-edited.
- `make tui` opens the supervisor/control client for the daemon. It launches commands, posts signals, and reads local state; it is not a second runtime implementation.
- In the TUI, `Tab` or `Left`/`Right` switches between the action list and the live output pane.
- When `Live Output` is focused, `Up`/`Down`, `PageUp`/`PageDown`, `Home`, and `End` scroll the captured logs.
- The status pane shows live reconciliation progress from `state/runtime_status.json`, including the active mode, queued reruns, current title, and completed/total page count.
- `revisiondelete` actions cannot be marked as minor edits by this daemon.
- If the service account receives the bot flag, those bot-marked log entries should be hidden in the usual RecentChanges view; without the bot flag, they remain visible there.

## Adapting To Another Local Wiki

The current defaults are be.wiki-specific, but the daemon is structured around config files and
local state instead of hard-coded server logic.

- change `[wiki]` in `config.toml` to the target wiki API URL, EventStreams URL, `wiki_code`,
  `server_name`, and user-agent
- change `[auth]` in `config.toml` if the target wiki uses different environment variable names for
  the bot password credentials
- update `.env` so `BEWIKI_BOT_USERNAME` and `BEWIKI_BOT_PASSWORD` match the target wiki's
  `Special:BotPasswords` values
- update `[suppression_list].title` to the local page that should drive the watched title list
- confirm that the target wiki exposes a compatible recent-changes stream and that the service
  account has the local rights needed for revision deletion
- keep the `state/` directory local to the machine; it is runtime data, not source control data
- if the target wiki has different rights or a different suppression workflow, revisit the
  `revdel` section and the operator runbook together

The `bewiki_` prefix remains in internal file names and environment variable names for now because
the implementation was developed here first and those names are still wired through the codebase.

## Scope

In scope:

- Rust stable implementation
- EventStreams real-time path
- suppression-list cache and refresh logic
- immediate public RevDel for `user|comment`
- nightly reconciliation/backfill sweep
- local config, local state, structured logs, and metrics

Out of scope:

- full suppression (`suppress=yes`)
- revision content hiding in the normal path
- per-page polling as the main real-time mechanism
- browser UI or database server

## Primary References

- [MediaWiki recent changes stream](https://www.mediawiki.org/wiki/API%3ARecent_changes_stream)
- [Wikitech EventStreams](https://wikitech.wikimedia.org/wiki/EventStreams)
- [MediaWiki revisiondelete API](https://www.mediawiki.org/wiki/API%3ARevisiondelete)
- [MediaWiki revisions API](https://www.mediawiki.org/wiki/API%3ARevisions)
- [MediaWiki bot passwords](https://www.mediawiki.org/wiki/Manual%3ABot_passwords)
- [bewiki group rights](https://be.wikipedia.org/wiki/%D0%90%D0%B4%D0%BC%D1%8B%D1%81%D0%BB%D0%BE%D0%B2%D0%B0%D0%B5%3AListGroupRights)

Next document: [Docs index](docs/README.md)
