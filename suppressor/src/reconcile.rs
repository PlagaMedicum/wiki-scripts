use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use anyhow::{Result, bail};
use chrono::{DateTime, TimeDelta, Utc};
use futures_util::StreamExt;
use metrics::histogram;
use tokio::sync::{Mutex, oneshot};
use tracing::{debug, info, warn};

use crate::cache::{CachePersistence, enrich_redirects, fetch_redirect_target};
use crate::mw_api::classify_api_failure;
use crate::runtime::{ReconcilePassContext, ReconciliationRuntime, RevDelMode, set_shared_backoff};
use crate::state::{
    ActionableIssueSnapshot, ApiFailureSnapshot, NightlySweepProgress, PageCheckpoint,
    ResourceEconomySnapshot, WarningSummary, save_json_atomic,
};

#[derive(Copy, Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum ReconcileMode {
    CurrentDay,
    Full,
}

#[derive(Default)]
struct CoordinatorState {
    active: bool,
    pending: Option<ReconcileMode>,
}

#[derive(Default)]
pub struct ReconcileCoordinator {
    state: Mutex<CoordinatorState>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct ReconciliationPassSummary {
    pub stopped_early_reason: Option<String>,
    pub backoff_until: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct ReconciliationStopRequest {
    reason: String,
    backoff_until: Option<DateTime<Utc>>,
}

fn rolling_window_start(now: DateTime<Utc>, window_hours: u64) -> DateTime<Utc> {
    now - TimeDelta::hours(window_hours as i64)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ReconcileTitleOutcome {
    Processed,
    StoppedEarly,
}

impl ReconcileCoordinator {
    pub async fn request_run(
        self: &Arc<Self>,
        runtime: Arc<ReconciliationRuntime>,
        mode: ReconcileMode,
    ) {
        let mut guard = self.state.lock().await;
        if guard.active {
            let queued_mode = guard.pending.unwrap_or(mode).max(mode);
            guard.pending = Some(queued_mode);
            drop(guard);
            runtime
                .update_runtime_status(move |status| {
                    status.reconciliation.queued_mode = Some(queued_mode.label().to_string());
                    status.last_notice = Some(format!(
                        "queued {} reconciliation rerun",
                        queued_mode.label()
                    ));
                    status.last_notice_at = Some(Utc::now());
                })
                .await;
            info!(
                requested_mode = %mode.label(),
                queued_mode = %queued_mode.label(),
                "queued reconciliation rerun because another pass is active"
            );
            return;
        }
        guard.active = true;
        drop(guard);

        let coordinator = Arc::clone(self);
        tokio::spawn(async move {
            let mut current_mode = mode;
            loop {
                if let Err(error) = runtime.run_reconciliation_pass(current_mode).await {
                    warn!("reconciliation {:?} failed: {error:#}", current_mode);
                }
                let mut state = coordinator.state.lock().await;
                if let Some(next_mode) = state.pending.take() {
                    current_mode = next_mode;
                    drop(state);
                    continue;
                }
                state.active = false;
                break;
            }
        });
    }
}

pub(crate) async fn reconciliation_loop(
    ctx: Arc<ReconcilePassContext>,
) -> Result<ReconciliationPassSummary> {
    let listed_titles = ctx.listed_titles.clone();
    ctx.update_runtime_status(|status| {
        status.reconciliation.phase = Some("resolving redirects".to_string());
        status.reconciliation.total_titles = listed_titles.len();
        status.reconciliation.completed_titles = 0;
        status.reconciliation.phase_total = listed_titles.len();
        status.reconciliation.phase_completed = 0;
        status.reconciliation.current_title = None;
        status.reconciliation.queued_mode = None;
    })
    .await;
    if listed_titles.is_empty() {
        info!(
            mode = ?ctx.mode,
            "skipping reconciliation because no listed titles are cached"
        );
        return Ok(ReconciliationPassSummary::default());
    }
    info!(
        mode = ?ctx.mode,
        listed_titles = listed_titles.len(),
        "starting reconciliation pass"
    );

    let listed_titles_set = listed_titles.iter().cloned().collect::<BTreeSet<_>>();
    let mut progress = ctx.progress.lock().await.clone();
    progress
        .pages
        .retain(|title, _| listed_titles_set.contains(title));
    let shared_progress = Arc::new(Mutex::new(progress));
    let stop_request = Arc::new(Mutex::new(None::<ReconciliationStopRequest>));
    let mut discovered_redirects = std::collections::BTreeMap::new();
    for (index, title) in listed_titles.iter().enumerate() {
        if maybe_stop_for_live_priority(&ctx, &stop_request).await {
            break;
        }
        if current_stop_request(&stop_request).await.is_some() {
            break;
        }
        ctx.update_runtime_status({
            let title = title.clone();
            move |status| {
                status.reconciliation.current_title = Some(title);
                status.reconciliation.phase_completed = index;
            }
        })
        .await;
        if let Some(target) = fetch_redirect_target(&ctx.client, title).await? {
            discovered_redirects.insert(title.clone(), target);
        }
        ctx.update_runtime_status(move |status| {
            status.reconciliation.phase_completed = index + 1;
        })
        .await;
    }
    ctx.update_runtime_status(|status| {
        status.reconciliation.phase = Some("checking page revisions".to_string());
        status.reconciliation.phase_completed = 0;
        status.reconciliation.phase_total = status.reconciliation.total_titles;
        status.reconciliation.current_title = None;
        status.last_notice =
            Some("redirect discovery finished; checking page revisions".to_string());
        status.last_notice_at = Some(Utc::now());
    })
    .await;

    let failures = Arc::new(Mutex::new(ReconciliationFailureAggregates::new(
        ctx.warning_sample_limit,
    )));

    futures_util::stream::iter(listed_titles)
        .for_each_concurrent(ctx.page_concurrency, |title| {
            let ctx = Arc::clone(&ctx);
            let shared_progress = Arc::clone(&shared_progress);
            let failures = Arc::clone(&failures);
            let stop_request = Arc::clone(&stop_request);
            async move {
                if current_stop_request(&stop_request).await.is_some()
                    || maybe_stop_for_live_priority(&ctx, &stop_request).await
                {
                    return;
                }
                ctx.update_runtime_status({
                    let title = title.clone();
                    move |status| {
                        status.reconciliation.current_title = Some(title);
                    }
                })
                .await;
                match reconcile_title(&ctx, &shared_progress, &stop_request, &title).await {
                    Ok(ReconcileTitleOutcome::StoppedEarly) => return,
                    Ok(ReconcileTitleOutcome::Processed) => {}
                    Err(failure) => {
                        let observation = failures.lock().await.record(
                            failure.clone(),
                            ctx.stop_after_failures,
                            ctx.rate_limit_backoff_default_seconds,
                            Utc::now(),
                        );
                        warn!(
                            title = %title,
                            class = %failure.class,
                            api_code = ?failure.api_code,
                            http_status = ?failure.http_status,
                            retry_after_seconds = ?failure.retry_after_seconds,
                            "reconciliation page check failed"
                        );
                        if observation.stop_after {
                            register_stop_request(
                                &stop_request,
                                ReconciliationStopRequest {
                                    reason: observation
                                        .stopped_early_reason
                                        .clone()
                                        .unwrap_or_else(|| "retryable-failures".to_string()),
                                    backoff_until: observation.backoff_until,
                                },
                            )
                            .await;
                        }
                        record_reconciliation_failure_status(&ctx, failure, observation).await;
                    }
                }
                ctx.update_runtime_status(|status| {
                    status.reconciliation.completed_titles += 1;
                    status.reconciliation.phase_completed += 1;
                })
                .await;
            }
        })
        .await;

    let progress = shared_progress.lock().await.clone();
    *ctx.progress.lock().await = progress.clone();
    if matches!(ctx.persistence, CachePersistence::Persist) {
        save_json_atomic(&ctx.paths.nightly_sweep_progress_file, &progress)?;
    }
    info!(
        mode = ?ctx.mode,
        checkpoint_pages = progress.pages.len(),
        redirects = discovered_redirects.len(),
        "reconciliation pass page checks finished"
    );
    enrich_redirects(
        &ctx.cache,
        &ctx.paths,
        std::mem::take(&mut discovered_redirects),
        ctx.persistence,
    )
    .await?;
    let stop_request = current_stop_request(&stop_request).await;
    let warning_summaries = failures.lock().await.clone().into_summaries();
    if !warning_summaries.is_empty() {
        let failed_pages = warning_summaries
            .iter()
            .map(|summary| summary.count)
            .sum::<usize>();
        record_reconciliation_warning_summaries(&ctx, warning_summaries.clone()).await;
        if let Some(stop_request) = stop_request {
            return Ok(ReconciliationPassSummary {
                stopped_early_reason: Some(stop_request.reason),
                backoff_until: stop_request.backoff_until,
            });
        }
        let top = warning_summaries
            .first()
            .map(|summary| {
                summary
                    .api_code
                    .as_deref()
                    .unwrap_or(summary.class.as_str())
                    .to_string()
            })
            .unwrap_or_else(|| "unknown".to_string());
        bail!(
            "{} failed for {} page checks; top root cause: {}",
            ctx.mode.operator_label(),
            failed_pages,
            top
        );
    }
    if let Some(stop_request) = stop_request {
        return Ok(ReconciliationPassSummary {
            stopped_early_reason: Some(stop_request.reason),
            backoff_until: stop_request.backoff_until,
        });
    }
    Ok(ReconciliationPassSummary::default())
}

#[derive(Clone, Debug)]
struct ReconciliationFailureAggregates {
    sample_limit: usize,
    by_key: BTreeMap<String, WarningSummary>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct ReconciliationFailureObservation {
    backoff_until: Option<DateTime<Utc>>,
    stop_after: bool,
    stopped_early_reason: Option<String>,
}

impl ReconciliationFailureAggregates {
    fn new(sample_limit: usize) -> Self {
        Self {
            sample_limit,
            by_key: BTreeMap::new(),
        }
    }

    fn record(
        &mut self,
        snapshot: ApiFailureSnapshot,
        stop_after_failures: usize,
        default_backoff_seconds: u64,
        now: DateTime<Utc>,
    ) -> ReconciliationFailureObservation {
        let key = format!(
            "{}|{}|{}|{}",
            snapshot.class,
            snapshot.api_code.as_deref().unwrap_or(""),
            snapshot
                .http_status
                .map(|value| value.to_string())
                .unwrap_or_default(),
            snapshot.operation
        );
        let retry_after_seconds =
            reconciliation_retry_after_seconds(&snapshot, default_backoff_seconds);
        let entry = self.by_key.entry(key).or_insert_with(|| WarningSummary {
            class: snapshot.class.clone(),
            api_code: snapshot.api_code.clone(),
            http_status: snapshot.http_status,
            content_type: snapshot.content_type.clone(),
            retryable: snapshot.retryable,
            retry_after_seconds,
            operation: snapshot.operation.clone(),
            count: 0,
            sample_titles: Vec::new(),
            message: snapshot.message.clone(),
            stopped_early: false,
        });
        entry.count += 1;
        entry.retry_after_seconds = match (entry.retry_after_seconds, retry_after_seconds) {
            (Some(current), Some(latest)) => Some(current.max(latest)),
            (None, Some(latest)) => Some(latest),
            (current, None) => current,
        };
        if let Some(ref title) = snapshot.sample_title
            && entry.sample_titles.len() < self.sample_limit
            && !entry.sample_titles.contains(title)
        {
            entry.sample_titles.push(title.clone());
        }
        let stopped_early_reason = if entry.count >= stop_after_failures.max(1) {
            if snapshot.class == "permission" {
                Some("permission-blocked".to_string())
            } else if snapshot.class == "auth-session" {
                Some("auth-session".to_string())
            } else if snapshot.http_status == Some(429)
                || snapshot.api_code.as_deref() == Some("ratelimited")
                || snapshot.retry_after_seconds.is_some()
            {
                Some("rate-limited".to_string())
            } else if snapshot.retryable {
                Some("retryable-failures".to_string())
            } else {
                None
            }
        } else {
            None
        };
        if stopped_early_reason.is_some() {
            entry.stopped_early = true;
        }
        let backoff_seconds = if stopped_early_reason.is_some() {
            Some(
                snapshot
                    .retry_after_seconds
                    .unwrap_or(default_backoff_seconds),
            )
        } else {
            reconciliation_retry_after_seconds(&snapshot, default_backoff_seconds)
        };
        ReconciliationFailureObservation {
            backoff_until: backoff_seconds
                .map(|seconds| now + TimeDelta::seconds(seconds.min(i64::MAX as u64) as i64)),
            stop_after: stopped_early_reason.is_some(),
            stopped_early_reason,
        }
    }

    fn into_summaries(self) -> Vec<WarningSummary> {
        let mut summaries = self.by_key.into_values().collect::<Vec<_>>();
        summaries.sort_by(|left, right| {
            right
                .count
                .cmp(&left.count)
                .then_with(|| left.class.cmp(&right.class))
                .then_with(|| left.operation.cmp(&right.operation))
        });
        summaries
    }
}

fn reconciliation_retry_after_seconds(
    snapshot: &ApiFailureSnapshot,
    default_backoff_seconds: u64,
) -> Option<u64> {
    if snapshot.http_status == Some(429) || snapshot.api_code.as_deref() == Some("ratelimited") {
        Some(
            snapshot
                .retry_after_seconds
                .unwrap_or(default_backoff_seconds),
        )
    } else {
        snapshot.retry_after_seconds
    }
}

async fn record_reconciliation_failure_status(
    ctx: &Arc<ReconcilePassContext>,
    failure: ApiFailureSnapshot,
    observation: ReconciliationFailureObservation,
) {
    let source = reconciliation_issue_source(ctx.mode);
    let summary = format!(
        "{} page check failed: {}",
        ctx.mode.operator_label(),
        failure.message
    );
    let next_action = if failure.class == "permission" {
        "verify bot rights or page-level revisiondelete permissions and rerun scheduled verification".to_string()
    } else if failure.class == "auth-session" {
        "re-authenticate the daemon session and rerun scheduled verification".to_string()
    } else {
        failure
            .retry_after_seconds
            .map(|seconds| {
                format!("wait {seconds}s for backoff, then rerun scheduled verification")
            })
            .unwrap_or_else(|| {
                "inspect API/network state and rerun scheduled verification".to_string()
            })
    };
    ctx.update_runtime_status(move |status| {
        let now = Utc::now();
        status.realtime.latest_error_code = failure
            .api_code
            .clone()
            .or_else(|| Some(failure.class.clone()));
        status.realtime.latest_error = Some(failure);
        if let Some(until) = observation.backoff_until {
            set_shared_backoff(status, source, "reconciliation-rate-limit", until, now);
        }
        status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
            source: source.to_string(),
            severity: "error".to_string(),
            summary,
            next_action,
            detected_at: Some(now),
        });
    })
    .await;
}

async fn record_reconciliation_warning_summaries(
    ctx: &Arc<ReconcilePassContext>,
    warning_summaries: Vec<WarningSummary>,
) {
    let warning_count = warning_summaries
        .iter()
        .map(|warning| warning.count)
        .sum::<usize>();
    ctx.update_runtime_status(move |status| {
        let now = Utc::now();
        status.realtime.latest_recovery_warnings = warning_summaries;
        let mut resource = status
            .resource_economy
            .clone()
            .unwrap_or_else(ResourceEconomySnapshot::default);
        resource.coalesced_warning_count_recent = warning_count;
        resource.latest_measurement_at = Some(now);
        status.resource_economy = Some(resource);
    })
    .await;
}

fn reconciliation_issue_source(mode: ReconcileMode) -> &'static str {
    match mode {
        ReconcileMode::CurrentDay => "last-24h-verification",
        ReconcileMode::Full => "full-watched-set-recheck",
    }
}

async fn current_stop_request(
    stop_request: &Arc<Mutex<Option<ReconciliationStopRequest>>>,
) -> Option<ReconciliationStopRequest> {
    stop_request.lock().await.clone()
}

async fn register_stop_request(
    stop_request: &Arc<Mutex<Option<ReconciliationStopRequest>>>,
    request: ReconciliationStopRequest,
) {
    let mut guard = stop_request.lock().await;
    if guard.is_none() {
        *guard = Some(request);
    }
}

async fn maybe_stop_for_live_priority(
    ctx: &Arc<ReconcilePassContext>,
    stop_request: &Arc<Mutex<Option<ReconciliationStopRequest>>>,
) -> bool {
    if current_stop_request(stop_request).await.is_some() {
        return true;
    }

    let status = ctx.runtime_status.lock().await;
    let live_busy =
        status.realtime.live_lane.queue_depth > 0 || status.realtime.live_lane.in_flight > 0;
    let unresolved_live_issue = status
        .realtime
        .latest_actionable_issue
        .as_ref()
        .is_some_and(|issue| issue.source == "live-hide");
    let unresolved_live_outcome = status
        .realtime
        .latest_outcome
        .as_ref()
        .is_some_and(|outcome| {
            outcome.mode == RevDelMode::Live.label()
                && matches!(
                    outcome.outcome.as_str(),
                    "failed" | "retrying" | "throttled" | "unresolved" | "blocked"
                )
        });
    drop(status);

    if !(live_busy || unresolved_live_issue || unresolved_live_outcome) {
        return false;
    }

    let now = Utc::now();
    let reason = if unresolved_live_issue || unresolved_live_outcome {
        "live-hide-unresolved".to_string()
    } else {
        "yielding-to-live".to_string()
    };
    register_stop_request(
        stop_request,
        ReconciliationStopRequest {
            reason,
            backoff_until: Some(
                now + TimeDelta::seconds(
                    ctx.rate_limit_backoff_default_seconds.min(i64::MAX as u64) as i64,
                ),
            ),
        },
    )
    .await;
    true
}

async fn reconcile_title(
    ctx: &Arc<ReconcilePassContext>,
    shared_progress: &Arc<Mutex<NightlySweepProgress>>,
    stop_request: &Arc<Mutex<Option<ReconciliationStopRequest>>>,
    title: &str,
) -> std::result::Result<ReconcileTitleOutcome, ApiFailureSnapshot> {
    let Some(_page_guard) = ctx.page_locks.try_lock(title.to_string()) else {
        return Ok(ReconcileTitleOutcome::Processed);
    };
    if current_stop_request(stop_request).await.is_some()
        || maybe_stop_for_live_priority(ctx, stop_request).await
    {
        return Ok(ReconcileTitleOutcome::StoppedEarly);
    }
    let checkpoint = {
        shared_progress
            .lock()
            .await
            .pages
            .get(title)
            .cloned()
            .unwrap_or_default()
    };
    let since = reconciliation_since(
        ctx.mode,
        checkpoint.last_reconciled_at,
        &ctx.timezone,
        ctx.daytime_window_hours,
    )
    .map_err(|error| classify_api_failure(&error, "reconciliation", Some(title), None))?;
    let revisions = ctx
        .client
        .fetch_revisions(title, since)
        .await
        .map_err(|error| classify_api_failure(&error, "reconciliation", Some(title), None))?;
    let revisions_checked = revisions.len();
    metrics::counter!("nightly_sweep_pages_total").increment(1);
    metrics::counter!("nightly_sweep_revisions_checked_total").increment(revisions_checked as u64);

    let mut to_hide = Vec::new();
    let mut last_seen_timestamp = checkpoint.last_reconciled_at;
    let mut last_seen_revid = checkpoint.last_reconciled_revid;
    for revision in revisions {
        last_seen_timestamp = Some(
            last_seen_timestamp
                .map(|timestamp| timestamp.max(revision.timestamp))
                .unwrap_or(revision.timestamp),
        );
        last_seen_revid = Some(revision.revid);
        if !revision.user_hidden || !revision.comment_hidden {
            to_hide.push((revision.revid, revision.timestamp));
        }
    }

    for batch in to_hide.chunks(ctx.batch_limit) {
        if current_stop_request(stop_request).await.is_some()
            || maybe_stop_for_live_priority(ctx, stop_request).await
        {
            return Ok(ReconcileTitleOutcome::StoppedEarly);
        }
        if !batch.is_empty() {
            metrics::counter!("nightly_sweep_revisions_hidden_total").increment(batch.len() as u64);
            debug!(
                title = %title,
                batch_revids = ?batch,
                mode = ?ctx.mode,
                "queueing reconciliation revisiondelete batch"
            );
            let (completion_tx, completion_rx) = oneshot::channel();
            ctx.actions
                .dispatch_action(crate::runtime::RevDelDispatch {
                    title: title.to_string(),
                    revids: batch.iter().map(|(revid, _)| *revid).collect(),
                    event_id: None,
                    user: None,
                    comment: None,
                    mode: RevDelMode::Reconciliation,
                    observed_at: batch.iter().map(|(_, timestamp)| *timestamp).max(),
                    recovery_trigger: None,
                    completion_tx: Some(completion_tx),
                })
                .await
                .map_err(|error| {
                    classify_api_failure(
                        &error,
                        "reconciliation",
                        Some(title),
                        batch.first().map(|(revid, _)| *revid),
                    )
                })?;
            match tokio::time::timeout(std::time::Duration::from_secs(60), completion_rx).await {
                Ok(Ok(Ok(_))) => {}
                Ok(Ok(Err(reason))) => {
                    let failure = ctx
                        .runtime_status
                        .lock()
                        .await
                        .realtime
                        .latest_error
                        .clone()
                        .filter(|failure| failure.operation == "revisiondelete")
                        .unwrap_or_else(|| {
                            classify_api_failure(
                                &anyhow::anyhow!(reason),
                                "reconciliation",
                                Some(title),
                                batch.first().map(|(revid, _)| *revid),
                            )
                        });
                    return Err(failure);
                }
                Ok(Err(_)) | Err(_) => {
                    return Err(ApiFailureSnapshot {
                        class: "worker-timeout".to_string(),
                        api_code: None,
                        http_status: None,
                        content_type: None,
                        retryable: true,
                        retry_after_seconds: None,
                        operation: "reconciliation".to_string(),
                        sample_title: Some(title.to_string()),
                        sample_revid: batch.first().map(|(revid, _)| *revid),
                        message: "reconciliation worker completion timed out".to_string(),
                        occurred_at: Some(Utc::now()),
                    });
                }
            }
            debug!(
                sleep_ms = ctx.batch_sleep_ms,
                batch_size = batch.len(),
                mode = ?ctx.mode,
                "waiting before next reconciliation batch"
            );
            histogram!("reconcile_batch_sleep_ms").record(ctx.batch_sleep_ms as f64);
            tokio::time::sleep(std::time::Duration::from_millis(ctx.batch_sleep_ms)).await;
        }
    }
    debug!(
        title = %title,
        revisions_checked,
        revisions_to_hide = to_hide.len(),
        last_reconciled_revid = ?last_seen_revid,
        "reconciled listed title"
    );

    let next_checkpoint =
        next_checkpoint(ctx.mode, &checkpoint, last_seen_timestamp, last_seen_revid);
    shared_progress
        .lock()
        .await
        .pages
        .insert(title.to_string(), next_checkpoint);
    Ok(ReconcileTitleOutcome::Processed)
}

fn reconciliation_since(
    mode: ReconcileMode,
    previous: Option<DateTime<Utc>>,
    timezone: &str,
    daytime_window_hours: u64,
) -> Result<Option<DateTime<Utc>>> {
    let _ = timezone;
    match mode {
        ReconcileMode::Full => Ok(previous),
        ReconcileMode::CurrentDay => {
            Ok(Some(rolling_window_start(Utc::now(), daytime_window_hours)))
        }
    }
}

pub(crate) fn revisiondelete_batch_limit(has_high_limits: bool) -> usize {
    if has_high_limits { 500 } else { 50 }
}

fn next_checkpoint(
    mode: ReconcileMode,
    checkpoint: &PageCheckpoint,
    last_seen_timestamp: Option<DateTime<Utc>>,
    last_seen_revid: Option<u64>,
) -> PageCheckpoint {
    PageCheckpoint {
        last_full_check_at: match mode {
            ReconcileMode::Full => last_seen_timestamp
                .or(checkpoint.last_full_check_at)
                .or(Some(Utc::now())),
            ReconcileMode::CurrentDay => checkpoint.last_full_check_at,
        },
        last_reconciled_at: last_seen_timestamp.or(Some(Utc::now())),
        last_reconciled_revision_timestamp: last_seen_timestamp,
        last_reconciled_revid: last_seen_revid,
    }
}

impl ReconcileMode {
    pub fn label(self) -> &'static str {
        match self {
            ReconcileMode::CurrentDay => "last-24h",
            ReconcileMode::Full => "nightly-full",
        }
    }

