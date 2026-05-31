#![allow(dead_code)]

use std::collections::{HashSet, VecDeque};
use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use chrono::{TimeDelta, Utc};
use futures_util::StreamExt;
use metrics::{counter, histogram};
use reqwest_eventsource::{Event, EventSource};
use tracing::{debug, info, warn};

use crate::cache::{
    CachePersistence, CacheRefreshMode, SourceRefreshCatchupPlan, SourceRefreshFollowup,
    SourceRefreshTriggerKind, SuppressionListCache, plan_source_refresh_catchup, refresh_cache,
};
use crate::catchup::run_title_scoped_catchup;
use crate::mw_api::classify_api_failure;
use crate::recentchange::{LiveRevisionCandidate, PageChangeTrigger};
use crate::runtime::{AppRuntime, RevDelDispatch, RevDelMode};
use crate::state::{SourceListRefresh, load_text, save_text_atomic};

const LIVE_POLL_INTERVAL_SECONDS: u64 = 1;
const LIVE_POLL_OVERLAP_SECONDS: i64 = 5;
const LIVE_POLL_DEDUP_TTL_SECONDS: i64 = 60;
const LIVE_POLL_MAX_CHANGES: usize = 500;
const SOURCE_REFRESH_TIMEOUT_MIN_SECONDS: u64 = 20;
const SOURCE_REFRESH_TIMEOUT_MAX_SECONDS: u64 = 60;
const POLL_TASK_RESTART_INITIAL_SECONDS: u64 = 1;
const POLL_TASK_RESTART_MAX_SECONDS: u64 = 30;

#[derive(Default)]
struct RecentChangePollDeduper {
    revids: HashSet<u64>,
    order: VecDeque<(chrono::DateTime<Utc>, u64)>,
}

impl RecentChangePollDeduper {
    fn is_new(&mut self, revid: u64, keep_since: chrono::DateTime<Utc>) -> bool {
        self.prune(keep_since);
        !self.revids.contains(&revid)
    }

    fn remember(
        &mut self,
        revid: u64,
        observed_at: chrono::DateTime<Utc>,
        keep_since: chrono::DateTime<Utc>,
    ) {
        self.prune(keep_since);
        if self.revids.insert(revid) {
            self.order.push_back((observed_at, revid));
        }
    }

    fn prune(&mut self, keep_since: chrono::DateTime<Utc>) {
        while let Some((observed_at, revid)) = self.order.front().copied() {
            if observed_at >= keep_since {
                break;
            }
            self.order.pop_front();
            self.revids.remove(&revid);
        }
    }
}

#[derive(Debug)]
struct PollDispatchSummary {
    total_changes: usize,
    watched_matches: usize,
    source_refreshes: usize,
    request_refreshes: usize,
}

pub fn spawn_recentchanges_poll_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        let mut restart_delay = Duration::from_secs(POLL_TASK_RESTART_INITIAL_SECONDS);
        loop {
            let child_runtime = Arc::clone(&runtime);
            let handle = tokio::spawn(async move { recentchanges_poll_loop(child_runtime).await });
            let failure = match handle.await {
                Ok(Ok(())) => "recentchanges poll loop stopped unexpectedly".to_string(),
                Ok(Err(error)) => format!("recentchanges poll loop failed: {error:#}"),
                Err(error) => format!("recentchanges poll task ended: {error}"),
            };
            tracing::error!(
                restart_in_seconds = restart_delay.as_secs(),
                failure = %failure,
                "recentchanges poll supervisor restarting live detector"
            );
            runtime
                .mark_recentchanges_poll_failed(
                    crate::state::ApiFailureSnapshot {
                        class: "poll-task-restart".to_string(),
                        api_code: Some("poll-task-restart".to_string()),
                        retryable: true,
                        operation: "recentchanges-poll".to_string(),
                        message: failure.clone(),
                        occurred_at: Some(Utc::now()),
                        ..crate::state::ApiFailureSnapshot::default()
                    },
                    format!(
                        "{failure}; restarting live detector in {}s",
                        restart_delay.as_secs()
                    ),
                )
                .await;
            tokio::time::sleep(restart_delay).await;
            restart_delay = poll_restart_delay(restart_delay);
        }
    });
}

fn poll_restart_delay(current: Duration) -> Duration {
    Duration::from_secs(current.as_secs().saturating_mul(2).clamp(
        POLL_TASK_RESTART_INITIAL_SECONDS,
        POLL_TASK_RESTART_MAX_SECONDS,
    ))
}

async fn recentchanges_poll_loop(runtime: Arc<AppRuntime>) -> Result<()> {
    let mut startup_catchup_pending = true;
    let mut deduper = RecentChangePollDeduper::default();
    let mut last_successful_window_end: Option<chrono::DateTime<Utc>> = None;
    let poll_interval = Duration::from_secs(LIVE_POLL_INTERVAL_SECONDS);

    loop {
        if startup_catchup_pending {
            startup_catchup_pending = false;
            spawn_bounded_catchup_if_needed(Arc::clone(&runtime), "startup".to_string()).await;
        }

        let window_end = Utc::now();
        let window_start = recentchanges_poll_window_start(last_successful_window_end, window_end);
        let window = match runtime
            .client
            .fetch_recent_changes_in_window(window_start, window_end, LIVE_POLL_MAX_CHANGES)
            .await
        {
            Ok(window) => window,
            Err(error) => {
                runtime
                    .mark_recentchanges_poll_failed(
                        classify_api_failure(&error, "recentchanges-poll", None, None),
                        format!("recentchanges polling failed: {error}"),
                    )
                    .await;
                tokio::time::sleep(poll_interval).await;
                continue;
            }
        };

        let total_changes = window.changes.len();
        let latest_event_at = window.changes.iter().map(|change| change.timestamp).max();
        let truncated = window.truncated;
        let changes = window.changes;
        let keep_since = window_end - TimeDelta::seconds(LIVE_POLL_DEDUP_TTL_SECONDS);
        let summary = match dispatch_polled_recentchanges_window(
            &runtime,
            changes,
            &mut deduper,
            keep_since,
        )
        .await
        {
            Ok(summary) => summary,
            Err(error) => {
                warn!(
                    error = %error,
                    window_start = %window_start,
                    window_end = %window_end,
                    "recentchanges poll dispatch failed; preserving the previous poll window for retry"
                );
                tokio::time::sleep(poll_interval).await;
                continue;
            }
        };
        last_successful_window_end = Some(window_end);
        debug!(
            total_changes = summary.total_changes,
            watched_matches = summary.watched_matches,
            source_refreshes = summary.source_refreshes,
            request_refreshes = summary.request_refreshes,
            "recentchanges poll dispatched overlap window"
        );

        if truncated {
            runtime
                .mark_recentchanges_poll_failed(
                    crate::state::ApiFailureSnapshot {
                        class: "poll-window-truncated".to_string(),
                        api_code: Some("poll-window-truncated".to_string()),
                        retryable: false,
                        operation: "recentchanges-poll".to_string(),
                        message: format!(
                            "recentchanges polling hit the {}-change limit",
                            LIVE_POLL_MAX_CHANGES
                        ),
                        occurred_at: Some(Utc::now()),
                        ..crate::state::ApiFailureSnapshot::default()
                    },
                    format!(
                        "recentchanges polling hit the {}-change limit; starting bounded catch-up",
                        LIVE_POLL_MAX_CHANGES
                    ),
                )
                .await;
            spawn_bounded_catchup_if_needed(
                Arc::clone(&runtime),
                "poll-window-truncated".to_string(),
            )
            .await;
        } else {
            let success_notice = if total_changes == 0 {
                "recentchanges poll completed; no new edits in overlap window".to_string()
            } else {
                format!(
                    "recentchanges poll completed changes={} overlap={}s",
                    total_changes, LIVE_POLL_OVERLAP_SECONDS
                )
            };
            runtime
                .mark_recentchanges_poll_succeeded(latest_event_at, success_notice)
                .await;
        }

        tokio::time::sleep(poll_interval).await;
    }
}

pub fn spawn_stream_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        if let Err(error) = stream_loop(runtime).await {
            tracing::error!("stream loop failed: {error:#}");
        }
    });
}

