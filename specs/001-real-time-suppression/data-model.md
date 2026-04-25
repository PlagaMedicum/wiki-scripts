---
docmeta:
  status: draft
  review: feature-local
  purpose: Data model for real-time suppression recovery.
  source: speckit-plan on 2026-04-24
---

# Data Model: Real-Time Suppression Recovery


## WatchedSensitivePage

Represents a page whose eligible new revisions must be protected.

Fields:

- `title`: Canonical display title.
- `normalized_title`: Normalized title used for matching.
- `source`: Suppression-list source page or redirect-derived source.
- `active`: Whether the page is currently watched.
- `last_cache_seen_at`: Time the page was last present in the local cache.

Validation rules:

- `normalized_title` must match the same normalization rules used by live recentchange events.
- Only active watched pages are eligible for live hiding or catch-up hiding.

Relationships:

- Has many `ObservedEdit` records.
- Belongs to the current suppression-list cache snapshot.

## ObservedEdit

Represents a watched-page revision observed from the live stream or a catch-up/coverage query.

Fields:

- `revid`: Revision identifier.
- `title`: Page title at observation time.
- `normalized_title`: Normalized page title at observation time.
- `observed_at`: Local observation time.
- `published_at`: Wiki revision timestamp when available.
- `event_id`: Stream event ID when available.
- `source`: `live`, `startup-catchup`, `reconnect-catchup`, `stale-catchup`, `manual-catchup`, or `coverage`.
- `user_present`: Whether actor metadata was present without storing its value in routine status.
- `comment_present`: Whether comment metadata was present without storing its value in routine status.
- `eligibility`: `eligible`, `not-watched`, `not-revision`, `already-processed`, `policy-skipped`, or `unknown`.
- `outcome`: Current `SuppressionOutcome` for this revision.

Validation rules:

- `revid` is required for any hide attempt.
- `title` and `normalized_title` are required for watched-page decisions.
- Sensitive text, comments, credentials, and tokens are not stored in routine status or coverage reports.

Relationships:

- Belongs to one `WatchedSensitivePage` when eligible or watched.
- Has zero or more `SuppressionAction` attempts.

## SuppressionAction

Represents an attempt to hide one or more revision IDs.

Fields:

- `action_id`: Local unique identifier or deterministic revision/batch key.
- `revids`: Revision IDs included in the hide request.
- `title`: Page title for operator context.
- `mode`: `live`, `catchup`, `coverage`, `reconciliation`, or `manual`.
- `queued_at`: Time the action entered the worker queue.
- `submitted_at`: Time the hide request was submitted.
- `completed_at`: Time the action reached success or terminal failure.
- `outcome`: `hidden`, `already-hidden`, `skipped`, `retrying`, `failed`, `unresolved`, or `blocked`.
- `reason_code`: Compact non-sensitive reason such as `duplicate`, `not-watched`, `bad-token-retried`, `permission-denied`, `network`, `api-transient`, or `api-terminal`.
- `error`: Optional `ApiFailureSnapshot` for failed, retrying, unresolved, or blocked actions.
- `attempt_count`: Number of worker/API attempts.

Validation rules:

- Do not mark a revision processed until hiding succeeds or already-hidden status is confirmed.
- Transient failures remain retryable or unresolved; fatal rights/session failures move realtime health to blocked.
- Replayed events must not create conflicting duplicate actions.

State transitions:

```text
queued -> submitted -> hidden
queued -> submitted -> already-hidden
queued -> submitted -> retrying -> submitted
queued -> submitted -> failed -> unresolved
queued -> skipped
queued -> blocked
```

## ApiFailureSnapshot

Represents compact non-sensitive evidence for a failed MediaWiki API call or transport operation.

Fields:

- `class`: `api-json-error`, `http-status`, `non-json-response`, `decode-error`, `network`, `timeout`, `auth-session`, or `unknown`.
- `api_code`: MediaWiki API error code when present, such as `badtimestamp`, `badtoken`, or `permissiondenied`.
- `http_status`: HTTP status code when available.
- `content_type`: Response content type when available.
- `retryable`: Whether the daemon considers the failure transient.
- `operation`: `fetch-revisions`, `fetch-page-content`, `fetch-source-metadata`, `revisiondelete`, `login`, `csrf-token`, `userinfo`, or `freshness-probe`.
- `sample_title`: Optional page title associated with the failure.
- `sample_revid`: Optional revision ID associated with the failure.
- `message`: Short redacted message suitable for TUI display.
- `occurred_at`: Time the failure was classified.

Validation rules:

- Must not store full response bodies, hidden text, raw comments, credentials, tokens, cookies, or session material.
- Decode and non-JSON failures must preserve enough metadata to tell whether the daemon contacted MediaWiki and what kind of response came back.
- Repeated failures with the same class/code may be aggregated in summaries while retaining a small safe sample.

