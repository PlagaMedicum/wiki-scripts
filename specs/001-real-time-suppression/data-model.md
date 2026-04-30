---
docmeta:
  status: draft
  review: feature-local
  purpose: Data model for real-time suppression recovery.
  source: speckit-plan on 2026-04-29
---

# Data Model: Real-Time Suppression Recovery


## WatchedSensitivePage

Represents a page whose eligible revisions must be protected by the suppressor.

Fields:

- `title`: Canonical page title.
- `normalized_title`: Matching key used by live events and recovery queries.
- `source_kind`: `suppression-list`, `request-page`, `redirect-derived`, or another explicit local
  source classification.
- `active`: Whether the page is currently watched.
- `last_cache_seen_at`: Time the title last appeared in the active cache snapshot.

Validation rules:

- `normalized_title` must match the same normalization logic used by recentchange parsing and
  catch-up queries.
- Only active watched pages are eligible for live hiding or automated recovery.

Relationships:

- Has many `ObservedEdit` records.
- Belongs to a cache snapshot that may be refreshed by source-page edits.

## ObservedEdit

Represents a watched-page revision observed either live or through a recovery or verification path.

Fields:

- `revid`: Revision identifier.
- `title`: Title at observation time.
- `normalized_title`: Normalized title at observation time.
- `published_at`: Wiki revision timestamp when available.
- `observed_at`: Local observation timestamp.
- `observation_kind`: `live`, `gap-recovery`, `rolling-last-24h`, `nightly-full`,
  `manual-emergency`, `coverage-report`, or `source-refresh`.
- `event_cursor`: Optional stream cursor or resume token retained for transport logic only.
- `revision_url`: Safe browser-openable revision or diff URL.
- `eligibility`: `eligible`, `policy-skipped`, `already-processed`, `not-watched`,
  `missing-metadata`, or `unknown`.
- `latest_outcome`: Current `SuppressionOutcome`.

Validation rules:

- `revid` is required for any hide or operator inspection path.
- `revision_url` must be derivable without exposing hidden content or raw comments.
- Sensitive payloads are not stored in routine operator state.

Relationships:

- Belongs to one `WatchedSensitivePage` when matched to the watched set.
- Has zero or more `SuppressionAction` attempts.

## SuppressionAction

Represents a hide attempt or confirmed no-op for an observed revision.

Fields:

- `action_id`: Local unique identifier or deterministic revision key.
- `revid`: Revision identifier.
- `title`: Page title for operator context.
- `mode`: `live`, `recovery`, `verification`, `reconciliation`, `manual`, or `benchmark`.
- `queued_at`: Time work entered the queue.
- `submitted_at`: Time the API request was sent.
- `completed_at`: Time the action reached terminal success or terminal failure.
- `attempt_count`: Number of attempts.
- `outcome`: `hidden`, `already-hidden`, `skipped`, `retrying`, `failed`, `unresolved`, or
  `blocked`.
- `reason_code`: Compact non-sensitive reason such as `duplicate`, `policy-skip`,
  `permission-denied`, `rate-limited`, `network`, or `api-terminal`.
- `error`: Optional `ApiFailureSnapshot`.

Validation rules:

- A revision is not treated as fully covered until a terminal outcome is recorded.
- Replayed events must not create conflicting duplicate actions.
- Fatal auth or permission failures must surface a blocked protection state.

State transitions:

```text
queued -> submitted -> hidden
queued -> submitted -> already-hidden
queued -> submitted -> retrying -> submitted
queued -> submitted -> failed -> unresolved
queued -> skipped
queued -> blocked
```

## RecoveryAnchor

Represents the trusted starting point for automatic or operator-initiated recovery.

Fields:

- `anchor_kind`: `last-successful-hide`, `trusted-fallback`, or `operator-specified`.
- `anchor_at`: Timestamp from which recovery coverage begins.
- `recorded_at`: Time the anchor value itself was recorded or selected.
- `source_surface`: `runtime-status`, `legacy-state`, `command-input`, or another explicit source.
- `fallback_reason`: Reason a non-primary anchor was used, such as `missing-last-successful-hide`
  or `unreadable-state`.

Validation rules:

- Automatic recovery prefers `last-successful-hide`.
- Any fallback anchor must be explicit and operator-visible when it changes the recovery start
  point.
- Recovery may not silently truncate to a newer arbitrary recent window.

Relationships:

- Used by `VerificationRun` when the run type is gap recovery or emergency catch-up.

## VerificationRun

Represents one bounded recovery or verification job and its operator-visible scope.

Fields:

- `run_kind`: `gap-recovery`, `rolling-last-24h`, `nightly-full`, `manual-emergency`,
  `coverage-report`, or `source-refresh-catchup`.
- `trigger`: `daemon-start`, `stream-gap`, `stream-stale`, `reconnect-error`, `operator`,
  `scheduler-daytime`, `scheduler-nightly`, or `source-refresh`.
- `window_start`: Start timestamp when the run has a time window.
- `window_end`: End timestamp when the run has a time window.
- `scope_label`: Human-readable summary such as `since last successful hide`, `last 24 hours`, or
  `full watched set`.
- `page_scope_count`: Number of watched pages in scope when known.
- `progress_done`: Completed pages or units.
- `progress_total`: Total pages or units when known.
- `started_at`: Time the run started.
- `completed_at`: Time the run finished or stopped.
- `backoff_until`: When throttling delays resume.
- `stopped_early_reason`: Repeated-root-cause reason such as `rate-limited`.
- `counts`: `VerificationCounts`.
- `warning_summaries`: Bounded list of `WarningSummary`.
- `unresolved_items`: Bounded list of `UnresolvedExposureItem`.

Validation rules:

- Every run must report either a concrete time window or an explicit full-scope label.
- Daytime verification always uses a rolling 24-hour window.
- Nightly full recheck is distinct from rolling verification even if both run on the same date.
- Progress and unresolved samples remain bounded for low-spec safety.

Relationships:

- Uses zero or one `RecoveryAnchor`.
- Produces zero or more `ObservedEdit` outcomes.

## RecheckFreshnessSnapshot

Represents the current trustworthiness of full watched-set checkpoint coverage.

Fields:

- `target_hours`: Expected freshness target for full watched-set coverage, normally one night.
- `total_pages`: Count of watched pages represented in the checkpoint map.
- `pages_older_than_target`: Count of watched pages whose last full check is older than the target.
- `oldest_full_check_at`: Oldest known full watched-set checkpoint timestamp.
- `oldest_full_check_title`: Safe sample title for the oldest full-check entry.
- `oldest_full_check_age_seconds`: Computed age of the oldest full-check entry.
- `last_daytime_verification_result`: Compact result of the latest daytime rolling verification.
- `last_nightly_full_recheck_result`: Compact result of the latest nightly full recheck.
- `computed_at`: Time the freshness snapshot was derived.

Validation rules:

- A stale-page count greater than zero means the operator surface must not imply recent full
  watched-set coverage.
- A failed scheduled verification result must remain visible until a later successful run
  supersedes it.
- Raw checkpoint-page count without freshness age is not sufficient operator evidence.

Relationships:

- Derived from `VerificationRun` results plus persisted watched-set checkpoint state.

## VerificationCounts

Represents the bounded counts summary for a recovery or verification run.

Fields:

- `pages_checked`
- `edits_checked`
- `hidden_count`
- `already_hidden_count`
- `skipped_count`
- `failed_count`
- `unresolved_count`

Validation rules:

- Counts must cover every checked eligible edit exactly once across the outcome buckets.

## ApiFailureSnapshot

Represents a compact non-sensitive classification of a MediaWiki or transport failure.

Fields:

- `class`: `api-json-error`, `http-status`, `non-json-response`, `decode-error`, `network`,
  `timeout`, `auth-session`, or `unknown`.
- `api_code`: MediaWiki API error code when present.
- `http_status`: HTTP status when present.
- `content_type`: Response content type when present.
- `retryable`: Whether the daemon considers the failure transient.
- `retry_after_seconds`: Retry delay from `Retry-After` or local policy when available.
- `operation`: `fetch-revisions`, `revisiondelete`, `source-refresh`, `freshness-probe`,
  `coverage-report`, or another explicit operation.
- `sample_title`: Safe sample title when useful.
- `sample_revid`: Safe sample revision ID when useful.
- `message`: Short redacted operator-facing message.
- `occurred_at`: Classification time.

Validation rules:

- Never persist response bodies, hidden text, raw comments, cookies, credentials, or tokens.
- Rate-limit failures must preserve backoff information when possible.
- The same snapshot shape must work for live, recovery, verification, and source-refresh failures.

## WarningSummary

Represents one repeated-root-cause warning aggregated across a run.

Fields:

- `class`
- `api_code`
- `http_status`
- `retryable`
- `retry_after_seconds`
- `operation`
- `count`
- `sample_titles`
- `sample_revids`
- `message`
- `stopped_early`

Validation rules:

- One repeated root cause may not expand into one durable warning entry per watched page.
- Sample lists remain bounded.

## PrimaryOperatorStatus

Represents the operator-first summary needed by the compact TUI view.