pub async fn stream_loop(runtime: Arc<AppRuntime>) -> Result<()> {
    let mut last_event_id = if runtime.dry_run {
        None
    } else {
        load_text(&runtime.paths.last_event_id_file)?
    };
    let mut startup_catchup_pending = true;
    let mut use_since_recovery = false;
    let initial_backoff = runtime.config.retry.stream_backoff_initial_ms;
    let max_backoff = runtime
        .config
        .retry
        .stream_backoff_max_ms
        .max(initial_backoff);
    let mut backoff_ms = initial_backoff;
    loop {
        let resume_event_id = if use_since_recovery {
            None
        } else {
            last_event_id.clone()
        };
        let url = runtime.client.build_stream_url(
            resume_event_id.as_deref(),
            if use_since_recovery {
                Some(runtime.config.retry.since_recovery_seconds)
            } else {
                None
            },
        )?;
        info!(
            resume_event_id = ?resume_event_id,
            use_since_recovery,
            stream_url = %url,
            "connecting to recentchange stream"
        );
        let mut request = reqwest::Client::builder()
            .build()?
            .get(url)
            .header("Accept", "text/event-stream")
            .header("User-Agent", runtime.client.user_agent());
        if let Some(event_id) = resume_event_id.as_deref() {
            request = request.header("Last-Event-ID", event_id);
        }

        let mut stream = match EventSource::new(request) {
            Ok(stream) => stream,
            Err(error) => {
                counter!("event_reconnect_total").increment(1);
                let recovery = classify_stream_error_recovery(resume_event_id.as_deref(), &error);
                use_since_recovery = recovery.use_since_recovery;
                if let Some(trigger) = recovery.catchup_trigger {
                    runtime
                        .mark_stream_gap_detected(
                            trigger.to_string(),
                            "stream-open-failed".to_string(),
                            "real-time stream failed to open; verifying missed edits".to_string(),
                        )
                        .await;
                    spawn_bounded_catchup_if_needed(Arc::clone(&runtime), trigger.to_string())
                        .await;
                } else {
                    runtime
                        .mark_stream_reconnecting(
                            "stream-open-failed".to_string(),
                            error.to_string(),
                            "real-time stream failed to open".to_string(),
                        )
                        .await;
                }
                warn!(
                    use_since_recovery,
                    error = %error,
                    "failed to open event stream"
                );
                debug!(
                    backoff_ms,
                    use_since_recovery, "waiting before reopening recentchange stream"
                );
                histogram!("stream_reconnect_backoff_ms").record(backoff_ms as f64);
                tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
                backoff_ms = (backoff_ms.saturating_mul(2)).min(max_backoff);
                continue;
            }
        };
        let read_timeout =
            Duration::from_secs(runtime.config.realtime.stream_read_timeout_seconds.max(1));
        loop {
            let item = match tokio::time::timeout(read_timeout, stream.next()).await {
                Ok(Some(item)) => item,
                Ok(None) => {
                    counter!("event_reconnect_total").increment(1);
                    runtime
                        .mark_stream_reconnecting(
                            "stream-closed".to_string(),
                            "event stream ended".to_string(),
                            "real-time stream closed; reconnecting".to_string(),
                        )
                        .await;
                    break;
                }
                Err(_) => {
                    counter!("event_stream_starvation_total").increment(1);
                    let trigger = "silent-starvation".to_string();
                    let probe_outcome =
                        probe_recentchange_freshness(Arc::clone(&runtime), read_timeout).await;
                    if probe_outcome.requires_catchup {
                        runtime
                            .mark_stream_gap_detected(
                                trigger.clone(),
                                "stream-silent".to_string(),
                                probe_outcome.reason,
                            )
                            .await;
                        spawn_bounded_catchup_if_needed(Arc::clone(&runtime), trigger.clone())
                            .await;
                        use_since_recovery = true;
                    } else {
                        runtime
                            .mark_stream_quiet_without_gap(
                                read_timeout.as_secs(),
                                probe_outcome.reason,
                            )
                            .await;
                        use_since_recovery = false;
                    }
                    break;
                }
            };
            match item {
                Ok(Event::Open) => {
                    use_since_recovery = false;
                    backoff_ms = initial_backoff;
                    info!("recentchange stream opened");
                    runtime.mark_realtime_stream_open().await;
                    if let Some(trigger) =
                        take_startup_catchup_trigger(&mut startup_catchup_pending)
                    {
                        spawn_bounded_catchup(Arc::clone(&runtime), trigger.to_string());
                    }
                    continue;
                }
                Ok(Event::Message(message)) => {
                    use_since_recovery = false;
                    backoff_ms = initial_backoff;
                    counter!("events_received_total").increment(1);
                    let event = match crate::recentchange::RecentChangeEvent::parse(&message.data) {
                        Ok(event) => event,
                        Err(error) => {
                            warn!("failed to parse event: {error:#}");
                            continue;
                        }
                    };
                    if let Some(event_id) =
                        handle_recentchange_event(&runtime, event, Some(&message.id)).await?
                    {
                        if !runtime.dry_run && !persist_last_event_id(&runtime, &event_id).await {
                            use_since_recovery = true;
                            break;
                        }
                        last_event_id = Some(event_id);
                    }
                }
                Err(error) => {
                    counter!("event_reconnect_total").increment(1);
                    let recovery =
                        classify_stream_error_recovery(resume_event_id.as_deref(), &error);
                    use_since_recovery = recovery.use_since_recovery;
                    if let Some(trigger) = recovery.catchup_trigger {
                        runtime
                            .mark_stream_gap_detected(
                                trigger.to_string(),
                                "stream-error".to_string(),
                                "real-time stream found a gap; verifying missed edits".to_string(),
                            )
                            .await;
                        spawn_bounded_catchup_if_needed(Arc::clone(&runtime), trigger.to_string())
                            .await;
                    } else {
                        runtime
                            .mark_stream_reconnecting(
                                "stream-error".to_string(),
                                format!("{} ({})", recovery.status_trigger, error),
                                "real-time stream reconnecting after error".to_string(),
                            )
                            .await;
                    }
                    warn!(
                        use_since_recovery,
                        error = %error,
                        "event stream reconnecting after error"
                    );
                    break;
                }
            }
        }
        debug!(
            backoff_ms,
            use_since_recovery, "waiting before reconnecting to recentchange stream"
        );
        histogram!("stream_reconnect_backoff_ms").record(backoff_ms as f64);
        tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
        backoff_ms = (backoff_ms.saturating_mul(2)).min(max_backoff);
    }
}

async fn spawn_bounded_catchup_if_needed(runtime: Arc<AppRuntime>, trigger: String) {
    if !runtime.should_start_recovery(&trigger).await {
        return;
    }
    spawn_bounded_catchup(runtime, trigger);
}

async fn persist_last_event_id(runtime: &Arc<AppRuntime>, event_id: &str) -> bool {
    match save_text_atomic(&runtime.paths.last_event_id_file, event_id) {
        Ok(()) => true,
        Err(error) => {
            warn!(
                path = %runtime.paths.last_event_id_file.display(),
                error = %error,
                "failed to persist stream cursor; reopening recentchange stream"
            );
            runtime
                .record_state_persistence_failure(
                    "last_event_id".to_string(),
                    runtime.paths.last_event_id_file.display().to_string(),
                    error.to_string(),
                )
                .await;
            false
        }
    }
}

fn spawn_bounded_catchup(runtime: Arc<AppRuntime>, trigger: String) {
    tokio::spawn(async move {
        if let Err(error) = crate::catchup::run_default_catchup(&runtime, trigger.clone()).await {
            warn!(error = %error, trigger = %trigger, "bounded catch-up failed");
            runtime
                .mark_recovery_failed(
                    trigger,
                    "catchup-failed".to_string(),
                    format!("bounded catch-up failed: {error}"),
                )
                .await;
        }
    });
}

struct FreshnessProbeOutcome {
    requires_catchup: bool,
    reason: String,
}

fn recentchanges_poll_window_start(
    previous_window_end: Option<chrono::DateTime<Utc>>,
    window_end: chrono::DateTime<Utc>,
) -> chrono::DateTime<Utc> {
    let overlap = TimeDelta::seconds(LIVE_POLL_OVERLAP_SECONDS);
    previous_window_end
        .map(|previous_end| previous_end.min(window_end) - overlap)
        .unwrap_or(window_end - overlap)
}