## SourceListRefresh

Represents an observed change to the suppression-list source or request page and the recovery work triggered by that change.

Fields:

- `trigger_title`: Page that caused the refresh, such as `Удзельнік:Wizardist/SuppressionList` or `Вікіпедыя:Запыты да схавальнікаў`.
- `trigger_revid`: Revision ID of the triggering edit when available.
- `started_at`: Local time the refresh started.
- `completed_at`: Local time the refresh completed or failed.
- `old_source_revid`: Previous cached source revision.
- `new_source_revid`: New source revision after refresh.
- `new_titles`: Newly added watched titles after diffing the old and new cache snapshots.
- `removed_titles`: Titles removed from the watched set after refresh.
- `redirects_reused`: Whether existing redirect expansion was preserved.
- `catchup_triggered`: Whether immediate bounded catch-up was started.
- `catchup_title_scope`: `new-titles`, `request-window`, or `all-watched`.
- `outcome`: `unchanged`, `refreshed`, `refresh-failed`, `catchup-started`, `catchup-failed`, or `completed`.
- `error`: Optional `ApiFailureSnapshot`.

Validation rules:

- A successful source-list refresh that adds titles must trigger immediate bounded catch-up over those titles unless an operator explicitly runs report-only mode.
- Refresh failures must be visible as unhealthy or actionable notices; they must not be silently ignored.
- Routine automated benchmarks must not edit the production source list.

## SuppressionOutcome

Represents the latest known state for an observed edit.

Values:

- `hidden`: The revision's public user/comment metadata was hidden by the daemon.
- `already-hidden`: The revision did not require action because it was already hidden.
- `skipped`: The revision is not eligible under policy.
- `retrying`: A transient failure occurred and retry remains pending.
- `failed`: An action attempt failed and no retry is currently active.
- `unresolved`: The edit may still be exposed and requires catch-up or operator review.
- `blocked`: Hiding could not continue because of rights, session, or wiki-side blocking conditions.

Validation rules:

- Accident-window reports must account for every checked eligible edit with one of these outcomes.
- `unresolved` and `blocked` outcomes must be visible to the operator.

## RealtimeHealth

Represents the daemon's live protection state.

Fields:

- `state`: `starting`, `healthy`, `catching-up`, `stale`, `reconnecting`, `unhealthy`, `blocked`, or `stopped`.
- `last_state_changed_at`: Last time the realtime state changed.
- `stale_threshold_seconds`: Configured freshness threshold for treating the live path as stale.
- `last_stream_opened_at`: Last successful stream open time.
- `last_event_observed_at`: Last recentchange event observed for the target wiki.
- `last_matching_edit_at`: Last watched-page revision event observed.
- `last_action_queued_at`: Last time a hide action was queued.
- `last_action_completed_at`: Last time a hide action completed.
- `last_successful_hide_at`: Last successful hide time.
- `last_event_id`: Last stream event ID recorded.
- `current_lag_seconds`: Current freshness lag estimate.
- `queue_depth`: Current worker queue depth.
- `last_recovery_trigger`: Why recovery or catch-up is running, such as `startup`, `reconnect-error`, `invalid-resume`, `silent-starvation`, or `operator-manual`.
- `last_recovery_started_at`: Last time bounded recovery started.
- `last_recovery_completed_at`: Last time bounded recovery completed.
- `last_reconnect_reason`: Latest reconnect or stream-failure reason suitable for operator display.
- `catchup_active`: Whether bounded catch-up is running.
- `latest_error_code`: Compact latest actionable error.
- `latest_error`: Optional `ApiFailureSnapshot` or source-list failure summary.
- `latest_notice`: Operator-facing current status.
- `last_source_refresh`: Optional `SourceListRefresh` summary.

Validation rules:

- A running daemon cannot report `healthy` while realtime observation is stale beyond the configured threshold and recovery has not completed.
- Rights/session failures set `state` to `blocked`.
- TUI rendering must expose the state and latest notice without requiring log inspection.
- Repeated API failures must be summarized by class and count so one root cause cannot flood the operator terminal.

## CoverageWindow

Represents a bounded check over a recent incident or downtime range.

Fields:

- `started_at`: Window start timestamp.
- `ended_at`: Window end timestamp.
- `requested_by`: `operator`, `startup`, `reconnect`, or `watchdog`.
- `pages_checked`: Count of watched pages checked.
- `edits_checked`: Count of candidate edits checked.
- `hidden_count`: Count hidden by this run.
- `already_hidden_count`: Count already hidden before this run.
- `skipped_count`: Count skipped by policy.
- `failed_count`: Count with terminal failure.
- `unresolved_count`: Count requiring follow-up.
- `unresolved_items`: Compact list of page title, revision ID, age, reason, and next action.