    pub fn operator_label(self) -> &'static str {
        match self {
            ReconcileMode::CurrentDay => "Last 24 hours verification",
            ReconcileMode::Full => "Full watched-set recheck",
        }
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use chrono::TimeZone;
    use tempfile::tempdir;
    use wiremock::matchers::{body_string_contains, method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    use super::*;
    use crate::config::EnvConfig;
    use crate::metrics::lock_runtime_latency_metrics_for_tests;
    use crate::runtime::{
        ExecutionLaneKind, RuntimeStatusSurfaceMode, build_test_runtime_harness,
        build_test_runtime_harness_with_env, build_test_runtime_harness_with_env_and_dry_run,
    };

    #[test]
    fn batch_limit_uses_high_limit_rights() {
        assert_eq!(revisiondelete_batch_limit(true), 500);
        assert_eq!(revisiondelete_batch_limit(false), 50);
    }

    #[test]
    fn full_mode_since_keeps_previous_checkpoint() {
        let previous = Utc.with_ymd_and_hms(2026, 4, 7, 21, 0, 0).unwrap();
        let since =
            reconciliation_since(ReconcileMode::Full, Some(previous), "Europe/Warsaw", 24).unwrap();

        assert_eq!(since, Some(previous));
    }

    #[test]
    fn next_checkpoint_preserves_full_check_for_current_day_runs() {
        let previous_full = Utc.with_ymd_and_hms(2026, 4, 6, 4, 0, 0).unwrap();
        let last_seen = Utc.with_ymd_and_hms(2026, 4, 8, 8, 30, 0).unwrap();
        let checkpoint = PageCheckpoint {
            last_full_check_at: Some(previous_full),
            ..PageCheckpoint::default()
        };

        let next = next_checkpoint(
            ReconcileMode::CurrentDay,
            &checkpoint,
            Some(last_seen),
            Some(123),
        );

        assert_eq!(next.last_full_check_at, Some(previous_full));
        assert_eq!(next.last_reconciled_at, Some(last_seen));
        assert_eq!(next.last_reconciled_revision_timestamp, Some(last_seen));
        assert_eq!(next.last_reconciled_revid, Some(123));
    }

    #[test]
    fn next_checkpoint_updates_full_check_for_full_runs() {
        let last_seen = Utc.with_ymd_and_hms(2026, 4, 8, 8, 30, 0).unwrap();
        let checkpoint = PageCheckpoint::default();

        let next = next_checkpoint(ReconcileMode::Full, &checkpoint, Some(last_seen), Some(123));

        assert_eq!(next.last_full_check_at, Some(last_seen));
        assert_eq!(next.last_reconciled_at, Some(last_seen));
        assert_eq!(next.last_reconciled_revision_timestamp, Some(last_seen));
        assert_eq!(next.last_reconciled_revid, Some(123));
    }

    #[test]
    fn current_day_since_uses_rolling_last_24_hours_window() {
        let previous = Utc.with_ymd_and_hms(2026, 4, 20, 9, 0, 0).unwrap();
        let since = reconciliation_since(
            ReconcileMode::CurrentDay,
            Some(previous),
            "Europe/Warsaw",
            24,
        )
        .unwrap()
        .unwrap();
        let delta = Utc::now().signed_duration_since(since).num_hours();

        assert!((23..=24).contains(&delta));
        assert!(since > previous);
    }

    #[test]
    fn operator_labels_use_plain_language() {
        assert_eq!(
            ReconcileMode::CurrentDay.operator_label(),
            "Last 24 hours verification"
        );
        assert_eq!(
            ReconcileMode::Full.operator_label(),
            "Full watched-set recheck"
        );
    }

    #[test]
    fn reconciliation_failures_coalesce_root_causes_and_preserve_backoff() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();
        let mut failures = ReconciliationFailureAggregates::new(2);

        for title in ["A", "B", "C"] {
            let observation = failures.record(
                ApiFailureSnapshot {
                    class: "api-json-error".to_string(),
                    api_code: Some("ratelimited".to_string()),
                    http_status: Some(429),
                    retryable: true,
                    retry_after_seconds: Some(45),
                    operation: "reconciliation".to_string(),
                    sample_title: Some(title.to_string()),
                    message: "rate limited".to_string(),
                    occurred_at: Some(now),
                    ..ApiFailureSnapshot::default()
                },
                3,
                30,
                now,
            );
            assert_eq!(
                observation.backoff_until,
                Some(now + chrono::TimeDelta::seconds(45))
            );
        }

        let summaries = failures.into_summaries();

        assert_eq!(summaries.len(), 1);
        assert_eq!(summaries[0].count, 3);
        assert_eq!(summaries[0].retry_after_seconds, Some(45));
        assert_eq!(summaries[0].sample_titles, vec!["A", "B"]);
    }