async fn probe_recentchange_freshness(
    runtime: Arc<AppRuntime>,
    read_timeout: Duration,
) -> FreshnessProbeOutcome {
    match runtime.client.fetch_latest_recent_change().await {
        Ok(Some(probe)) => {
            let previous = runtime.last_event_observed_at().await;
            runtime
                .record_freshness_probe(
                    probe.timestamp,
                    "api-freshness-probe".to_string(),
                    format!(
                        "freshness probe saw latest target-wiki edit at {}",
                        probe.timestamp.format("%H:%M:%S UTC")
                    ),
                )
                .await;
            let requires_catchup = previous.map(|seen| probe.timestamp > seen).unwrap_or(true);
            FreshnessProbeOutcome {
                requires_catchup,
                reason: if requires_catchup {
                    format!(
                        "stream silent for {}s while newer wiki edits exist",
                        read_timeout.as_secs()
                    )
                } else {
                    format!(
                        "stream silent for {}s but no newer wiki edits were found",
                        read_timeout.as_secs()
                    )
                },
            }
        }
        Ok(None) => FreshnessProbeOutcome {
            requires_catchup: false,
            reason: format!(
                "stream silent for {}s and freshness probe returned no edits",
                read_timeout.as_secs()
            ),
        },
        Err(error) => {
            runtime
                .record_api_failure(classify_api_failure(&error, "freshness-probe", None, None))
                .await;
            FreshnessProbeOutcome {
                requires_catchup: true,
                reason: format!(
                    "stream silent for {}s and freshness probe failed: {}",
                    read_timeout.as_secs(),
                    error
                ),
            }
        }
    }
}

fn spawn_title_scope_catchup(runtime: Arc<AppRuntime>, trigger: String, titles: Vec<String>) {
    tokio::spawn(async move {
        if let Err(error) = run_title_scoped_catchup(&runtime, trigger.clone(), titles).await {
            warn!(error = %error, trigger = %trigger, "title-scoped catch-up failed");
            runtime
                .mark_recovery_failed(
                    trigger,
                    "catchup-failed".to_string(),
                    format!("title-scoped catch-up failed: {error}"),
                )
                .await;
        }
    });
}

fn spawn_title_scope_catchup_if_needed(
    runtime: Arc<AppRuntime>,
    trigger: String,
    titles: Vec<String>,
) {
    tokio::spawn(async move {
        if !runtime.should_start_recovery(&trigger).await {
            return;
        }
        if let Err(error) = run_title_scoped_catchup(&runtime, trigger.clone(), titles).await {
            warn!(error = %error, trigger = %trigger, "title-scoped catch-up failed");
            runtime
                .mark_recovery_failed(
                    trigger,
                    "catchup-failed".to_string(),
                    format!("title-scoped catch-up failed: {error}"),
                )
                .await;
        }
    });
}

fn source_refresh_catchup_trigger(trigger_kind: SourceRefreshTriggerKind) -> &'static str {
    match trigger_kind {
        SourceRefreshTriggerKind::SuppressionList => "source-list-refresh",
        SourceRefreshTriggerKind::RequestPage => "request-page-refresh",
    }
}

struct SourceRefreshActiveGuard {
    runtime: Arc<AppRuntime>,
}

impl Drop for SourceRefreshActiveGuard {
    fn drop(&mut self) {
        self.runtime.finish_source_refresh();
    }
}

struct SourceRefreshPlanInput<'a> {
    before: &'a SuppressionListCache,
    after: &'a SuppressionListCache,
    refreshed: bool,
    trigger_title: &'a str,
    trigger_revid: Option<u64>,
    catchup_plan: &'a SourceRefreshCatchupPlan,
    started_at: chrono::DateTime<Utc>,
    completed_at: chrono::DateTime<Utc>,
    deferred_until: Option<chrono::DateTime<Utc>>,
}

fn plan_source_refresh(input: SourceRefreshPlanInput<'_>) -> SourceListRefresh {
    let SourceRefreshPlanInput {
        before,
        after,
        refreshed,
        trigger_title,
        trigger_revid,
        catchup_plan,
        started_at,
        completed_at,
        deferred_until,
    } = input;
    let catchup_requested = catchup_plan.catchup_requested();
    let catchup_triggered = catchup_requested && deferred_until.is_none();
    let outcome = if deferred_until.is_some() {
        "catchup-deferred"
    } else if catchup_triggered {
        "catchup-started"
    } else if refreshed {
        "refreshed"
    } else {
        "unchanged"
    };

    SourceListRefresh {
        trigger_title: trigger_title.to_string(),
        trigger_revid,
        started_at: Some(started_at),
        completed_at: Some(completed_at),
        old_source_revid: before.source_lastrevid,
        new_source_revid: after.source_lastrevid,
        new_titles_count: catchup_plan.new_titles_count,
        removed_titles_count: catchup_plan.removed_titles_count,
        redirects_reused: catchup_plan.redirects_reused,
        catchup_triggered,
        catchup_title_scope: catchup_plan.catchup_scope_label().map(str::to_string),
        deferred_until,
        outcome: outcome.to_string(),
        error: None,
    }
}

fn spawn_source_refresh_catchup(
    runtime: Arc<AppRuntime>,
    trigger_kind: SourceRefreshTriggerKind,
    catchup_plan: SourceRefreshCatchupPlan,
) {
    let trigger = source_refresh_catchup_trigger(trigger_kind).to_string();
    match catchup_plan.followup {
        SourceRefreshFollowup::None => {}
        SourceRefreshFollowup::TitleScoped { titles, .. } => {
            spawn_title_scope_catchup_if_needed(runtime, trigger, titles);
        }
        SourceRefreshFollowup::RecentWindow { .. } => {
            tokio::spawn(async move {
                spawn_bounded_catchup_if_needed(runtime, trigger).await;
            });
        }
    }
}

struct RecentChangeDispatchContext<'a> {
    source_title_normalized: &'a str,
    request_pages: &'a [String],
    watched_set: &'a HashSet<String>,
}

enum RecentChangeDispatch {
    Ignore,
    IgnoredLiveRevision(LiveRevisionCandidate),
    SourceListRefresh(PageChangeTrigger),
    RequestPageRefresh(PageChangeTrigger),
    LiveWatchedRevision(LiveRevisionCandidate),
}

fn dispatch_recentchange_event(
    event: &crate::recentchange::RecentChangeEvent,
    sse_id: Option<&str>,
    context: &RecentChangeDispatchContext<'_>,
) -> RecentChangeDispatch {
    if let Some(trigger) = event.to_page_change_trigger() {
        if trigger.normalized_title == context.source_title_normalized {
            return RecentChangeDispatch::SourceListRefresh(trigger);
        }
        if is_request_page_trigger(&trigger.normalized_title, context.request_pages) {
            return RecentChangeDispatch::RequestPageRefresh(trigger);
        }
    }
    if !event.is_revision_event() {
        return RecentChangeDispatch::Ignore;
    }
    let Some(candidate) = event.to_candidate(sse_id) else {
        return RecentChangeDispatch::Ignore;
    };
    if context.watched_set.contains(&candidate.normalized_title) {
        RecentChangeDispatch::LiveWatchedRevision(candidate)
    } else {
        RecentChangeDispatch::IgnoredLiveRevision(candidate)
    }
}

fn dispatch_polled_recentchange_record(
    change: &crate::mw_api::RecentChangeRecord,
    context: &RecentChangeDispatchContext<'_>,
) -> RecentChangeDispatch {
    let normalized_title = crate::titles::normalize_title(&change.title);
    if normalized_title == context.source_title_normalized {
        return RecentChangeDispatch::SourceListRefresh(PageChangeTrigger {
            title: change.title.clone(),
            normalized_title,
            trigger_revid: Some(change.revid),
        });
    }
    if is_request_page_trigger(&normalized_title, context.request_pages) {
        return RecentChangeDispatch::RequestPageRefresh(PageChangeTrigger {
            title: change.title.clone(),
            normalized_title,
            trigger_revid: Some(change.revid),
        });
    }
    let candidate = LiveRevisionCandidate {
        title: change.title.clone(),
        normalized_title,
        revid: change.revid,
        old_revid: None,
        user: None,
        comment: None,
        event_id: None,
    };
    if context.watched_set.contains(&candidate.normalized_title) {
        RecentChangeDispatch::LiveWatchedRevision(candidate)
    } else {
        RecentChangeDispatch::IgnoredLiveRevision(candidate)
    }
}