Validation rules:

- Every checked eligible edit must be counted exactly once.
- Reports must not include hidden text, full edit comments, credentials, or tokens.

## BenchmarkRun

Represents controlled live verification against the approved bot test page.

Fields:

- `test_page_title`: Must be `Удзельнік:Plaga med Bot/suppressor/tests` unless explicitly overridden by the operator for a non-production environment.
- `run_id`: Unique local identifier included in edit summaries and metrics labels where safe.
- `edit_count`: Number of benchmark edits created.
- `bot_marked`: Whether every test edit was submitted with the MediaWiki bot edit marker.
- `started_at`: Run start time.
- `completed_at`: Run completion time.
- `publish_to_detect_ms`: Timing samples from page edit publication to stream/catch-up observation.
- `detect_to_queue_ms`: Timing samples from observation to worker queueing.
- `queue_to_hide_ms`: Timing samples from queueing to confirmed hide/already-hidden outcome.
- `publish_to_hidden_ms`: End-to-end timing samples.
- `p50_ms`, `p95_ms`, `p99_ms`: Summary percentiles when the sample size is large enough.
- `smoke_only`: Whether the sample is too small for SLO percentile claims.
- `unresolved_items`: Any test revisions not hidden or explicitly accounted for.

Validation rules:

- Every benchmark edit to the wiki test page must be marked as a bot edit.
- Benchmark edit content and summaries must be test-only and must not contain sensitive payloads.
- Percentile compliance claims require the documented controlled sample size; smaller production-safe checks are smoke evidence only.

## InternalServiceBoundary

Represents a microservice-like module boundary inside the single suppressor daemon/TUI deployment.

Fields:

- `name`: Boundary name such as `stream-ingestion`, `source-refresh`, `catchup`, `mw-api`, `revdel-worker`, `runtime-state`, `metrics`, or `tui-status`.
- `owner_module`: Primary Rust module or module tree that owns the boundary.
- `input_contracts`: Typed structs, enums, channels, or function inputs accepted by the boundary.
- `output_contracts`: Typed outputs, status updates, metrics, or queued actions emitted by the boundary.
- `bounded_resources`: Queue capacity, concurrency limit, sample size, state retention, or log aggregation limits that protect low-spec hosts.
- `failure_contract`: How the boundary reports errors without leaking sensitive payloads.
- `test_surface`: Unit, subsystem, or integration tests that prove the boundary behavior.
- `docs_surface`: Maintained docs where the boundary and its operational lessons are explained.

Validation rules:

- A boundary must not require a separate deployed OS process, public network endpoint, or new operator supervisor for this feature.
- Cross-boundary communication must prefer typed data over raw strings for stable contracts.
- Every boundary that performs IO, buffering, retries, or background work must document its resource bound and failure contract.

## ResourceEconomySnapshot

Represents release evidence that the daemon and TUI remain suitable for low-spec local hardware.

Fields:

- `scenario`: `idle-daemon`, `daemon-plus-tui`, `live-edit`, `startup-catchup`, `source-refresh-catchup`, `benchmark`, or `failure-storm`.
- `started_at`: Measurement start time.
- `duration_seconds`: Measurement duration.
- `rss_bytes`: Resident memory sample or summary.
- `cpu_percent`: CPU sample or summary.
- `queue_depth_max`: Maximum worker queue depth observed.
- `api_concurrency_max`: Maximum concurrent MediaWiki API work observed.
- `state_file_bytes`: Size of relevant state files after the scenario.
- `log_lines_per_minute`: Log volume summary, with repeated failures coalesced.
- `notes`: Compact non-sensitive notes about the environment and any limits.

Validation rules:

- Measurements must not include secrets or hidden content.
- Resource evidence must cover both normal operation and at least one failure/recovery scenario.
- A failing low-spec check blocks production-readiness claims until the tradeoff is documented or fixed.

## DurableLesson

Represents a lesson from the incident that must remain discoverable after feature-local planning notes are removed.

Fields:

- `lesson_id`: Stable short identifier.
- `topic`: `timestamp-format`, `source-refresh`, `api-error-classification`, `warning-coalescing`, `benchmark-safety`, `resource-economy`, or `architecture-boundary`.
- `source`: Incident, test, code audit, benchmark, or operator observation that produced the lesson.
- `durable_location`: Code test, maintained doc, or concise code comment where the lesson is preserved.
- `verification`: Test, docs gate, or manual release check that proves the lesson remains covered.

Validation rules:

- Lessons that prevent a repeat safety incident must be captured in tests when feasible.
- Operator-facing lessons belong in maintained suppressor docs, not only in feature-local artifacts.
- Code comments should be used only when the local rule is non-obvious from names and tests.
