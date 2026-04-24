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
- `latest_notice`: Operator-facing current status.

Validation rules:

- A running daemon cannot report `healthy` while realtime observation is stale beyond the configured threshold and recovery has not completed.
- Rights/session failures set `state` to `blocked`.
- TUI rendering must expose the state and latest notice without requiring log inspection.

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