Fields:

- `protection_state`: `healthy`, `recovering`, `degraded`, `blocked`, `stale`, `reconnecting`, or
  `stopped`.
- `daemon_pid`: PID when known from the supervisor view.
- `daemon_started_at`: Time continuous daemon protection began.
- `uptime_seconds`: Current daemon uptime.
- `current_task`: Optional `OperatorTaskStatus`.
- `last_successful_hide`: Optional `ObservedEditSummary`.
- `last_observed_event`: Optional `ObservedEditSummary`.
- `latest_actionable_issue`: Optional `ActionableIssue`.
- `lag_seconds`: Compatibility whole-seconds lag value.
- `lag_millis`: Additive precise lag value for sub-second operator display.
- `lag_source`: `stream` or `api-probe`.
- `recent_offline_interval`: Optional `OfflineInterval`.
- `recheck_freshness`: Optional `RecheckFreshnessSnapshot`.
- `compatibility_notice`: Optional `CompatibilityNotice`.

Validation rules:

- The primary view must answer current operator questions before showing internal counters.
- Raw transport cursors, processed-ring sizes, and checkpoint-page counts are secondary diagnostics,
  not primary status.
- The primary view must not report healthy protection while `recheck_freshness` shows a failed
  scheduled verification or obviously stale full watched-set coverage that still needs operator
  attention.

## OperatorTaskStatus

Represents the background work currently active or most recently completed.

Fields:

- `task_kind`: `idle`, `gap-recovery`, `rolling-last-24h`, `nightly-full`, `source-refresh`,
  `manual-command`, or `backoff`.
- `label`: Plain-language description shown to the operator.
- `window_start`
- `window_end`
- `progress_done`
- `progress_total`
- `started_at`
- `expected_resume_at`

Validation rules:

- A task must carry either a window or an explicit full-scope label.
- `idle` carries no misleading progress numbers.

## ObservedEditSummary

Represents a safe summary row for a meaningful last event or last hide.

Fields:

- `title`
- `revid`
- `revision_url`
- `occurred_at`
- `outcome_label`

Validation rules:

- The summary must be directly usable by a human and safe to show in the TUI.

## ActionableIssue

Represents the single most important problem requiring operator attention now.

Fields:

- `severity`: `info`, `warning`, `error`, or `blocked`.
- `kind`: `rate-limit`, `auth`, `permission`, `stream-gap`, `compatibility`, `source-refresh`, or
  another explicit category.
- `summary`: Plain-language issue summary.
- `next_action`: Exact next operator action when one is required.
- `related_revid`
- `related_revision_url`
- `detected_at`

Validation rules:

- The issue must be compact and non-sensitive.
- If no operator action is required, the field may be omitted.

## OfflineInterval

Represents a recent known or inferred offline or stalled protection interval.

Fields:

- `started_at`
- `ended_at`
- `duration_seconds`
- `reason`

Validation rules:

- Present only when the interval is meaningful for operator trust or recovery interpretation.

## CompatibilityNotice

Represents a bounded machine-readable migration or incompatibility diagnostic.

Fields:

- `scope`: `runtime-status`, `command-report`, `launch-path`, `pid-file`, `supervisor-output`, or
  another operator-facing surface.
- `severity`: `info`, `warning`, or `migration-required`.
- `detected_at`
- `previous_value`
- `expected_value`
- `summary`
- `operator_action`
- `rollback_path`
- `blocking`

Validation rules:

- `blocking=true` or `severity=migration-required` prevents a healthy or release-ready
  interpretation until acted on.
- The notice remains compact and non-sensitive.

## OperatorCommandReport

Represents the bounded output of a one-shot operator command.

Fields:

- `command`: `emergency-catchup`, `coverage-report`, `coverage-last-24h`, `nightly-recheck-now`,
  or another explicit command.
- `generated_at`
- `report_only`
- `window_start`
- `window_end`
- `scope_label`
- `counts`: `VerificationCounts`
- `unresolved_items`
- `stopped_early_reason`
- `backoff_until`
- `next_action`
- `compatibility_notice`

Validation rules:

- One-shot command reports must not replace daemon realtime truth.
- The `Last 24 hours` preset must carry that exact label in the report surface.

## ResourceEconomySnapshot

Represents compact recent resource evidence.

Fields:

- `queue_depth_max_recent`
- `api_concurrency_max_recent`
- `state_bytes_recent`
- `coalesced_warning_count_recent`
- `latest_measurement_at`

Validation rules:

- This is a bounded recent summary, not a long-term timeseries.
- Resource tracking must remain cheap enough for continuous local use.
