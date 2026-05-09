---
docmeta:
  status: draft
  review: feature-local
  purpose: Data model for real-time suppression recovery.
  source:
  - speckit-plan on 2026-04-29
  - speckit-plan stabilization update on 2026-05-05
  - speckit-plan config-stability update on 2026-05-06
  - speckit-plan human-review queue update on 2026-05-06
  - speckit-plan server-running launch-path mismatch update on 2026-05-07
  - speckit-plan live-priority parallel execution update on 2026-05-09
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
- `lane`: `live` for recentchange-triggered work, or `background` for catch-up,
  reconciliation, verification, manual command, and report work.
- `deadline_at`: Optional live-action deadline after which the current attempt must record degraded
  protection and defer retry instead of blocking newer live work.
- `outcome`: `hidden`, `already-hidden`, `skipped`, `retrying`, `failed`, `unresolved`, or
  `blocked`.
- `reason_code`: Compact non-sensitive reason such as `duplicate`, `policy-skip`,
  `permission-denied`, `rate-limited`, `network`, or `api-terminal`.
- `error`: Optional `ApiFailureSnapshot`.

Validation rules:

- A revision is not treated as fully covered until a terminal outcome is recorded.
- Replayed events must not create conflicting duplicate actions.
- Fatal auth or permission failures must surface a blocked protection state.
- Live-lane actions must not wait behind background-lane actions.
- Runtime status, processed-revision state, and queue-depth updates for the same action should be
  persisted as a short transaction around each state transition and must not hold locks across API
  calls or retry sleeps.

State transitions:

```text
queued -> submitted -> hidden
queued -> submitted -> already-hidden
queued -> submitted -> retrying -> deferred-retry -> queued
queued -> submitted -> failed -> unresolved
queued -> skipped
queued -> blocked
```

## ExecutionLane

Represents one bounded internal work lane inside the daemon.

Fields:

- `lane_kind`: `live` or `background`.
- `queue_depth`: Current number of queued actions.
- `queue_capacity`: Bounded queue capacity.
- `in_flight`: Number of actions currently submitted or executing.
- `concurrency_limit`: Maximum in-flight actions allowed for this lane.
- `latest_saturation_at`: Last time enqueue or capacity pressure degraded protection.
- `latest_saturation_reason`: Compact reason such as `live-queue-full`,
  `background-backpressure`, or `deadline-exceeded`.
- `latency`: Recent `LatencyEvidence` snapshot for this lane.

Validation rules:

- The live lane is reserved for `ObservedEdit.observation_kind=live`.
- Background queue pressure must not prevent the live lane from accepting or rejecting live work
  independently.
- Background concurrency remains bounded by the reviewed default API cap unless a later reviewed
  config decision changes it.
- Saturation or deadline failures in the live lane must surface as degraded or unhealthy protection,
  not as a silent queue wait.

Relationships:

- Owns many `SuppressionAction` items for its lane.
- Feeds `Real-Time Health State` and `ResourceEconomySnapshot`.

## SuppressionTransaction

Represents the atomic state update around one suppression action transition.

Fields:

- `transaction_id`: Local action transition identifier.
- `action_id`: Associated `SuppressionAction`.
- `phase`: `queued`, `submitted`, `completed`, `processed-recorded`, `retry-deferred`, or
  `failed`.
- `started_at`: Transaction start time.
- `completed_at`: Transaction persistence completion time.
- `status_written`: Whether daemon-owned runtime status was persisted.
- `processed_state_written`: Whether processed-revision state was persisted when required.
- `error`: Optional compact non-sensitive persistence failure.

Validation rules:

- Transactions must be short and local: in-memory update plus atomic-file persistence only.
- Transactions must not contain MediaWiki network calls, retry sleeps, page scans, or reconciliation
  loops.
- A completion transaction that records `hidden` or `already-hidden` must update
  `last_successful_hide_at` and the processed-revision state consistently before reporting success
  to an operator surface.

Relationships:

- Belongs to one `SuppressionAction`.
- Produces status evidence consumed by `Real-Time Health State`.

## LatencyEvidence

Represents bounded timing samples used for tests and release evidence.

Fields:

- `sample_count`
- `latest_ms`
- `min_ms`
- `p50_ms`
- `p95_ms`
- `p99_ms`
- `max_ms`
- `window_label`: `recent-live-samples`, `controlled-burst`, or another explicit test/evidence
  label.
- `measured_path`: `observed-to-queue`, `queue-to-submit`, `submit-to-complete`,
  `observed-to-hidden`, `publish-to-detect`, or `publish-to-hidden`.
- `computed_at`

Validation rules:

- Runtime samples must remain bounded so latency evidence cannot grow without limit.
- Local deterministic tests should use synthetic or controlled timestamps and must not store real
  sensitive-edit identifiers.
- Deployment evidence may include publish-to-detect and publish-to-hidden, but real incident
  identifiers must stay out of tracked files.

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

## DeploymentArtifact

Represents the binary artifact that will be copied to the server for the MVP daemon run.

Fields:

- `build_command`: `make build-server` from `suppressor/`, wrapping
  `cargo zigbuild --release --target aarch64-unknown-linux-musl`.
- `target_triple`: `aarch64-unknown-linux-musl`.
- `artifact_path`: `target/aarch64-unknown-linux-musl/release/suppressor`.
- `built_at`: Local build timestamp when recorded in release evidence.
- `source_revision`: Git revision or local dirty-state note used for the build.
- `rsync_destination`: Operator-supplied server destination, not stored with credentials.
- `verification_result`: `built`, `copied`, `launched`, `failed`, or `not-verified`.

Validation rules:

- Existing `build` and `release` Makefile targets remain unchanged.
- The server build target is additive and must print the artifact path for rsync.
- Release evidence must not include server credentials, tokens, or sensitive environment values.

## DetachedDaemonLaunch

Represents one operator request to start the daemon in the background from the deployed binary.

Fields:

- `command`: `server-start`.
- `binary_path`: Path of the binary used to spawn the daemon child.
- `config_path`: Config path resolved for the daemon.
- `state_dir`: Runtime state directory created or verified before spawn.
- `pid_file`: PID file expected to be written by the daemon.
- `runtime_status_file`: Daemon-owned runtime status file used for startup verification.
- `log_path`: Non-sensitive daemon stdout/stderr log path for detached operation.
- `mode`: `live` or `dry-run`.
- `spawned_pid`: PID returned by the detached child process.
- `started_at`: Time the command spawned the daemon child.
- `verification_deadline_seconds`: Maximum startup wait before the command fails.
- `verification_result`: `running`, `already-running`, `stale-pid`, `missing-config`,
  `missing-auth`, `status-timeout`, `spawn-failed`, `pid-mismatch`,
  `launch-path-mismatch`, `runtime-status-mismatch`, `already-running-untrusted`, or `unhealthy`.
- `next_action`: Compact safe operator instruction when startup did not become trustworthy.

Validation rules:

- A successful launch requires both a live child process and daemon-owned runtime status evidence.
- The command must not overwrite a trustworthy live daemon or silently treat stale PID/status files
  as healthy.
- A live process whose PID file, launch-path PID, runtime-status writer, or detached log evidence
  cannot be tied to the same `server-start` run is `already-running-untrusted` or a mismatch result,
  not `running`.
- Secrets, cookies, tokens, hidden text, and sensitive article content must not appear in the launch
  receipt or detached log path.
- The detached child must not depend on the invoking terminal after `server-start` exits.

## ConfigReviewEvidence

Represents the human-reviewed evidence that a config-affecting change or deployment config
divergence is safe to trust.

Fields:

- `config_path`: Path to the config used by the binary.
- `surface`: `tracked-config`, `schema`, `default`, `environment-variable`, `loading-semantic`, or
  `deployment-required-section`.
- `motivation`: Concrete runtime, safety, compatibility, or operator-control reason for the change.
- `human_review`: Explicit review reference or approval note.
- `compatibility_verdict`: `unchanged`, `backward-compatible`, `migration-needed`, or `blocked`.
- `previous_config_fixture`: Safe fixture or summary of the prior config shape, without secrets.
- `migration_steps`: Exact operator steps required when compatibility is not automatic.
- `rollback_steps`: How to return to the last trusted config or launch workflow.
- `server_verification`: Target-host command or evidence proving the reviewed config path loads or
  fails safely.

Validation rules:

- Config edits, schema/default changes, env-var changes, loading changes, and new required
  deployment sections require this evidence before production trust.
- Evidence must not include credentials, tokens, cookies, `.env` values, or sensitive page content.
- A missing or incompatible config blocks `server-start` trust unless the diagnostic is explicitly
  reviewed and migration-needed rather than false healthy.

## HumanReviewQueueItem

Represents a feature-local human answer, requested comment, or maintainer update needed before the
MVP can move to the next trust gate.

Fields:

- `id`: Stable queue identifier such as `Q001` or `RQ001`.
- `status`: `pending-answer`, `answered`, `comment_requested`, `update_needed`, or `resolved`.
- `subject`: Short title of the decision or action.
- `owner`: `human`, `maintainer`, or another explicit owner.
- `needed_before`: Task or release gate blocked by the item.
- `decision_options`: Allowed answer set when the item needs a human choice.
- `selected_decision`: Chosen answer after review.
- `evidence_paths`: Feature-local docs that record the answer and follow-up evidence.
- `sensitive_data_policy`: Reminder that credentials, `.env` values, tokens, cookies, and
  sensitive page content must not be recorded.

Validation rules:

- Any config-affecting implementation proposal that needs a human choice must have a queue item
  before code or server config changes proceed.
- A queue item that blocks T040 must be resolved or explicitly kept blocked before launch evidence
  can count.
- Feature-local queue status must be visible through `python3 tools/doc_workflow.py status`; if the
  status tool cannot surface `approval_needed` rows, encode the direct approval as
  `pending-answer` until the parser is repaired.

## MvpReleaseEvidence

Represents the minimum evidence required before the active safety freeze can be considered ready to
release for production trust.

Fields:

- `tests_passed`: Result for the shortest required suppressor test gate.
- `server_artifact`: `DeploymentArtifact`.
- `config_review`: Optional `ConfigReviewEvidence`; required when config differs from the reviewed
  tracked baseline or any config-affecting change is part of the release.
- `human_review_queue`: Required `HumanReviewQueueItem` references for any unresolved config,
  compatibility, launch-path, or docs-gate approval blockers.
- `detached_launch`: Optional `DetachedDaemonLaunch` for rsync-to-server verification.
- `launch_path_verified`: Whether the actual server launch path was used.
- `live_hiding_verified`: Whether live or controlled dry-run hiding was observed through the daemon.
- `recovery_verified`: Whether recovery from the last successful hide was verified.
- `reconciliation_verified`: Whether rolling last-24h and nightly full recheck behavior were
  verified or explicitly blocked with a non-healthy status.
- `backoff_verified`: Whether rate-limit/backoff behavior stays bounded and visible.
- `non_healthy_status_verified`: Whether blocked/degraded states avoid false healthy output.

Validation rules:

- Checked implementation tasks are not enough; evidence must come from tests, build output, or
  actual launch-path verification.
- Missing evidence keeps the MVP non-release-ready.
