# Bewiki Suppressor v1 Implementation

Navigation: [README](../README.md) | [Docs index](../docs/README.md) | [Architecture analysis](../docs/architecture-analysis.md) | [Operations spec](operations.md)

## Purpose

Build a small, low-resource Rust daemon that:

- consumes Wikimedia EventStreams `recentchange`
- filters client-side to bewiki revision events
- keeps an in-memory and on-disk cache of listed titles from `Удзельнік:Wizardist/SuppressionList`
- maintains a derived watched set with redirect targets discovered during reconciliation
- immediately calls `action=revisiondelete` for matching new revisions
- hides `user|comment` with `suppress=no`
- runs checkpointed reconciliation with a nightly sweep plus randomized current-day rechecks

## Non-Goals

- full suppression or `suppress=yes`
- hiding revision content in the normal path
- per-page polling as the real-time path
- tolerant parsing of arbitrary wiki markup in the suppression-list source page
- browser UI or external database

## Platform

- language: Rust stable
- runtime: `tokio`
- HTTP: `reqwest` with cookie store enabled
- stream transport: SSE/EventSource over HTTP
- deployment: Linux-first, single binary
- resource target: low tens of MB RSS, acceptable under 100 MB at light load

## Fixed Interfaces

### Secrets

The default operator workflow loads auth values from a dedicated local `.env` file.
The loader also accepts matching process env overrides for the same names.

Default file:

- `suppressor/.env`

Required auth variables:

- `BEWIKI_BOT_USERNAME`
- `BEWIKI_BOT_PASSWORD`

Optional runtime overrides:

- `BEWIKI_API_URL`
- `BEWIKI_STREAM_URL`
- `BEWIKI_USER_AGENT`

### Components

- auth client
- suppression-list cache manager
- EventStreams consumer
- immediate RevDel worker
- nightly sweep worker
- state manager

### CLI

- `run`
- `tui`
- `check-auth`
- `reload-cache`
- `dry-run`
- `hide-revid <id>`
- `nightly-sweep-now`
- `print-effective-config`

`tui` is the supervisor/control client, not a second daemon implementation.

## Event Flow

- stream endpoint: `https://stream.wikimedia.org/v2/stream/recentchange`
- discard canary events where `meta.domain == "canary"`
- accept bewiki only: `wiki == "bewiki"` or `server_name == "be.wikipedia.org"`
- accept revision events of type `edit` or `new`
- codify a deterministic field precedence table for accepted live event shapes
- require a usable new revision ID
- extract immediately visible user/comment data from the event when present
- process all edits, including edits from the same authenticated account
- normalize the title and check exact membership in the cached title set
- acquire an in-memory revision transaction lock before enqueue
- dedupe by revision ID before submit
- persist `Last-Event-ID` and reuse it on reconnect
- reconnect automatically after disconnect or WMF timeout
- when resume IDs fail, use a minimal `since` recovery window

Default stream behavior:

- one stream consumer
- reconnect backoff: 1s initial, 30s max
- action queue capacity: 100

## Suppression-List Cache

Source page:

- `Удзельнік:Wizardist/SuppressionList`

Persisted metadata:

- `source_title`
- `source_pageid`
- `source_lastrevid`
- `source_last_timestamp`
- `fetched_at`
- `listed_titles_normalized`
- `watched_titles_normalized`
- `redirect_map`
- `titles_hash_sha256`

Startup behavior:

- if cache exists, load it immediately as provisional state and verify source metadata asynchronously
- if cache is absent, fetch the source page before entering full monitoring

Refresh triggers:

- source page edited in the stream
- periodic metadata recheck detects newer timestamp or latest revision
- startup cache metadata missing
- manual reload command

`reload-cache` behavior:

- refresh source-page metadata and listed-title source content only
- do not recompute redirect-derived watched titles outside reconciliation

Default metadata recheck interval:

- 600 seconds

Source-page contract:

- the source page is a plain newline-separated list of page titles
- blank lines and HTML comment-only lines are tolerated
- unsupported markup is ignored with a warning instead of being parsed heuristically

Title normalization:

- trim surrounding whitespace
- convert underscores to spaces
- collapse repeated spaces
- canonicalize namespace prefix spacing and casing
- keep remaining title text exact

Redirect-aware watched set:

- listed titles remain the source-of-truth cache layer
- nightly and randomized current-day reconciliation discover redirect targets for listed titles
- persist redirect-derived watched titles into `watched_titles_normalized` and `redirect_map`
- do not require broader recursive redirect chasing in v1

## Authentication And RevDel

Authentication sequence:

1. get login token
2. `POST action=login`
3. get CSRF token via `meta=tokens`
4. verify rights via `meta=userinfo&uiprop=rights`

Startup must hard-fail unless the session has:

- `bot`
- `deleterevision`
- `deletelogentry`

Immediate hide request shape:

- `POST action=revisiondelete`
- `type=revision`
- `ids=<revid>`
- `hide=user|comment`
- `suppress=no`
- `reason=<configured reason>`
- `token=<csrf>`