async fn dispatch_polled_recentchanges_window(
    runtime: &Arc<AppRuntime>,
    mut changes: Vec<crate::mw_api::RecentChangeRecord>,
    deduper: &mut RecentChangePollDeduper,
    keep_since: chrono::DateTime<Utc>,
) -> Result<PollDispatchSummary> {
    changes.sort_by(|left, right| {
        left.timestamp
            .cmp(&right.timestamp)
            .then_with(|| left.revid.cmp(&right.revid))
    });
    let mut summary = PollDispatchSummary {
        total_changes: 0,
        watched_matches: 0,
        source_refreshes: 0,
        request_refreshes: 0,
    };
    let (source_title_normalized, watched_set) = {
        let cache = runtime.cache.read().await;
        (
            cache.source_title_normalized.clone(),
            cache.watched_set.clone(),
        )
    };
    let request_pages = runtime.config.suppression_list.request_pages.clone();
    let context = RecentChangeDispatchContext {
        source_title_normalized: &source_title_normalized,
        request_pages: &request_pages,
        watched_set: &watched_set,
    };

    for change in changes {
        if !deduper.is_new(change.revid, keep_since) {
            continue;
        }
        match dispatch_polled_recentchange_record(&change, &context) {
            RecentChangeDispatch::Ignore | RecentChangeDispatch::IgnoredLiveRevision(_) => {
                deduper.remember(change.revid, change.timestamp, keep_since);
                summary.total_changes += 1;
            }
            RecentChangeDispatch::SourceListRefresh(trigger) => {
                deduper.remember(change.revid, change.timestamp, keep_since);
                summary.total_changes += 1;
                summary.source_refreshes += 1;
                handle_source_list_change(runtime, &trigger.title, trigger.trigger_revid).await;
            }
            RecentChangeDispatch::RequestPageRefresh(trigger) => {
                deduper.remember(change.revid, change.timestamp, keep_since);
                summary.total_changes += 1;
                summary.request_refreshes += 1;
                handle_request_page_change(runtime, &trigger.title, trigger.trigger_revid).await;
            }
            RecentChangeDispatch::LiveWatchedRevision(candidate) => {
                summary.total_changes += 1;
                summary.watched_matches += 1;
                info!(
                    title = %candidate.title,
                    revid = candidate.revid,
                    "matched polled watched revision"
                );
                runtime
                    .mark_realtime_match(
                        candidate.title.clone(),
                        candidate.revid,
                        crate::mw_api::revision_url(
                            &runtime.config.wiki.server_name,
                            candidate.revid,
                        ),
                        Some(change.timestamp),
                    )
                    .await;
                handle_live_candidate(runtime, candidate, Some(change.timestamp)).await?;
                deduper.remember(change.revid, change.timestamp, keep_since);
            }
        }
    }

    Ok(summary)
}

pub async fn handle_recentchange_event(
    runtime: &Arc<AppRuntime>,
    event: crate::recentchange::RecentChangeEvent,
    sse_id: Option<&str>,
) -> Result<Option<String>> {
    if runtime.config.matching.drop_canary && event.is_canary() {
        return Ok(None);
    }
    if !event.matches_wiki(
        &runtime.config.wiki.wiki_code,
        &runtime.config.wiki.server_name,
    ) {
        return Ok(None);
    }
    counter!("events_bewiki_total").increment(1);
    let event_id = event.event_id(sse_id);
    let observed_at = event.observed_at();
    runtime
        .mark_realtime_event(event_id.clone(), observed_at)
        .await;
    let dispatch = {
        let cache = runtime.cache.read().await;
        dispatch_recentchange_event(
            &event,
            sse_id,
            &RecentChangeDispatchContext {
                source_title_normalized: &cache.source_title_normalized,
                request_pages: &runtime.config.suppression_list.request_pages,
                watched_set: &cache.watched_set,
            },
        )
    };
    match dispatch {
        RecentChangeDispatch::Ignore => {}
        RecentChangeDispatch::IgnoredLiveRevision(candidate) => {
            debug!(
                title = %candidate.title,
                normalized_title = %candidate.normalized_title,
                "ignoring revision event because title is not in watched set"
            );
        }
        RecentChangeDispatch::SourceListRefresh(trigger) => {
            handle_source_list_change(runtime, &trigger.title, trigger.trigger_revid).await;
        }
        RecentChangeDispatch::RequestPageRefresh(trigger) => {
            handle_request_page_change(runtime, &trigger.title, trigger.trigger_revid).await;
        }
        RecentChangeDispatch::LiveWatchedRevision(candidate) => {
            counter!("events_matched_total").increment(1);
            info!(
                title = %candidate.title,
                revid = candidate.revid,
                old_revid = ?candidate.old_revid,
                event_id = ?candidate.event_id,
                "matched live watched revision"
            );
            runtime
                .mark_realtime_match(
                    candidate.title.clone(),
                    candidate.revid,
                    crate::mw_api::revision_url(&runtime.config.wiki.server_name, candidate.revid),
                    observed_at,
                )
                .await;
            handle_live_candidate(runtime, candidate, observed_at).await?;
        }
    }
    Ok(event_id)
}

async fn handle_source_list_change(
    runtime: &Arc<AppRuntime>,
    title: &str,
    trigger_revid: Option<u64>,
) {
    handle_source_refresh_trigger(
        runtime,
        title,
        trigger_revid,
        SourceRefreshTriggerKind::SuppressionList,
    )
    .await;
}

async fn handle_request_page_change(
    runtime: &Arc<AppRuntime>,
    title: &str,
    trigger_revid: Option<u64>,
) {
    handle_source_refresh_trigger(
        runtime,
        title,
        trigger_revid,
        SourceRefreshTriggerKind::RequestPage,
    )
    .await;
}

async fn handle_source_refresh_trigger(
    runtime: &Arc<AppRuntime>,
    title: &str,
    trigger_revid: Option<u64>,
    trigger_kind: SourceRefreshTriggerKind,
) {
    spawn_source_refresh_trigger_with_timeout(
        runtime,
        title,
        trigger_revid,
        trigger_kind,
        source_refresh_timeout(runtime),
    )
    .await;
}

async fn spawn_source_refresh_trigger_with_timeout(
    runtime: &Arc<AppRuntime>,
    title: &str,
    trigger_revid: Option<u64>,
    trigger_kind: SourceRefreshTriggerKind,
    timeout: Duration,
) {
    if !runtime.try_begin_source_refresh() {
        runtime
            .record_notice(format!(
                "source refresh already active; coalesced trigger for {title}"
            ))
            .await;
        return;
    }
    let runtime = Arc::clone(runtime);
    let title = title.to_string();
    tokio::spawn(async move {
        let _active_guard = SourceRefreshActiveGuard {
            runtime: Arc::clone(&runtime),
        };
        let started_at = Utc::now();
        let before = runtime.cache.read().await.snapshot.clone();
        let result = tokio::time::timeout(
            timeout,
            run_source_refresh_trigger(
                &runtime,
                title.clone(),
                trigger_revid,
                trigger_kind,
                started_at,
                before.clone(),
            ),
        )
        .await;
        if result.is_err() {
            warn!(
                title = %title,
                trigger_kind = ?trigger_kind,
                timeout_seconds = timeout.as_secs(),
                "source refresh timed out"
            );
            runtime
                .record_source_refresh(SourceListRefresh {
                    trigger_title: title,
                    trigger_revid,
                    started_at: Some(started_at),
                    completed_at: Some(Utc::now()),
                    old_source_revid: before.source_lastrevid,
                    new_source_revid: before.source_lastrevid,
                    outcome: "refresh-timeout".to_string(),
                    error: Some(source_refresh_timeout_failure(
                        trigger_kind,
                        timeout,
                        trigger_revid,
                    )),
                    ..SourceListRefresh::default()
                })
                .await;
        }
    });
}

fn source_refresh_timeout(runtime: &AppRuntime) -> Duration {
    Duration::from_secs(
        runtime
            .config
            .realtime
            .stream_read_timeout_seconds
            .saturating_mul(2)
            .clamp(
                SOURCE_REFRESH_TIMEOUT_MIN_SECONDS,
                SOURCE_REFRESH_TIMEOUT_MAX_SECONDS,
            ),
    )
}

fn source_refresh_timeout_failure(
    trigger_kind: SourceRefreshTriggerKind,
    timeout: Duration,
    trigger_revid: Option<u64>,
) -> crate::state::ApiFailureSnapshot {
    crate::state::ApiFailureSnapshot {
        class: "timeout".to_string(),
        retryable: true,
        operation: "source-refresh".to_string(),
        sample_revid: trigger_revid,
        message: format!(
            "{trigger_kind:?} source refresh exceeded {}s",
            timeout.as_secs()
        ),
        occurred_at: Some(Utc::now()),
        ..crate::state::ApiFailureSnapshot::default()
    }
}