    #[test]
    fn reconciliation_failures_stop_early_on_repeated_auth_session_errors() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();
        let mut failures = ReconciliationFailureAggregates::new(2);
        let mut last = ReconciliationFailureObservation::default();

        for title in ["A", "B", "C"] {
            last = failures.record(
                ApiFailureSnapshot {
                    class: "auth-session".to_string(),
                    api_code: Some("badtoken".to_string()),
                    retryable: false,
                    operation: "reconciliation".to_string(),
                    sample_title: Some(title.to_string()),
                    message: "session expired".to_string(),
                    occurred_at: Some(now),
                    ..ApiFailureSnapshot::default()
                },
                3,
                30,
                now,
            );
        }

        assert!(last.stop_after);
        assert_eq!(last.stopped_early_reason.as_deref(), Some("auth-session"));
        assert_eq!(
            last.backoff_until,
            Some(now + chrono::TimeDelta::seconds(30))
        );

        let summaries = failures.into_summaries();
        assert_eq!(summaries.len(), 1);
        assert!(summaries[0].stopped_early);
        assert_eq!(summaries[0].count, 3);
        assert_eq!(summaries[0].sample_titles, vec!["A", "B"]);
    }

    #[test]
    fn reconciliation_failures_stop_early_on_repeated_permission_errors() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();
        let mut failures = ReconciliationFailureAggregates::new(2);
        let mut last = ReconciliationFailureObservation::default();

        for title in ["A", "B", "C"] {
            last = failures.record(
                ApiFailureSnapshot {
                    class: "permission".to_string(),
                    api_code: Some("permissiondenied".to_string()),
                    retryable: false,
                    operation: "reconciliation".to_string(),
                    sample_title: Some(title.to_string()),
                    message: "permission denied".to_string(),
                    occurred_at: Some(now),
                    ..ApiFailureSnapshot::default()
                },
                3,
                30,
                now,
            );
        }

        assert!(last.stop_after);
        assert_eq!(
            last.stopped_early_reason.as_deref(),
            Some("permission-blocked")
        );
        assert_eq!(
            last.backoff_until,
            Some(now + chrono::TimeDelta::seconds(30))
        );
    }

    #[tokio::test]
    async fn current_day_page_failures_mark_verification_failed_with_coalesced_warning() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("redirects", "1"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(r#"{"query":{"pages":[{"pageid":1}]}}"#, "application/json"),
            )
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("prop", "revisions"))
            .and(query_param("rvdir", "newer"))
            .respond_with(
                ResponseTemplate::new(429)
                    .insert_header("retry-after", "45")
                    .set_body_raw(
                        r#"{"error":{"code":"ratelimited","info":"rate limited"}}"#,
                        "application/json",
                    ),
            )
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            EnvConfig {
                api_url: format!("{}/w/api.php", server.uri()),
                stream_url: "https://example.invalid/stream".to_string(),
                bot_username: "bot".to_string(),
                bot_password: "pw".to_string(),
                user_agent: "bewiki-test/1.0".to_string(),
                env_file: temp.path().join(".env"),
            },
        );

        let result = harness
            .runtime
            .run_reconciliation_pass(ReconcileMode::CurrentDay)
            .await;

        assert!(result.is_err());
        let status = harness.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "unhealthy");
        assert!(
            status
                .realtime
                .last_daytime_verification_result
                .as_deref()
                .is_some_and(|result| result.starts_with("failed:"))
        );
        assert_eq!(status.realtime.latest_recovery_warnings.len(), 1);
        let warning = &status.realtime.latest_recovery_warnings[0];
        assert_eq!(warning.count, 2);
        assert_eq!(warning.api_code.as_deref(), Some("ratelimited"));
        assert_eq!(warning.retry_after_seconds, Some(45));
        assert_eq!(warning.sample_titles.len(), 2);
        assert!(warning.sample_titles.contains(&"Foo".to_string()));
        assert!(warning.sample_titles.contains(&"Bar".to_string()));
        assert_eq!(
            status
                .realtime
                .shared_backoff
                .as_ref()
                .map(|backoff| backoff.source.as_str()),
            Some("last-24h-verification")
        );
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("last-24h-verification")
        );
        assert_eq!(
            status
                .resource_economy
                .as_ref()
                .map(|resource| resource.coalesced_warning_count_recent),
            Some(2)
        );
    }

    #[tokio::test]
    async fn reconciliation_stops_early_when_live_lane_is_busy() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        {
            let mut status = harness.runtime_status.lock().await;
            status.realtime.live_lane.queue_depth = 1;
        }

        let result = harness
            .runtime
            .run_reconciliation_pass(ReconcileMode::CurrentDay)
            .await;

        assert!(result.is_err());
        let status = harness.runtime_status.lock().await.clone();
        assert!(!status.reconciliation.active);
        assert_eq!(
            status.reconciliation.stopped_early_reason.as_deref(),
            Some("yielding-to-live")
        );
    }

    #[tokio::test]
    async fn reconciliation_stops_early_on_repeated_auth_session_failures() {
        let _metrics_guard = lock_runtime_latency_metrics_for_tests().await;
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("redirects", "1"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(r#"{"query":{"pages":[{"pageid":1}]}}"#, "application/json"),
            )
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("prop", "revisions"))
            .and(query_param("rvdir", "newer"))
            .and(query_param("titles", "Foo"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(
                    r#"{"query":{"pages":[{"pageid":1,"revisions":[{"revid":1,"timestamp":"2026-04-29T09:00:00Z"}]}]}}"#,
                    "application/json",
                ),
            )
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("prop", "revisions"))
            .and(query_param("rvdir", "newer"))
            .and(query_param("titles", "Bar"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(
                    r#"{"query":{"pages":[{"pageid":2,"revisions":[{"revid":2,"timestamp":"2026-04-29T09:00:00Z"}]}]}}"#,
                    "application/json",
                ),
            )
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("prop", "revisions"))
            .and(query_param("rvdir", "newer"))
            .and(query_param("titles", "Baz"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(
                    r#"{"query":{"pages":[{"pageid":3,"revisions":[{"revid":3,"timestamp":"2026-04-29T09:00:00Z"}]}]}}"#,
                    "application/json",
                ),
            )
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"permissiondenied","info":"synthetic denied"}}"#,
                "application/json",
            ))
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = EnvConfig {
            api_url: format!("{}/w/api.php", server.uri()),
            stream_url: "https://example.invalid/stream".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "pw".to_string(),
            user_agent: "bewiki-test/1.0".to_string(),
            env_file: temp.path().join(".env"),
        };
        let harness = build_test_runtime_harness_with_env_and_dry_run(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
            false,
        );
        {
            let mut cache = harness.runtime.cache.write().await;
            cache.snapshot.listed_titles_normalized =
                vec!["Foo".to_string(), "Bar".to_string(), "Baz".to_string()];
        }
        let worker = tokio::spawn(crate::worker::run_worker_for_lane(
            Arc::clone(&harness.runtime),
            ExecutionLaneKind::Background,
            harness.background_work_rx,
        ));

        let result = harness
            .runtime
            .run_reconciliation_pass(ReconcileMode::Full)
            .await;
        let status = harness.runtime_status.lock().await.clone();
        assert!(
            result.is_err(),
            "result={result:?} last_result={:?} issue={:?}",
            status.reconciliation.last_result,
            status.realtime.latest_actionable_issue
        );
        assert!(!status.reconciliation.active);
        assert_eq!(
            status.reconciliation.stopped_early_reason.as_deref(),
            Some("permission-blocked")
        );
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("full-watched-set-recheck")
        );

        worker.abort();
    }

    #[tokio::test]
    async fn queued_full_recheck_supersedes_active_last_24h_rerun() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let coordinator = Arc::new(ReconcileCoordinator::default());
        {
            let mut state = coordinator.state.lock().await;
            state.active = true;
            state.pending = Some(ReconcileMode::CurrentDay);
        }

        coordinator
            .request_run(Arc::clone(&harness.runtime.reconcile), ReconcileMode::Full)
            .await;

        let state = coordinator.state.lock().await;
        assert!(state.active);
        assert_eq!(state.pending, Some(ReconcileMode::Full));
        drop(state);

        let status = harness.runtime_status.lock().await.clone();
        assert_eq!(
            status.reconciliation.queued_mode.as_deref(),
            Some("nightly-full")
        );
        assert_eq!(
            status.last_notice.as_deref(),
            Some("queued nightly-full reconciliation rerun")
        );
    }

    #[tokio::test]
    async fn queued_full_recheck_is_not_downgraded_by_later_last_24h_request() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let coordinator = Arc::new(ReconcileCoordinator::default());
        {
            let mut state = coordinator.state.lock().await;
            state.active = true;
            state.pending = Some(ReconcileMode::Full);
        }

        coordinator
            .request_run(
                Arc::clone(&harness.runtime.reconcile),
                ReconcileMode::CurrentDay,
            )
            .await;

        let state = coordinator.state.lock().await;
        assert!(state.active);
        assert_eq!(state.pending, Some(ReconcileMode::Full));
        drop(state);

        let status = harness.runtime_status.lock().await.clone();
        assert_eq!(
            status.reconciliation.queued_mode.as_deref(),
            Some("nightly-full")
        );
        assert_eq!(
            status.last_notice.as_deref(),
            Some("queued nightly-full reconciliation rerun")
        );
    }

    #[tokio::test]
    async fn queued_reconciliation_does_not_overwrite_active_live_hide_task() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let coordinator = Arc::new(ReconcileCoordinator::default());
        {
            let mut state = coordinator.state.lock().await;
            state.active = true;
        }
        {
            let mut status = harness.runtime_status.lock().await;
            status.realtime.current_task = Some(crate::state::CurrentTaskSnapshot {
                task_kind: "live-hide".to_string(),
                label: "hiding watched edit Sensitive".to_string(),
                progress_done: Some(0),
                progress_total: Some(1),
                started_at: Some(chrono::Utc::now()),
                ..crate::state::CurrentTaskSnapshot::default()
            });
        }

        coordinator
            .request_run(
                Arc::clone(&harness.runtime.reconcile),
                ReconcileMode::CurrentDay,
            )
            .await;

        let status = harness.runtime_status.lock().await.clone();
        assert_eq!(
            status.reconciliation.queued_mode.as_deref(),
            Some("last-24h")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("live-hide")
        );
    }
}
