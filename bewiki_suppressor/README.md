# bewiki_suppressor

`bewiki_suppressor` is a Rust daemon for rapid public revision deletion on be.wikipedia.org.

It watches Wikimedia EventStreams, keeps a local cache of strict newline-separated titles from `Удзельнік:Wizardist/SuppressionList`, maintains a reconciliation-derived redirect-aware watched set, immediately hides `user` and `comment` on matching new revisions, and runs checkpointed reconciliation with nightly plus randomized same-day rechecks.

## Navigation

- [Docs index](docs/README.md)
- [Operations spec](specs/operations.md)
- [Runtime boundaries](docs/runtime-boundaries.md)
- [Architecture analysis](docs/architecture-analysis.md)
- [Implementation spec](specs/implementation.md)
- [systemd unit](systemd/bewiki_suppressor.service)

## Status

- This directory now contains the current Rust implementation of the daemon.
- The current target is a Linux-first single-binary daemon with a default `bewiki_suppressor/.env` file and local state files.
- The tracked config and specs document the current defaults, but they still reflect live operator inputs rather than frozen policy.

## Next Step

- [Docs index](docs/README.md) for navigation.
- [Operations spec](specs/operations.md) for setup and day-to-day use.
- [Runtime boundaries](docs/runtime-boundaries.md) for the current architecture map and state categories.
- [Architecture analysis](docs/architecture-analysis.md) for the critical refactor notes.

## Common Commands

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
- Runtime state belongs under `state/` and is not hand-edited.
- `make tui` opens the supervisor/control client for the daemon. It launches commands, posts signals, and reads local state; it is not a second runtime implementation.
- In the TUI, `Tab` or `Left`/`Right` switches between the action list and the live output pane.
- When `Live Output` is focused, `Up`/`Down`, `PageUp`/`PageDown`, `Home`, and `End` scroll the captured logs.
- The status pane shows live reconciliation progress from `state/runtime_status.json`, including the active mode, queued reruns, current title, and completed/total page count.
- `revisiondelete` actions cannot be marked as minor edits by this daemon.
- If the service account receives the bot flag, those bot-marked log entries should be hidden in the usual RecentChanges view; without the bot flag, they remain visible there.

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