Bot-marked visibility requirement:

- `action=revisiondelete` does not expose a separate `bot` request parameter
- bot-marked log visibility therefore depends on the authenticated account having the `bot` right

Default reason:

`Emergency public RevDel on sensitive-list page; hide username and comment pending oversight resolution`

Execution model:

- one immediate RevDel worker
- same-account edits are not exempt from hiding
- success marks the revision as processed
- failed permanent actions are logged as failures and must not be marked successful

## Reconciliation

Goal:

- find listed-page revisions where `userhidden` or `commenthidden` is still absent

Nightly schedule:

- daily at `02:00 Europe/Minsk`

Checkpointed model:

- persist a full-check checkpoint per listed page
- newly added listed pages always receive a full initial backfill
- already checked pages reconcile incrementally from their stored checkpoint
- run one additional randomized current-day recheck loop every 1 to 6 hours
- reconciliation may enrich the derived watched set with redirect targets for listed titles
- manual `nightly-sweep-now` may be requested at any time
- if a sweep is already active, queue at most one pending rerun after the current run finishes

API behavior:

- request revision metadata with `ids`, `timestamp`, `user`, and `comment`
- batch `revisiondelete` calls
- use up to 50 IDs normally
- use up to 500 IDs when high limits are available

Default load controls:

- one nightly worker
- one active sweep engine at a time
- page concurrency: 2
- batch/page sleep: 250 ms
- use in-memory page transaction locks for sweep work
- persist per-page checkpoints so interrupted sweeps resume

## Dry-Run Semantics

- `dry-run` must not call `revisiondelete`
- `dry-run` must not persist `Last-Event-ID`, processed revision IDs, or sweep checkpoints
- `dry-run` may emit logs and in-memory counters only

## State Contract

State directory contents:

- `state/last_event_id.txt`
- `state/processed_revids.json`
- `state/suppression_list_cache.json`
- `state/nightly_sweep_progress.json`
- `state/runtime_status.json`
- `state/daemon.pid`

State rules:

- all writes are atomic: temp file, flush, rename
- startup tolerates missing state files
- processed revision cache is persisted and bounded
- `nightly_sweep_progress.json` stores per-page checkpoints
- `runtime_status.json` stores operator-facing live daemon and reconciliation status
- `suppression_list_cache.json` stores the derived watched set and redirect map
- page and revision transaction locks are runtime-only and are not persisted
- default processed revision capacity is 50,000 IDs

## Retry And Failure Policy

Stream:

- reconnect automatically
- reuse saved `Last-Event-ID`
- fall back to minimal `since` recovery when resume IDs cannot be reused
- treat immediate live coverage as best-effort across short disconnects
- rely on randomized current-day reconciliation plus nightly reconciliation for missed windows after longer outages

API:

- on `badtoken`, refresh CSRF and retry once
- on session loss, re-login once and retry once
- on transient 5xx, retry with exponential backoff up to 3 times
- on permanent failure, record failure and continue
- on permission loss or unrecoverable auth failure, fail closed and stop action processing

## Observability

Logging:

- structured logs, JSON preferred
- each action log includes timestamp, page title, revision ID, event ID, RC username, action mode, result, retry count, latency, and error code when present
- secrets, login tokens, and CSRF tokens must never be logged

Metrics:

- expose a Prometheus endpoint
- track at minimum:
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

## Operational Bounds

- use the first real dry runs to establish and publish the initial supported runtime envelope
- keep per-page checkpoints as the default scaling mechanism for reconciliation
- treat newly added listed pages as mandatory full initial backfills

## Acceptance Criteria

- authenticates successfully using the dedicated suppressor `.env`
- verifies `deleterevision` and `deletelogentry` at startup
- loads suppression-list cache and compares source metadata to cached metadata
- consumes EventStreams continuously and survives reconnects
- ignores canary and non-bewiki events
- uses a deterministic revision-field precedence for accepted live event shapes
- does not skip same-account edits in the live path
- loads a strict newline-separated source list and maintains redirect-derived watched titles through reconciliation
- refreshes the cache on source-page edits and periodic metadata changes
- hides `user` and `comment` quickly for new edits on listed pages
- keeps `dry-run` non-persistent
- persists checkpointed reconciliation state and resumes correctly after restart
- runs the nightly sweep plus randomized current-day rechecks and hides listed-page revisions still lacking hidden user/comment fields
- never exposes `.env` contents or tokens in logs or output

## References

- [MediaWiki recent changes stream](https://www.mediawiki.org/wiki/API%3ARecent_changes_stream)
- [Wikitech EventStreams](https://wikitech.wikimedia.org/wiki/EventStreams)
- [MediaWiki revisiondelete API](https://www.mediawiki.org/wiki/API%3ARevisiondelete)
- [MediaWiki revisions API](https://www.mediawiki.org/wiki/API%3ARevisions)
- [MediaWiki bot passwords](https://www.mediawiki.org/wiki/Manual%3ABot_passwords)