async fn run_source_refresh_trigger(
    runtime: &Arc<AppRuntime>,
    title: String,
    trigger_revid: Option<u64>,
    trigger_kind: SourceRefreshTriggerKind,
    started_at: chrono::DateTime<Utc>,
    before: SuppressionListCache,
) {
    info!(
        title = %title,
        trigger_kind = ?trigger_kind,
        "source-adjacent page changed; refreshing cache and planning follow-up"
    );
    let persistence = if runtime.dry_run {
        CachePersistence::Ephemeral
    } else {
        CachePersistence::Persist
    };
    match refresh_cache(
        &runtime.cache,
        &runtime.client,
        &runtime.config,
        &runtime.paths,
        CacheRefreshMode::Forced,
        persistence,
    )
    .await
    {
        Ok(refreshed) => {
            let after = runtime.cache.read().await.snapshot.clone();
            let catchup_plan = plan_source_refresh_catchup(
                &before,
                &after,
                trigger_kind,
                runtime.config.catchup.source_refresh_title_scope_limit,
            );
            if let SourceRefreshFollowup::TitleScoped { titles, .. } = &catchup_plan.followup
                && titles.len() > runtime.config.catchup.source_refresh_title_scope_limit
            {
                warn!(
                    added_titles = titles.len(),
                    configured_limit = runtime.config.catchup.source_refresh_title_scope_limit,
                    "source refresh added more titles than the low-spec planning threshold"
                );
            }
            let deferred_until = if catchup_plan.catchup_requested() {
                runtime.current_backoff_until().await
            } else {
                None
            };
            let refresh = plan_source_refresh(SourceRefreshPlanInput {
                before: &before,
                after: &after,
                refreshed,
                trigger_title: &title,
                trigger_revid,
                catchup_plan: &catchup_plan,
                started_at,
                completed_at: Utc::now(),
                deferred_until,
            });
            runtime.record_source_refresh(refresh.clone()).await;
            if refresh.catchup_triggered {
                spawn_source_refresh_catchup(Arc::clone(runtime), trigger_kind, catchup_plan);
            }
        }
        Err(error) => {
            let failure =
                classify_api_failure(&error, "source-refresh", Some(&title), trigger_revid);
            warn!(title = %title, error = %error, "source suppression list refresh failed");
            runtime
                .record_source_refresh(SourceListRefresh {
                    trigger_title: title.to_string(),
                    trigger_revid,
                    started_at: Some(started_at),
                    completed_at: Some(Utc::now()),
                    old_source_revid: before.source_lastrevid,
                    new_source_revid: before.source_lastrevid,
                    outcome: "refresh-failed".to_string(),
                    error: Some(failure),
                    ..SourceListRefresh::default()
                })
                .await;
        }
    }
}

async fn handle_live_candidate(
    runtime: &Arc<AppRuntime>,
    candidate: LiveRevisionCandidate,
    observed_at: Option<chrono::DateTime<Utc>>,
) -> Result<()> {
    runtime
        .dispatch_action(RevDelDispatch {
            title: candidate.title,
            revids: vec![candidate.revid],
            event_id: candidate.event_id,
            user: candidate.user,
            comment: candidate.comment,
            mode: RevDelMode::Live,
            observed_at,
            recovery_trigger: None,
            completion_tx: None,
        })
        .await
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct StreamErrorRecovery {
    use_since_recovery: bool,
    status_trigger: &'static str,
    catchup_trigger: Option<&'static str>,
}

fn take_startup_catchup_trigger(startup_catchup_pending: &mut bool) -> Option<&'static str> {
    if *startup_catchup_pending {
        *startup_catchup_pending = false;
        Some("startup")
    } else {
        None
    }
}

fn classify_stream_error_recovery(
    resume_event_id: Option<&str>,
    error: &dyn std::fmt::Display,
) -> StreamErrorRecovery {
    if should_use_since_recovery(resume_event_id, error) {
        return StreamErrorRecovery {
            use_since_recovery: true,
            status_trigger: "invalid-resume",
            catchup_trigger: Some("invalid-resume"),
        };
    }
    StreamErrorRecovery {
        use_since_recovery: false,
        status_trigger: "reconnect-error",
        catchup_trigger: None,
    }
}

pub fn should_use_since_recovery(
    resume_event_id: Option<&str>,
    error: &dyn std::fmt::Display,
) -> bool {
    if resume_event_id.is_none() {
        return false;
    }
    let rendered = error.to_string().to_ascii_lowercase();
    rendered.contains("400")
        || rendered.contains("410")
        || rendered.contains("gone")
        || rendered.contains("last-event-id")
        || rendered.contains("invalid")
}

fn is_request_page_trigger(normalized_title: &str, request_pages: &[String]) -> bool {
    request_pages
        .iter()
        .any(|title| crate::titles::normalize_title(title) == normalized_title)
}

#[cfg(test)]
mod tests {
    use std::collections::{BTreeMap, HashSet};

    use chrono::{TimeDelta, TimeZone};
    use tempfile::tempdir;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    use super::*;
    use crate::cache::{
        SourceRefreshFollowup, SourceRefreshTriggerKind, SuppressionListCache,
        plan_source_refresh_catchup,
    };
    use crate::config::EnvConfig;
    use crate::mw_api::RecentChangeRecord;
    use crate::recentchange::test_fixtures::SyntheticRecentChange;
    use crate::runtime::{
        RuntimeStatusSurfaceMode, build_test_runtime_harness, build_test_runtime_harness_with_env,
    };

    #[test]
    fn since_recovery_is_disabled_without_resume_id() {
        assert!(!should_use_since_recovery(None, &"410 Gone"));
    }

    #[test]
    fn since_recovery_is_enabled_for_resume_errors() {
        assert!(should_use_since_recovery(Some("abc"), &"410 Gone"));
        assert!(should_use_since_recovery(
            Some("abc"),
            &"invalid Last-Event-ID"
        ));
    }

    #[test]
    fn since_recovery_is_disabled_for_generic_errors() {
        assert!(!should_use_since_recovery(
            Some("abc"),
            &"temporary network timeout"
        ));
    }

    #[test]
    fn startup_catchup_runs_only_once() {
        let mut pending = true;

        assert_eq!(take_startup_catchup_trigger(&mut pending), Some("startup"));
        assert_eq!(take_startup_catchup_trigger(&mut pending), None);
    }

    #[test]
    fn recentchanges_poll_window_reuses_previous_successful_head_after_outage() {
        let previous_window_end = Utc.with_ymd_and_hms(2026, 5, 14, 18, 0, 0).unwrap();
        let resumed_at = previous_window_end + TimeDelta::seconds(30);

        let window_start = recentchanges_poll_window_start(Some(previous_window_end), resumed_at);

        assert_eq!(
            window_start,
            previous_window_end - TimeDelta::seconds(LIVE_POLL_OVERLAP_SECONDS)
        );
    }

    #[test]
    fn poll_restart_delay_doubles_to_cap() {
        assert_eq!(
            poll_restart_delay(Duration::from_secs(1)),
            Duration::from_secs(2)
        );
        assert_eq!(
            poll_restart_delay(Duration::from_secs(30)),
            Duration::from_secs(30)
        );
    }

    #[test]
    fn invalid_resume_errors_trigger_since_recovery_catchup() {
        let recovery = classify_stream_error_recovery(Some("abc"), &"410 Gone");

        assert_eq!(
            recovery,
            StreamErrorRecovery {
                use_since_recovery: true,
                status_trigger: "invalid-resume",
                catchup_trigger: Some("invalid-resume"),
            }
        );
    }

    #[test]
    fn generic_reconnect_errors_do_not_trigger_catchup() {
        let recovery = classify_stream_error_recovery(Some("abc"), &"error decoding response body");

        assert_eq!(
            recovery,
            StreamErrorRecovery {
                use_since_recovery: false,
                status_trigger: "reconnect-error",
                catchup_trigger: None,
            }
        );
    }

    fn test_env(temp: &tempfile::TempDir, api_url: String) -> EnvConfig {
        EnvConfig {
            api_url,
            stream_url: "https://example.invalid/stream".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "pw".to_string(),
            user_agent: "bewiki-test/1.0".to_string(),
            env_file: temp.path().join(".env"),
        }
    }

    fn latest_recent_change_response(timestamp: chrono::DateTime<Utc>) -> String {
        format!(
            r#"{{
              "query": {{
                "recentchanges": [
                  {{
                    "title": "Fixture Page",
                    "timestamp": "{}",
                    "revid": 9000001
                  }}
                ]
              }}
            }}"#,
            timestamp.to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
        )
    }

    #[test]
    fn configured_request_page_is_detected_after_normalization() {
        assert!(is_request_page_trigger(
            "Вікіпедыя:Запыты да схавальнікаў",
            &["Вікіпедыя:Запыты_да_схавальнікаў".to_string()]
        ));
        assert!(!is_request_page_trigger(
            "Іншая старонка",
            &["Вікіпедыя:Запыты да схавальнікаў".to_string()]
        ));
    }

    #[tokio::test]
    async fn watchdog_probe_requests_catchup_when_newer_wiki_edit_exists() {
        let server = MockServer::start().await;
        let previous = Utc::now() - TimeDelta::seconds(30);
        let newer = previous + TimeDelta::seconds(10);
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(latest_recent_change_response(newer), "application/json"),
            )
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );
        harness
            .runtime
            .mark_realtime_event(Some("evt-1".to_string()), Some(previous))
            .await;

        let outcome =
            probe_recentchange_freshness(Arc::clone(&harness.runtime), Duration::from_secs(10))
                .await;
        let status = harness.runtime_status.lock().await.clone();

        assert!(outcome.requires_catchup);
        assert!(outcome.reason.contains("newer wiki edits exist"));
        assert_eq!(
            status.realtime.last_freshness_probe_source.as_deref(),
            Some("api-freshness-probe")
        );
        assert_eq!(
            status.realtime.current_lag_source.as_deref(),
            Some("api-freshness-probe")
        );
        assert!(
            status
                .realtime
                .last_event_observed_at
                .is_some_and(|value| value > previous)
        );
    }

    #[tokio::test]
    async fn watchdog_probe_does_not_request_catchup_when_no_newer_edit_exists() {
        let server = MockServer::start().await;
        let previous = Utc::now() - TimeDelta::seconds(15);
        let older = previous - TimeDelta::seconds(5);
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(latest_recent_change_response(older), "application/json"),
            )
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );
        harness
            .runtime
            .mark_realtime_event(Some("evt-2".to_string()), Some(previous))
            .await;

        let outcome =
            probe_recentchange_freshness(Arc::clone(&harness.runtime), Duration::from_secs(10))
                .await;
        let status = harness.runtime_status.lock().await.clone();

        assert!(!outcome.requires_catchup);
        assert!(outcome.reason.contains("no newer wiki edits were found"));
        assert_eq!(status.realtime.last_event_observed_at, Some(previous));
        assert_eq!(
            status.realtime.last_freshness_probe_source.as_deref(),
            Some("api-freshness-probe")
        );
    }

    #[tokio::test]
    async fn ordinary_stream_reopen_does_not_retrigger_startup_recovery() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let observed_at = Utc::now() - TimeDelta::seconds(2);
        harness
            .runtime
            .mark_realtime_event(Some("evt-3".to_string()), Some(observed_at))
            .await;
        harness
            .runtime
            .mark_stream_reconnecting(
                "stream-error".to_string(),
                "temporary network timeout".to_string(),
                "real-time stream reconnecting after error".to_string(),
            )
            .await;

        harness.runtime.mark_realtime_stream_open().await;
        let status = harness.runtime_status.lock().await.clone();

        assert_eq!(status.realtime.state, "healthy");
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("idle")
        );
        assert_eq!(
            status.realtime.latest_notice.as_deref(),
            Some("real-time stream opened")
        );
        assert!(!status.realtime.catchup_active);
        assert_eq!(status.realtime.last_recovery_trigger, None);
        assert_eq!(status.realtime.last_reconnect_reason, None);
        assert!(status.realtime.last_offline_recovered_at.is_some());
    }

    #[tokio::test]
    async fn cursor_persistence_failure_records_state_issue_and_keeps_retry_path() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        std::fs::create_dir_all(&harness.runtime.paths.last_event_id_file).unwrap();

        let persisted = persist_last_event_id(&harness.runtime, "evt-state-failure").await;

        let status = harness.runtime_status.lock().await.clone();
        assert!(!persisted);
        assert_eq!(status.realtime.state, "unhealthy");
        assert_eq!(
            status
                .realtime
                .latest_error
                .as_ref()
                .map(|error| error.class.as_str()),
            Some("state-persistence")
        );
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("state-persistence")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("state-persistence")
        );
    }

    #[test]
    fn source_page_edit_routes_to_source_refresh_dispatch() {
        let event = SyntheticRecentChange::default()
            .with_title("Удзельнік:Wizardist/SuppressionList")
            .with_revision_ids(Some(10), Some(11))
            .parse();
        let request_pages = vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()];
        let watched = HashSet::from(["Foo".to_string()]);
        let dispatch = dispatch_recentchange_event(
            &event,
            Some("stream-11"),
            &RecentChangeDispatchContext {
                source_title_normalized: "Удзельнік:Wizardist/SuppressionList",
                request_pages: &request_pages,
                watched_set: &watched,
            },
        );

        match dispatch {
            RecentChangeDispatch::SourceListRefresh(trigger) => {
                assert_eq!(trigger.title, "Удзельнік:Wizardist/SuppressionList");
                assert_eq!(trigger.trigger_revid, Some(11));
            }
            _ => panic!("expected source refresh dispatch"),
        }
    }

    #[test]
    fn request_page_edit_routes_to_request_refresh_dispatch() {
        let event = SyntheticRecentChange::default()
            .with_title("Вікіпедыя:Запыты_да_схавальнікаў")
            .with_revision_ids(Some(10), Some(11))
            .parse();
        let request_pages = vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()];
        let watched = HashSet::from(["Foo".to_string()]);
        let dispatch = dispatch_recentchange_event(
            &event,
            Some("stream-11"),
            &RecentChangeDispatchContext {
                source_title_normalized: "Удзельнік:Wizardist/SuppressionList",
                request_pages: &request_pages,
                watched_set: &watched,
            },
        );

        match dispatch {
            RecentChangeDispatch::RequestPageRefresh(trigger) => {
                assert_eq!(trigger.normalized_title, "Вікіпедыя:Запыты да схавальнікаў");
                assert_eq!(trigger.trigger_revid, Some(11));
            }
            _ => panic!("expected request page refresh dispatch"),
        }
    }

    #[test]
    fn watched_revision_routes_to_live_dispatch() {
        let event = SyntheticRecentChange::default()
            .with_title("Foo")
            .with_revision_ids(Some(10), Some(77))
            .parse();
        let request_pages = vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()];
        let watched = HashSet::from(["Foo".to_string()]);
        let dispatch = dispatch_recentchange_event(
            &event,
            Some("stream-77"),
            &RecentChangeDispatchContext {
                source_title_normalized: "Удзельнік:Wizardist/SuppressionList",
                request_pages: &request_pages,
                watched_set: &watched,
            },
        );

        match dispatch {
            RecentChangeDispatch::LiveWatchedRevision(candidate) => {
                assert_eq!(candidate.title, "Foo");
                assert_eq!(candidate.revid, 77);
                assert_eq!(candidate.event_id.as_deref(), Some("stream-77"));
            }
            _ => panic!("expected live watched revision dispatch"),
        }
    }

    #[test]
    fn operator_account_watched_revision_routes_to_live_dispatch() {
        let title = "Synthetic Sensitive Page";
        let event = SyntheticRecentChange::default()
            .with_title(title)
            .with_user("SyntheticOperator")
            .with_revision_ids(Some(20), Some(88))
            .parse();
        let request_pages = vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()];
        let watched = HashSet::from([title.to_string()]);
        let dispatch = dispatch_recentchange_event(
            &event,
            Some("stream-88"),
            &RecentChangeDispatchContext {
                source_title_normalized: "Удзельнік:Wizardist/SuppressionList",
                request_pages: &request_pages,
                watched_set: &watched,
            },
        );

        match dispatch {
            RecentChangeDispatch::LiveWatchedRevision(candidate) => {
                assert_eq!(candidate.title, title);
                assert_eq!(candidate.normalized_title, title);
                assert_eq!(candidate.revid, 88);
                assert_eq!(candidate.user.as_deref(), Some("SyntheticOperator"));
                assert_eq!(candidate.event_id.as_deref(), Some("stream-88"));
            }
            _ => panic!("expected operator-account watched revision live dispatch"),
        }
    }

    #[test]
    fn unwatched_revision_routes_to_ignored_live_dispatch() {
        let event = SyntheticRecentChange::default()
            .with_title("Baz")
            .with_revision_ids(Some(10), Some(99))
            .parse();
        let request_pages = vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()];
        let watched = HashSet::from(["Foo".to_string()]);
        let dispatch = dispatch_recentchange_event(
            &event,
            Some("stream-99"),
            &RecentChangeDispatchContext {
                source_title_normalized: "Удзельнік:Wizardist/SuppressionList",
                request_pages: &request_pages,
                watched_set: &watched,
            },
        );

        match dispatch {
            RecentChangeDispatch::IgnoredLiveRevision(candidate) => {
                assert_eq!(candidate.title, "Baz");
                assert_eq!(candidate.revid, 99);
            }
            _ => panic!("expected ignored live revision dispatch"),
        }
    }

    #[tokio::test]
    async fn watched_revision_event_is_queued_for_live_hiding() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let event = SyntheticRecentChange::default()
            .with_title("Foo")
            .with_revision_ids(Some(10), Some(77))
            .parse();

        let event_id = handle_recentchange_event(&harness.runtime, event, Some("stream-77"))
            .await
            .unwrap();

        let action = harness.work_rx.try_recv().unwrap();
        let status = harness.runtime_status.lock().await.clone();

        assert_eq!(event_id.as_deref(), Some("stream-77"));
        assert_eq!(action.title, "Foo");
        assert_eq!(action.revids, vec![77]);
        assert_eq!(action.event_id.as_deref(), Some("stream-77"));
        assert_eq!(action.mode.label(), RevDelMode::Live.label());
        assert_eq!(status.realtime.last_matching_title.as_deref(), Some("Foo"));
        assert_eq!(status.realtime.last_matching_revid, Some(77));
        assert!(status.realtime.last_action_queued_at.is_some());
        assert_eq!(
            status
                .realtime
                .latest_outcome
                .as_ref()
                .map(|outcome| outcome.outcome.as_str()),
            Some("queued")
        );
    }

    #[tokio::test]
    async fn active_source_refresh_does_not_block_live_dispatch() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_delay(Duration::from_millis(200))
                    .set_body_raw(r#"{}"#, "application/json"),
            )
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let mut harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );

        spawn_source_refresh_trigger_with_timeout(
            &harness.runtime,
            "Удзельнік:Wizardist/SuppressionList",
            Some(44),
            SourceRefreshTriggerKind::SuppressionList,
            Duration::from_millis(200),
        )
        .await;
        assert!(harness.runtime.source_refresh_is_active());

        let event = SyntheticRecentChange::default()
            .with_title("Foo")
            .with_revision_ids(Some(76), Some(77))
            .parse();
        handle_recentchange_event(&harness.runtime, event, Some("stream-77"))
            .await
            .unwrap();

        let action = harness.work_rx.try_recv().unwrap();
        assert_eq!(action.title, "Foo");
        assert_eq!(action.revids, vec![77]);
        assert_eq!(action.mode.label(), RevDelMode::Live.label());
    }

    #[tokio::test]
    async fn source_refresh_timeout_records_status_and_releases_gate() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_delay(Duration::from_millis(200))
                    .set_body_raw(r#"{}"#, "application/json"),
            )
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );

        spawn_source_refresh_trigger_with_timeout(
            &harness.runtime,
            "Удзельнік:Wizardist/SuppressionList",
            Some(44),
            SourceRefreshTriggerKind::SuppressionList,
            Duration::from_millis(10),
        )
        .await;
        tokio::time::sleep(Duration::from_millis(50)).await;

        let status = harness.runtime_status.lock().await.clone();
        let refresh = status.realtime.last_source_refresh.as_ref().unwrap();
        assert!(!harness.runtime.source_refresh_is_active());
        assert_eq!(refresh.outcome, "refresh-timeout");
        assert_eq!(refresh.old_source_revid, Some(2));
        assert_eq!(refresh.new_source_revid, Some(2));
        assert_eq!(
            refresh.error.as_ref().map(|error| error.class.as_str()),
            Some("timeout")
        );
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("source-refresh")
        );
    }

    #[tokio::test]
    async fn duplicate_source_refresh_trigger_is_coalesced() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_delay(Duration::from_millis(200))
                    .set_body_raw(r#"{}"#, "application/json"),
            )
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );

        spawn_source_refresh_trigger_with_timeout(
            &harness.runtime,
            "Удзельнік:Wizardist/SuppressionList",
            Some(44),
            SourceRefreshTriggerKind::SuppressionList,
            Duration::from_millis(200),
        )
        .await;
        spawn_source_refresh_trigger_with_timeout(
            &harness.runtime,
            "Удзельнік:Wizardist/SuppressionList",
            Some(45),
            SourceRefreshTriggerKind::SuppressionList,
            Duration::from_millis(200),
        )
        .await;

        let status = harness.runtime_status.lock().await.clone();
        assert!(harness.runtime.source_refresh_is_active());
        assert!(
            status
                .last_notice
                .as_deref()
                .unwrap_or_default()
                .contains("coalesced trigger")
        );
    }

    #[tokio::test]
    async fn operator_account_watched_revision_event_is_queued_for_live_hiding() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let title = "Synthetic Sensitive Page";
        harness
            .runtime
            .cache
            .write()
            .await
            .replace_snapshot(test_snapshot(3, &[title], &[title], "synthetic"));
        let event = SyntheticRecentChange::default()
            .with_title(title)
            .with_user("SyntheticOperator")
            .with_revision_ids(Some(87), Some(88))
            .parse();

        let event_id = handle_recentchange_event(&harness.runtime, event, Some("stream-88"))
            .await
            .unwrap();

        let action = harness.work_rx.try_recv().unwrap();
        let status = harness.runtime_status.lock().await.clone();

        assert_eq!(event_id.as_deref(), Some("stream-88"));
        assert_eq!(action.title, title);
        assert_eq!(action.revids, vec![88]);
        assert_eq!(action.user.as_deref(), Some("SyntheticOperator"));
        assert_eq!(action.mode.label(), RevDelMode::Live.label());
        assert_eq!(status.realtime.last_matching_title.as_deref(), Some(title));
        assert_eq!(status.realtime.last_matching_revid, Some(88));
        assert_eq!(
            status
                .realtime
                .latest_outcome
                .as_ref()
                .map(|outcome| outcome.outcome.as_str()),
            Some("queued")
        );
    }

    #[tokio::test]
    async fn processed_watched_revision_is_not_requeued() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        harness.runtime.processed.write().await.insert(77);
        let event = SyntheticRecentChange::default()
            .with_title("Foo")
            .with_revision_ids(Some(10), Some(77))
            .parse();

        let event_id = handle_recentchange_event(&harness.runtime, event, Some("stream-77"))
            .await
            .unwrap();
        let status = harness.runtime_status.lock().await.clone();

        assert_eq!(event_id.as_deref(), Some("stream-77"));
        assert!(harness.work_rx.try_recv().is_err());
        assert_eq!(status.realtime.last_matching_title.as_deref(), Some("Foo"));
        assert!(status.realtime.last_action_queued_at.is_none());
        let outcome = status.realtime.latest_outcome.as_ref().unwrap();
        assert_eq!(outcome.outcome, "already-hidden");
        assert_eq!(outcome.reason_code.as_deref(), Some("already-processed"));
        assert_eq!(outcome.mode, RevDelMode::Live.label());
    }

    #[tokio::test]
    async fn non_watched_revision_event_is_observed_but_not_queued() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let event = SyntheticRecentChange::default()
            .with_title("Baz")
            .with_revision_ids(Some(10), Some(99))
            .parse();

        let event_id = handle_recentchange_event(&harness.runtime, event, Some("stream-99"))
            .await
            .unwrap();
        let status = harness.runtime_status.lock().await.clone();

        assert_eq!(event_id.as_deref(), Some("stream-99"));
        assert!(harness.work_rx.try_recv().is_err());
        assert_eq!(status.realtime.last_matching_title, None);
        assert_eq!(status.realtime.last_matching_revid, None);
    }

    #[tokio::test]
    async fn polled_watched_revision_is_queued_for_live_hiding_once_across_overlap() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let mut deduper = RecentChangePollDeduper::default();
        let observed_at = Utc.with_ymd_and_hms(2026, 5, 14, 18, 0, 10).unwrap();
        let keep_since = observed_at - TimeDelta::seconds(LIVE_POLL_DEDUP_TTL_SECONDS);
        let changes = vec![RecentChangeRecord {
            title: "Foo".to_string(),
            timestamp: observed_at,
            revid: 5141510,
        }];

        let summary = dispatch_polled_recentchanges_window(
            &harness.runtime,
            changes.clone(),
            &mut deduper,
            keep_since,
        )
        .await
        .unwrap();
        let action = harness.work_rx.try_recv().unwrap();
        let status = harness.runtime_status.lock().await.clone();

        assert_eq!(summary.total_changes, 1);
        assert_eq!(summary.watched_matches, 1);
        assert_eq!(action.title, "Foo");
        assert_eq!(action.revids, vec![5141510]);
        assert_eq!(status.realtime.last_matching_title.as_deref(), Some("Foo"));
        assert_eq!(status.realtime.last_matching_revid, Some(5141510));

        let repeat = dispatch_polled_recentchanges_window(
            &harness.runtime,
            changes,
            &mut deduper,
            keep_since,
        )
        .await
        .unwrap();

        assert_eq!(repeat.total_changes, 0);
        assert!(harness.work_rx.try_recv().is_err());
    }

    #[tokio::test]
    async fn polled_watched_revision_retries_after_live_dispatch_failure() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let mut deduper = RecentChangePollDeduper::default();
        let observed_at = Utc.with_ymd_and_hms(2026, 5, 14, 18, 0, 10).unwrap();
        let keep_since = observed_at - TimeDelta::seconds(LIVE_POLL_DEDUP_TTL_SECONDS);
        for offset in 0..harness.runtime.config.queue.capacity {
            harness
                .runtime
                .dispatch_action_batch(
                    format!("Queue filler {offset}"),
                    vec![900_000 + offset as u64],
                    None,
                    None,
                    None,
                    RevDelMode::Live,
                )
                .await
                .unwrap();
        }
        let changes = vec![RecentChangeRecord {
            title: "Foo".to_string(),
            timestamp: observed_at,
            revid: 5141511,
        }];

        let error = dispatch_polled_recentchanges_window(
            &harness.runtime,
            changes.clone(),
            &mut deduper,
            keep_since,
        )
        .await
        .unwrap_err();
        assert!(error.to_string().contains("live queue is full"));

        let _ = harness.work_rx.try_recv().unwrap();

        let retry = dispatch_polled_recentchanges_window(
            &harness.runtime,
            changes,
            &mut deduper,
            keep_since,
        )
        .await
        .unwrap();

        let mut saw_retried_revid = false;
        for _ in 0..harness.runtime.config.queue.capacity {
            let action = harness.work_rx.try_recv().unwrap();
            if action.revids == vec![5141511] {
                saw_retried_revid = true;
                break;
            }
        }

        assert_eq!(retry.total_changes, 1);
        assert_eq!(retry.watched_matches, 1);
        assert!(saw_retried_revid);
    }

    #[test]
    fn polled_request_page_change_routes_to_refresh_dispatch() {
        let request_pages = vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()];
        let watched = HashSet::from(["Foo".to_string()]);
        let change = RecentChangeRecord {
            title: "Вікіпедыя:Запыты да схавальнікаў".to_string(),
            timestamp: Utc.with_ymd_and_hms(2026, 5, 14, 18, 1, 0).unwrap(),
            revid: 6001,
        };

        let dispatch = dispatch_polled_recentchange_record(
            &change,
            &RecentChangeDispatchContext {
                source_title_normalized: "Удзельнік:Wizardist/SuppressionList",
                request_pages: &request_pages,
                watched_set: &watched,
            },
        );

        match dispatch {
            RecentChangeDispatch::RequestPageRefresh(trigger) => {
                assert_eq!(trigger.title, "Вікіпедыя:Запыты да схавальнікаў");
                assert_eq!(trigger.trigger_revid, Some(6001));
            }
            _ => panic!("expected request page refresh dispatch"),
        }
    }

    fn test_snapshot(
        source_revid: u64,
        listed: &[&str],
        watched: &[&str],
        hash: &str,
    ) -> SuppressionListCache {
        SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(source_revid),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: listed.iter().map(|value| (*value).to_string()).collect(),
            watched_titles_normalized: watched.iter().map(|value| (*value).to_string()).collect(),
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: hash.to_string(),
        }
    }

    #[test]
    fn source_refresh_plan_reports_delta_and_starts_title_scoped_catchup() {
        let before = test_snapshot(10, &["Foo", "Bar"], &["Foo", "Bar"], "old");
        let after = test_snapshot(11, &["Bar", "Baz", "Qux"], &["Bar", "Baz", "Qux"], "new");
        let started_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 0, 0).unwrap();
        let completed_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 0, 5).unwrap();
        let catchup_plan = plan_source_refresh_catchup(
            &before,
            &after,
            SourceRefreshTriggerKind::SuppressionList,
            10,
        );
        let refresh = plan_source_refresh(SourceRefreshPlanInput {
            before: &before,
            after: &after,
            refreshed: true,
            trigger_title: "Удзельнік:Wizardist/SuppressionList",
            trigger_revid: Some(11),
            catchup_plan: &catchup_plan,
            started_at,
            completed_at,
            deferred_until: None,
        });

        assert_eq!(refresh.trigger_revid, Some(11));
        assert_eq!(refresh.old_source_revid, Some(10));
        assert_eq!(refresh.new_source_revid, Some(11));
        assert_eq!(refresh.new_titles_count, 2);
        assert_eq!(refresh.removed_titles_count, 1);
        assert!(refresh.catchup_triggered);
        assert_eq!(refresh.catchup_title_scope.as_deref(), Some("new-titles"));
        assert_eq!(refresh.outcome, "catchup-started");
        assert_eq!(
            catchup_plan.followup,
            SourceRefreshFollowup::TitleScoped {
                scope_label: "new-titles",
                titles: vec!["Baz".to_string(), "Qux".to_string()],
            }
        );
    }

    #[test]
    fn source_refresh_plan_defers_large_new_title_scope_when_backoff_is_active() {
        let before = test_snapshot(10, &["Foo"], &["Foo"], "same");
        let after = test_snapshot(11, &["Foo", "Bar", "Baz"], &["Foo", "Bar", "Baz"], "same");
        let started_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 0, 0).unwrap();
        let completed_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 0, 5).unwrap();
        let deferred_until = Utc.with_ymd_and_hms(2026, 4, 29, 10, 2, 0).unwrap();
        let catchup_plan = plan_source_refresh_catchup(
            &before,
            &after,
            SourceRefreshTriggerKind::SuppressionList,
            1,
        );
        let refresh = plan_source_refresh(SourceRefreshPlanInput {
            before: &before,
            after: &after,
            refreshed: false,
            trigger_title: "Удзельнік:Wizardist/SuppressionList",
            trigger_revid: Some(11),
            catchup_plan: &catchup_plan,
            started_at,
            completed_at,
            deferred_until: Some(deferred_until),
        });

        assert!(!refresh.catchup_triggered);
        assert_eq!(
            refresh.catchup_title_scope.as_deref(),
            Some("new-titles-large")
        );
        assert_eq!(refresh.deferred_until, Some(deferred_until));
        assert_eq!(refresh.outcome, "catchup-deferred");
        assert_eq!(
            catchup_plan.followup,
            SourceRefreshFollowup::TitleScoped {
                scope_label: "new-titles-large",
                titles: vec!["Bar".to_string(), "Baz".to_string()],
            }
        );
    }

    #[test]
    fn request_page_refresh_plan_uses_recent_window_when_titles_are_unchanged() {
        let before = test_snapshot(10, &["Foo"], &["Foo"], "same");
        let after = test_snapshot(11, &["Foo"], &["Foo"], "same");
        let started_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 5, 0).unwrap();
        let completed_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 5, 1).unwrap();
        let catchup_plan =
            plan_source_refresh_catchup(&before, &after, SourceRefreshTriggerKind::RequestPage, 10);
        let refresh = plan_source_refresh(SourceRefreshPlanInput {
            before: &before,
            after: &after,
            refreshed: true,
            trigger_title: "Вікіпедыя:Запыты да схавальнікаў",
            trigger_revid: Some(55),
            catchup_plan: &catchup_plan,
            started_at,
            completed_at,
            deferred_until: None,
        });

        assert!(refresh.catchup_triggered);
        assert_eq!(
            refresh.catchup_title_scope.as_deref(),
            Some("request-window")
        );
        assert_eq!(refresh.outcome, "catchup-started");
        assert_eq!(refresh.trigger_revid, Some(55));
        assert_eq!(refresh.old_source_revid, Some(10));
        assert_eq!(refresh.new_source_revid, Some(11));
    }

    #[test]
    fn request_page_refresh_plan_prefers_new_titles_after_refresh() {
        let before = test_snapshot(10, &["Foo"], &["Foo"], "old");
        let after = test_snapshot(11, &["Foo", "Bar"], &["Foo", "Bar"], "new");
        let started_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 5, 0).unwrap();
        let completed_at = Utc.with_ymd_and_hms(2026, 4, 29, 10, 5, 1).unwrap();
        let catchup_plan =
            plan_source_refresh_catchup(&before, &after, SourceRefreshTriggerKind::RequestPage, 10);
        let refresh = plan_source_refresh(SourceRefreshPlanInput {
            before: &before,
            after: &after,
            refreshed: true,
            trigger_title: "Вікіпедыя:Запыты да схавальнікаў",
            trigger_revid: Some(55),
            catchup_plan: &catchup_plan,
            started_at,
            completed_at,
            deferred_until: None,
        });

        assert!(refresh.catchup_triggered);
        assert_eq!(refresh.catchup_title_scope.as_deref(), Some("new-titles"));
        assert_eq!(refresh.new_titles_count, 1);
        assert_eq!(
            catchup_plan.followup,
            SourceRefreshFollowup::TitleScoped {
                scope_label: "new-titles",
                titles: vec!["Bar".to_string()],
            }
        );
    }
}
