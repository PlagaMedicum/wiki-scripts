use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use anyhow::{Result, bail};
use chrono::{DateTime, TimeDelta, Utc};
use tokio::sync::oneshot;
use tracing::{info, warn};

use crate::mw_api::classify_api_failure;
use crate::runtime::{AppRuntime, DispatchCompletion, RevDelDispatch, RevDelMode};
use crate::state::{ApiFailureSnapshot, CoverageSummary, UnresolvedExposureItem, WarningSummary};
use crate::titles::normalize_title;

#[derive(Clone, Debug)]
pub struct CatchupRequest {
    pub start: DateTime<Utc>,
    pub end: DateTime<Utc>,
    pub trigger: String,
    pub scope_label: String,
    pub report_only: bool,
    pub allow_large_window: bool,
    pub title_scope: Option<Vec<String>>,
}

pub async fn run_default_catchup(
    runtime: &Arc<AppRuntime>,
    trigger: String,
) -> Result<CoverageSummary> {
    let end = Utc::now();
    let window = runtime.default_recovery_window(end).await;
    run_catchup_window(
        runtime,
        CatchupRequest {
            start: window.start,
            end,
            trigger,
            scope_label: window.scope_label,
            report_only: false,
            allow_large_window: window.allow_large_window,
            title_scope: None,
        },
    )
    .await
}

pub async fn run_title_scoped_catchup(
    runtime: &Arc<AppRuntime>,
    trigger: String,
    titles: Vec<String>,
) -> Result<CoverageSummary> {
    let end = Utc::now();
    let window = runtime.default_recovery_window(end).await;
    run_catchup_window(
        runtime,
        CatchupRequest {
            start: window.start,
            end,
            trigger,
            scope_label: window.scope_label,
            report_only: false,
            allow_large_window: window.allow_large_window,
            title_scope: Some(titles),
        },
    )
    .await
}

pub async fn run_catchup_window(
    runtime: &Arc<AppRuntime>,
    request: CatchupRequest,
) -> Result<CoverageSummary> {
    validate_window(
        runtime,
        request.start,
        request.end,
        request.allow_large_window,
        request.report_only,
    )?;
    runtime
        .mark_recovery_started(
            request.trigger.clone(),
            request.scope_label.clone(),
            request.start,
            request.end,
        )
        .await;
    let mut warning_aggregates =
        WarningAggregates::new(runtime.config.catchup.warning_sample_limit);
    let mut summary = CoverageSummary {
        scope_label: Some(request.scope_label.clone()),
        started_at: Some(request.start),
        ended_at: Some(request.end),
        requested_by: request.trigger.clone(),
        ..CoverageSummary::default()
    };

    if let Some(backoff_until) = runtime.current_backoff_until().await {
        summary.stopped_early_reason = Some("rate-limit-backoff-active".to_string());
        summary.backoff_until = Some(backoff_until);
        runtime.mark_recovery_completed(summary.clone()).await;
        return Ok(summary);
    }

    if request.title_scope.is_none() {
        match discover_recentchange_candidates(runtime, request.start, request.end).await {
            Ok(discovery) if !discovery.truncated => {
                summary.candidate_source = Some("recentchanges".to_string());
                summary.candidate_count = discovery.candidate_count;
                summary.watched_candidate_count = discovery.watched_candidates.len();
                summary.candidate_chunk_count = discovery.chunk_count;
                summary.candidate_discovery_elapsed_ms = Some(discovery.elapsed_ms);
                summary.pages_checked = discovery
                    .watched_candidates
                    .iter()
                    .map(|candidate| candidate.title.as_str())
                    .collect::<BTreeSet<_>>()
                    .len();
                info!(
                    trigger = %request.trigger,
                    candidate_count = discovery.candidate_count,
                    watched_candidate_count = discovery.watched_candidates.len(),
                    chunk_count = discovery.chunk_count,
                    elapsed_ms = discovery.elapsed_ms,
                    "starting candidate-first catch-up"
                );
                for candidate in discovery.watched_candidates {
                    if !process_revision_candidate(
                        runtime,
                        &request,
                        &mut summary,
                        &mut warning_aggregates,
                        candidate,
                    )
                    .await?
                    {
                        break;
                    }
                }
                summary.warning_summaries = warning_aggregates.into_summaries();
                runtime.mark_recovery_completed(summary.clone()).await;
                return Ok(summary);
            }
            Ok(discovery) => {
                summary.candidate_source = Some("full-scan-fallback".to_string());
                summary.candidate_count = discovery.candidate_count;
                summary.watched_candidate_count = discovery.watched_candidates.len();
                summary.candidate_chunk_count = discovery.chunk_count;
                summary.candidate_discovery_elapsed_ms = Some(discovery.elapsed_ms);
                summary.fallback_reason = Some("candidate-limit-reached".to_string());
            }
            Err(error) => {
                let failure = classify_api_failure(&error, "recentchanges", None, None);
                warning_aggregates.record(
                    failure,
                    runtime.config.catchup.rate_limit_stop_after_failures,
                    runtime.config.catchup.rate_limit_backoff_default_seconds,
                    Utc::now(),
                );
                summary.candidate_source = Some("full-scan-fallback".to_string());
                summary.fallback_reason = Some("candidate-source-unavailable".to_string());
            }
        }
    }

    let titles = scoped_titles(runtime, request.title_scope.clone()).await;

    info!(
        trigger = %request.trigger,
        pages = titles.len(),
        start = %request.start,
        end = %request.end,
        report_only = request.report_only,
        "starting bounded catch-up"
    );

    'titles: for title in titles {
        summary.pages_checked += 1;
        let revisions = match runtime
            .client
            .fetch_revisions_in_window(&title, request.start, request.end)
            .await
        {
            Ok(revisions) => revisions,
            Err(error) => {
                let failure = classify_api_failure(&error, "fetch-revisions", Some(&title), None);
                let observation = warning_aggregates.record(
                    failure.clone(),
                    runtime.config.catchup.rate_limit_stop_after_failures,
                    runtime.config.catchup.rate_limit_backoff_default_seconds,
                    Utc::now(),
                );
                summary.failed_count += 1;
                push_unresolved_item(
                    &mut summary,
                    runtime.config.catchup.unresolved_sample_limit,
                    UnresolvedExposureItem {
                        title: title.clone(),
                        revid: 0,
                        revision_url: None,
                        age_seconds: None,
                        reason: format!("revision-query-failed:{}", warning_reason(&failure)),
                        next_action: "check API/network and rerun catch-up".to_string(),
                    },
                );
                if observation.stop_after {
                    summary.stopped_early_reason = Some("rate-limited".to_string());
                    summary.backoff_until = observation.backoff_until;
                    break 'titles;
                }
                continue;
            }
        };

        for revision in revisions.into_iter().rev() {
            if !process_revision_candidate(
                runtime,
                &request,
                &mut summary,
                &mut warning_aggregates,
                CatchupRevisionCandidate {
                    title: title.clone(),
                    revid: revision.revid,
                    timestamp: revision.timestamp,
                    user_hidden: revision.user_hidden,
                    comment_hidden: revision.comment_hidden,
                    hidden_state_verified: true,
                },
            )
            .await?
            {
                break 'titles;
            }
        }
    }

    summary.warning_summaries = warning_aggregates.into_summaries();
    for warning in &summary.warning_summaries {
        warn!(
            count = warning.count,
            class = %warning.class,
            api_code = ?warning.api_code,
            http_status = ?warning.http_status,
            retry_after_seconds = ?warning.retry_after_seconds,
            stopped_early = warning.stopped_early,
            sample_titles = ?warning.sample_titles,
            "catch-up page query failures coalesced"
        );
    }
    runtime.mark_recovery_completed(summary.clone()).await;
    Ok(summary)
}

#[derive(Clone, Debug)]
struct CatchupRevisionCandidate {
    title: String,
    revid: u64,
    timestamp: DateTime<Utc>,
    user_hidden: bool,
    comment_hidden: bool,
    hidden_state_verified: bool,
}

#[derive(Clone, Debug)]
struct CandidateDiscovery {
    candidate_count: usize,
    watched_candidates: Vec<CatchupRevisionCandidate>,
    chunk_count: usize,
    truncated: bool,
    elapsed_ms: u64,
}

async fn discover_recentchange_candidates(
    runtime: &Arc<AppRuntime>,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
) -> Result<CandidateDiscovery> {
    let started = std::time::Instant::now();
    let recent = runtime
        .client
        .fetch_recent_changes_in_window(start, end, runtime.config.catchup.max_revisions_per_run)
        .await?;
    let watched_set = runtime.cache.read().await.watched_set.clone();
    let candidate_count = recent.changes.len();
    let mut seen_revids = BTreeSet::new();
    let mut watched_candidates = Vec::new();
    for change in recent.changes {
        if !watched_set.contains(&normalize_title(&change.title))
            || !seen_revids.insert(change.revid)
        {
            continue;
        }
        watched_candidates.push(CatchupRevisionCandidate {
            title: change.title,
            revid: change.revid,
            timestamp: change.timestamp,
            user_hidden: false,
            comment_hidden: false,
            hidden_state_verified: false,
        });
    }
    Ok(CandidateDiscovery {
        candidate_count,
        watched_candidates,
        chunk_count: recent.chunk_count,
        truncated: recent.truncated,
        elapsed_ms: started.elapsed().as_millis() as u64,
    })
}

async fn process_revision_candidate(
    runtime: &Arc<AppRuntime>,
    request: &CatchupRequest,
    summary: &mut CoverageSummary,
    warning_aggregates: &mut WarningAggregates,
    mut candidate: CatchupRevisionCandidate,
) -> Result<bool> {
    if summary.edits_checked >= runtime.config.catchup.max_revisions_per_run {
        summary.stopped_early_reason = Some("max-revisions-reached".to_string());
        push_unresolved_item(
            summary,
            runtime.config.catchup.unresolved_sample_limit,
            UnresolvedExposureItem {
                title: candidate.title,
                revid: candidate.revid,
                revision_url: Some(crate::mw_api::revision_url(
                    &runtime.config.wiki.server_name,
                    candidate.revid,
                )),
                age_seconds: Some((Utc::now() - candidate.timestamp).num_seconds()),
                reason: "max-revisions-reached".to_string(),
                next_action: "rerun catch-up with a narrower window".to_string(),
            },
        );
        return Ok(false);
    }
    summary.edits_checked += 1;
    let needs_report_only_verification = request.report_only
        && !candidate.hidden_state_verified
        && (!candidate.user_hidden || !candidate.comment_hidden);
    if needs_report_only_verification
        && !verify_report_only_candidate(runtime, summary, warning_aggregates, &mut candidate)
            .await?
    {
        return Ok(summary.stopped_early_reason.is_none());
    }
    if candidate.user_hidden && candidate.comment_hidden {
        summary.already_hidden_count += 1;
        return Ok(true);
    }
    if request.report_only {
        push_unresolved_item(
            summary,
            runtime.config.catchup.unresolved_sample_limit,
            UnresolvedExposureItem {
                title: candidate.title,
                revid: candidate.revid,
                revision_url: Some(crate::mw_api::revision_url(
                    &runtime.config.wiki.server_name,
                    candidate.revid,
                )),
                age_seconds: Some((Utc::now() - candidate.timestamp).num_seconds()),
                reason: "report-only-not-hidden".to_string(),
                next_action: "run emergency catch-up without report-only".to_string(),
            },
        );
        return Ok(true);
    }
    let (completion_tx, completion_rx) = oneshot::channel();
    runtime
        .dispatch_action(RevDelDispatch {
            title: candidate.title.clone(),
            revids: vec![candidate.revid],
            event_id: None,
            user: None,
            comment: None,
            mode: RevDelMode::Catchup,
            observed_at: Some(candidate.timestamp),
            recovery_trigger: Some(request.trigger.clone()),
            completion_tx: Some(completion_tx),
        })
        .await?;
    match tokio::time::timeout(std::time::Duration::from_secs(60), completion_rx).await {
        Ok(Ok(Ok(DispatchCompletion::Hidden))) => summary.hidden_count += 1,
        Ok(Ok(Ok(DispatchCompletion::AlreadyHandled))) => summary.already_hidden_count += 1,
        Ok(Ok(Err(reason))) => {
            summary.failed_count += 1;
            push_unresolved_item(
                summary,
                runtime.config.catchup.unresolved_sample_limit,
                UnresolvedExposureItem {
                    title: candidate.title,
                    revid: candidate.revid,
                    revision_url: Some(crate::mw_api::revision_url(
                        &runtime.config.wiki.server_name,
                        candidate.revid,
                    )),
                    age_seconds: Some((Utc::now() - candidate.timestamp).num_seconds()),
                    reason,
                    next_action: "review auth/API state and rerun catch-up".to_string(),
                },
            );
        }
        Ok(Err(_)) | Err(_) => {
            push_unresolved_item(
                summary,
                runtime.config.catchup.unresolved_sample_limit,
                UnresolvedExposureItem {
                    title: candidate.title,
                    revid: candidate.revid,
                    revision_url: Some(crate::mw_api::revision_url(
                        &runtime.config.wiki.server_name,
                        candidate.revid,
                    )),
                    age_seconds: Some((Utc::now() - candidate.timestamp).num_seconds()),
                    reason: "worker-completion-timeout".to_string(),
                    next_action: "check worker status and rerun catch-up".to_string(),
                },
            );
        }
    }
    Ok(true)
}

async fn verify_report_only_candidate(
    runtime: &Arc<AppRuntime>,
    summary: &mut CoverageSummary,
    warning_aggregates: &mut WarningAggregates,
    candidate: &mut CatchupRevisionCandidate,
) -> Result<bool> {
    match runtime.client.fetch_revision_by_id(candidate.revid).await {
        Ok(Some(revision)) => {
            candidate.timestamp = revision.timestamp;
            candidate.user_hidden = revision.user_hidden;
            candidate.comment_hidden = revision.comment_hidden;
            candidate.hidden_state_verified = true;
            Ok(true)
        }
        Ok(None) => {
            summary.failed_count += 1;
            push_unresolved_item(
                summary,
                runtime.config.catchup.unresolved_sample_limit,
                UnresolvedExposureItem {
                    title: candidate.title.clone(),
                    revid: candidate.revid,
                    revision_url: Some(crate::mw_api::revision_url(
                        &runtime.config.wiki.server_name,
                        candidate.revid,
                    )),
                    age_seconds: Some((Utc::now() - candidate.timestamp).num_seconds()),
                    reason: "revision-query-missing".to_string(),
                    next_action: "rerun coverage; if the revision was deleted, verify manually"
                        .to_string(),
                },
            );
            Ok(false)
        }
        Err(error) => {
            let failure = classify_api_failure(
                &error,
                "fetch-revision",
                Some(&candidate.title),
                Some(candidate.revid),
            );
            let observation = warning_aggregates.record(
                failure.clone(),
                runtime.config.catchup.rate_limit_stop_after_failures,
                runtime.config.catchup.rate_limit_backoff_default_seconds,
                Utc::now(),
            );
            summary.failed_count += 1;
            push_unresolved_item(
                summary,
                runtime.config.catchup.unresolved_sample_limit,
                UnresolvedExposureItem {
                    title: candidate.title.clone(),
                    revid: candidate.revid,
                    revision_url: Some(crate::mw_api::revision_url(
                        &runtime.config.wiki.server_name,
                        candidate.revid,
                    )),
                    age_seconds: Some((Utc::now() - candidate.timestamp).num_seconds()),
                    reason: format!("revision-query-failed:{}", warning_reason(&failure)),
                    next_action: "check API/network and rerun coverage".to_string(),
                },
            );
            if observation.stop_after {
                summary.stopped_early_reason = Some("rate-limited".to_string());
                summary.backoff_until = observation.backoff_until;
            }
            Ok(false)
        }
    }
}

async fn scoped_titles(runtime: &Arc<AppRuntime>, title_scope: Option<Vec<String>>) -> Vec<String> {
    let watched_titles = runtime.cache.read().await.watched_titles().to_vec();
    scoped_titles_from_input(&watched_titles, title_scope)
}

fn scoped_titles_from_input(
    watched_titles: &[String],
    title_scope: Option<Vec<String>>,
) -> Vec<String> {
    let mut titles = match title_scope {
        Some(titles) => titles,
        None => watched_titles.to_vec(),
    };
    titles.sort();
    titles.dedup();
    titles
}

pub fn validate_window(
    runtime: &AppRuntime,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
    allow_large_window: bool,
    report_only: bool,
) -> Result<()> {
    if end < start {
        bail!("catch-up window end must be >= start");
    }
    let seconds = (end - start).num_seconds();
    if seconds > runtime.config.catchup.max_window_seconds && !allow_large_window && !report_only {
        bail!(
            "catch-up window {}s exceeds configured maximum {}s",
            seconds,
            runtime.config.catchup.max_window_seconds
        );
    }
    Ok(())
}

pub fn format_summary_lines(summary: &CoverageSummary) -> Vec<String> {
    let mut lines = vec![
        format!(
            "coverage.scope_label={}",
            summary.scope_label.as_deref().unwrap_or("recent window")
        ),
        format!("coverage.requested_by={}", summary.requested_by),
        format!("coverage.pages_checked={}", summary.pages_checked),
        format!("coverage.edits_checked={}", summary.edits_checked),
        format!("coverage.hidden={}", summary.hidden_count),
        format!("coverage.already_hidden={}", summary.already_hidden_count),
        format!("coverage.skipped={}", summary.skipped_count),
        format!("coverage.failed={}", summary.failed_count),
        format!("coverage.unresolved={}", summary.unresolved_count),
    ];
    if let Some(source) = summary.candidate_source.as_deref() {
        lines.push(format!("coverage.candidate_source={}", source));
        lines.push(format!(
            "coverage.candidate_count={}",
            summary.candidate_count
        ));
        lines.push(format!(
            "coverage.watched_candidate_count={}",
            summary.watched_candidate_count
        ));
        lines.push(format!(
            "coverage.candidate_chunk_count={}",
            summary.candidate_chunk_count
        ));
        if let Some(elapsed_ms) = summary.candidate_discovery_elapsed_ms {
            lines.push(format!(
                "coverage.candidate_discovery_elapsed_ms={}",
                elapsed_ms
            ));
        }
    }
    if let Some(reason) = summary.fallback_reason.as_deref() {
        lines.push(format!("coverage.fallback_reason={}", reason));
    }
    if let Some(reason) = summary.stopped_early_reason.as_deref() {
        lines.push(format!("coverage.stopped_early_reason={}", reason));
    }
    if let Some(until) = summary.backoff_until.as_ref() {
        lines.push(format!(
            "coverage.backoff_until={}",
            until.format("%Y-%m-%dT%H:%M:%SZ")
        ));
    }
    for item in &summary.unresolved_items {
        lines.push(format!(
            "coverage.unresolved_item title={} revid={} revision_url={} age_seconds={} reason={} next_action={}",
            compact_report_text(&item.title),
            item.revid,
            item.revision_url.as_deref().unwrap_or("none"),
            item.age_seconds
                .map(|value| value.to_string())
                .unwrap_or_else(|| "unknown".to_string()),
            sanitize_report_detail(&item.reason),
            sanitize_report_detail(&item.next_action)
        ));
    }
    for warning in &summary.warning_summaries {
        lines.push(format!(
            "coverage.warning_summary class={} api_code={} http_status={} retryable={} retry_after_seconds={} count={} samples={} stopped_early={}",
            warning.class,
            warning.api_code.as_deref().unwrap_or("none"),
            warning
                .http_status
                .map(|value| value.to_string())
                .unwrap_or_else(|| "none".to_string()),
            warning.retryable,
            warning
                .retry_after_seconds
                .map(|value| value.to_string())
                .unwrap_or_else(|| "none".to_string()),
            warning.count,
            warning.sample_titles.join("|"),
            warning.stopped_early
        ));
    }
    lines
}

fn push_unresolved_item(
    summary: &mut CoverageSummary,
    sample_limit: usize,
    item: UnresolvedExposureItem,
) {
    summary.unresolved_count += 1;
    if summary.unresolved_items.len() < sample_limit {
        summary.unresolved_items.push(item);
    }
}

fn compact_report_text(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .chars()
        .take(180)
        .collect()
}

fn sanitize_report_detail(value: &str) -> String {
    let compact = compact_report_text(value);
    let lower = compact.to_ascii_lowercase();
    let marker = [
        "response body",
        "response-body",
        "set-cookie",
        "cookie=",
        "cookie:",
        "token=",
        "token:",
        "password=",
        "password:",
        "authorization:",
        "csrf",
    ]
    .into_iter()
    .filter_map(|marker| lower.find(marker).map(|index| (index, marker)))
    .min_by_key(|(index, _)| *index);
    if let Some((index, marker)) = marker {
        let prefix = compact[..index].trim();
        let suffix = if marker.contains("body") {
            "response-body-redacted"
        } else {
            "sensitive-details-redacted"
        };
        return if prefix.is_empty() {
            suffix.to_string()
        } else {
            format!("{prefix} {suffix}")
        };
    }
    compact
}

fn warning_reason(snapshot: &ApiFailureSnapshot) -> String {
    snapshot
        .api_code
        .as_deref()
        .unwrap_or(snapshot.class.as_str())
        .to_string()
}

#[derive(Clone, Debug)]
struct WarningAggregates {
    sample_limit: usize,
    by_key: BTreeMap<String, WarningSummary>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct WarningObservation {
    stop_after: bool,
    backoff_until: Option<DateTime<Utc>>,
}

impl WarningAggregates {
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
    ) -> WarningObservation {
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
            rate_limit_retry_after_seconds(&snapshot, default_backoff_seconds);
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
        if let Some(title) = snapshot.sample_title
            && entry.sample_titles.len() < self.sample_limit
            && !entry.sample_titles.contains(&title)
        {
            entry.sample_titles.push(title);
        }
        let stop_after =
            entry.retry_after_seconds.is_some() && entry.count >= stop_after_failures.max(1);
        if stop_after {
            entry.stopped_early = true;
        }
        WarningObservation {
            stop_after,
            backoff_until: stop_after.then(|| {
                now + TimeDelta::seconds(
                    entry
                        .retry_after_seconds
                        .unwrap_or(default_backoff_seconds)
                        .min(i64::MAX as u64) as i64,
                )
            }),
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

fn rate_limit_retry_after_seconds(
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
        None
    }
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;
    use wiremock::matchers::{method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    use super::*;
    use crate::config::EnvConfig;
    use crate::runtime::{RuntimeStatusSurfaceMode, build_test_runtime_harness_with_env};

    #[test]
    fn formats_summary_without_sensitive_payloads() {
        let summary = CoverageSummary {
            requested_by: "operator-manual".to_string(),
            pages_checked: 1,
            edits_checked: 2,
            hidden_count: 1,
            unresolved_count: 1,
            unresolved_items: vec![UnresolvedExposureItem {
                title: "Sensitive Page".to_string(),
                revid: 42,
                revision_url: Some("https://example.invalid/wiki/Special:Diff/42".to_string()),
                age_seconds: Some(15),
                reason: "report-only-not-hidden".to_string(),
                next_action: "run emergency catch-up without report-only".to_string(),
            }],
            ..CoverageSummary::default()
        };

        let rendered = format_summary_lines(&summary).join("\n");

        assert!(rendered.contains("coverage.unresolved=1"));
        assert!(rendered.contains("revid=42"));
        assert!(!rendered.contains("comment="));
        assert!(!rendered.contains("token="));
    }

    #[test]
    fn unresolved_item_details_are_sanitized_but_stay_actionable() {
        let summary = CoverageSummary {
            unresolved_items: vec![UnresolvedExposureItem {
                title: "Sensitive Page".to_string(),
                revid: 42,
                revision_url: Some("https://example.invalid/wiki/Special:Diff/42".to_string()),
                age_seconds: Some(15),
                reason: "revisiondelete failed token=abc123 cookie=session raw comment".to_string(),
                next_action: "inspect response body: <html>denied</html> and password=secret"
                    .to_string(),
            }],
            unresolved_count: 1,
            ..CoverageSummary::default()
        };

        let rendered = format_summary_lines(&summary).join("\n");

        assert!(rendered.contains("title=Sensitive Page"));
        assert!(rendered.contains("revid=42"));
        assert!(rendered.contains("age_seconds=15"));
        assert!(rendered.contains("reason=revisiondelete failed sensitive-details-redacted"));
        assert!(rendered.contains("next_action=inspect response-body-redacted"));
        assert!(!rendered.contains("abc123"));
        assert!(!rendered.contains("session"));
        assert!(!rendered.contains("<html>"));
        assert!(!rendered.contains("password=secret"));
    }

    #[test]
    fn warning_aggregates_coalesce_repeated_root_causes() {
        let mut aggregates = WarningAggregates::new(2);
        for title in ["A", "B", "C"] {
            let _ = aggregates.record(
                ApiFailureSnapshot {
                    class: "api-json-error".to_string(),
                    api_code: Some("badtimestamp".to_string()),
                    http_status: Some(200),
                    retryable: false,
                    operation: "fetch-revisions".to_string(),
                    sample_title: Some(title.to_string()),
                    message: "invalid timestamp".to_string(),
                    ..ApiFailureSnapshot::default()
                },
                3,
                30,
                Utc::now(),
            );
        }

        let summaries = aggregates.into_summaries();

        assert_eq!(summaries.len(), 1);
        assert_eq!(summaries[0].count, 3);
        assert_eq!(summaries[0].api_code.as_deref(), Some("badtimestamp"));
        assert_eq!(summaries[0].sample_titles, vec!["A", "B"]);
    }

    #[test]
    fn warning_aggregates_stop_early_for_repeated_rate_limits() {
        let mut aggregates = WarningAggregates::new(2);
        let now = DateTime::parse_from_rfc3339("2026-04-25T17:05:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let mut observation = WarningObservation::default();
        for title in ["A", "B", "C"] {
            observation = aggregates.record(
                ApiFailureSnapshot {
                    class: "non-json-response".to_string(),
                    http_status: Some(429),
                    retryable: true,
                    retry_after_seconds: Some(45),
                    operation: "fetch-revisions".to_string(),
                    sample_title: Some(title.to_string()),
                    message: "rate limited".to_string(),
                    ..ApiFailureSnapshot::default()
                },
                3,
                30,
                now,
            );
        }

        let summaries = aggregates.into_summaries();

        assert!(observation.stop_after);
        assert_eq!(
            observation.backoff_until,
            Some(now + TimeDelta::seconds(45))
        );
        assert_eq!(summaries[0].retry_after_seconds, Some(45));
        assert!(summaries[0].stopped_early);
    }

    #[test]
    fn unresolved_samples_are_bounded_but_counts_keep_growing() {
        let mut summary = CoverageSummary::default();

        for revid in 1..=4 {
            push_unresolved_item(
                &mut summary,
                2,
                UnresolvedExposureItem {
                    title: format!("Page {revid}"),
                    revid,
                    revision_url: Some(format!(
                        "https://be.wikipedia.org/wiki/Special:Diff/{revid}"
                    )),
                    age_seconds: Some(5),
                    reason: "rate-limited".to_string(),
                    next_action: "retry later".to_string(),
                },
            );
        }

        assert_eq!(summary.unresolved_count, 4);
        assert_eq!(summary.unresolved_items.len(), 2);
        assert_eq!(summary.unresolved_items[0].revid, 1);
        assert_eq!(summary.unresolved_items[1].revid, 2);
    }

    #[test]
    fn formats_summary_with_backoff_and_stop_reason() {
        let summary = CoverageSummary {
            requested_by: "operator-manual".to_string(),
            stopped_early_reason: Some("rate-limited".to_string()),
            backoff_until: Some(
                DateTime::parse_from_rfc3339("2026-04-25T17:06:00Z")
                    .unwrap()
                    .with_timezone(&Utc),
            ),
            warning_summaries: vec![WarningSummary {
                class: "non-json-response".to_string(),
                http_status: Some(429),
                retryable: true,
                retry_after_seconds: Some(30),
                operation: "fetch-revisions".to_string(),
                count: 3,
                sample_titles: vec!["A".to_string()],
                message: "rate limited".to_string(),
                stopped_early: true,
                ..WarningSummary::default()
            }],
            ..CoverageSummary::default()
        };

        let rendered = format_summary_lines(&summary).join("\n");

        assert!(rendered.contains("coverage.stopped_early_reason=rate-limited"));
        assert!(rendered.contains("coverage.backoff_until=2026-04-25T17:06:00Z"));
        assert!(rendered.contains("retry_after_seconds=30"));
        assert!(rendered.contains("stopped_early=true"));
    }

    #[test]
    fn title_scoped_catchup_dedups_and_sorts_requested_titles() {
        let titles = scoped_titles_from_input(
            &["Watched A".to_string(), "Watched B".to_string()],
            Some(vec![
                "Title B".to_string(),
                "Title A".to_string(),
                "Title B".to_string(),
            ]),
        );

        assert_eq!(titles, vec!["Title A".to_string(), "Title B".to_string()]);
    }

    #[test]
    fn catchup_without_title_scope_uses_full_watched_set() {
        let titles =
            scoped_titles_from_input(&["Watched B".to_string(), "Watched A".to_string()], None);

        assert_eq!(
            titles,
            vec!["Watched A".to_string(), "Watched B".to_string()]
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

    fn empty_revisions_response() -> &'static str {
        r#"{"query":{"pages":[{"pageid":1,"revisions":[]}]}}"#
    }

    fn recentchanges_response() -> &'static str {
        r#"{
          "query": {
            "recentchanges": [
              {
                "title": "Foo",
                "timestamp": "2026-05-13T12:00:00Z",
                "revid": 101
              },
              {
                "title": "Unwatched",
                "timestamp": "2026-05-13T12:01:00Z",
                "revid": 102
              }
            ]
          }
        }"#
    }

    fn revision_by_id_response(revid: u64, hidden: bool) -> String {
        let hidden_fields = if hidden {
            r#","userhidden":true,"commenthidden":true"#
        } else {
            ""
        };
        format!(
            r#"{{
              "query": {{
                "pages": [
                  {{
                    "pageid": 1,
                    "title": "Foo",
                    "revisions": [
                      {{"revid": {revid}, "timestamp": "2026-05-13T12:00:00Z"{hidden_fields}}}
                    ]
                  }}
                ]
              }}
            }}"#
        )
    }

    #[tokio::test]
    async fn default_catchup_reports_last_successful_hide_anchor_in_summary() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(empty_revisions_response(), "application/json"),
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
        let anchor = Utc::now() - TimeDelta::hours(3);
        harness
            .runtime
            .update_runtime_status(move |status| {
                status.realtime.last_successful_hide_at = Some(anchor);
            })
            .await;

        let summary = run_default_catchup(&harness.runtime, "stream-gap".to_string())
            .await
            .unwrap();

        assert_eq!(
            summary.scope_label.as_deref(),
            Some("since last successful hide")
        );
        assert_eq!(summary.requested_by, "stream-gap");
        assert_eq!(summary.started_at, Some(anchor));
        assert!(
            summary
                .ended_at
                .zip(summary.started_at)
                .is_some_and(|(end, start)| {
                    (end - start).num_seconds() > harness.runtime.config.catchup.max_window_seconds
                })
        );
    }

    #[tokio::test]
    async fn default_catchup_reports_recent_emergency_window_when_anchor_is_missing() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(empty_revisions_response(), "application/json"),
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

        let summary = run_default_catchup(&harness.runtime, "startup".to_string())
            .await
            .unwrap();
        let start = summary.started_at.unwrap();
        let end = summary.ended_at.unwrap();

        assert_eq!(
            summary.scope_label.as_deref(),
            Some("recent emergency window")
        );
        assert_eq!(summary.requested_by, "startup");
        assert_eq!(
            (end - start).num_seconds(),
            harness.runtime.config.catchup.default_window_seconds
        );
    }

    #[tokio::test]
    async fn ordinary_catchup_uses_recentchanges_candidates_before_full_scan() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("list", "recentchanges"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(recentchanges_response(), "application/json"),
            )
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("revids", "101"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(revision_by_id_response(101, false), "application/json"),
            )
            .expect(1)
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );
        let start = DateTime::parse_from_rfc3339("2026-05-13T11:59:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let end = DateTime::parse_from_rfc3339("2026-05-13T12:02:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let summary = run_catchup_window(
            &harness.runtime,
            CatchupRequest {
                start,
                end,
                trigger: "startup".to_string(),
                scope_label: "recent emergency window".to_string(),
                report_only: true,
                allow_large_window: false,
                title_scope: None,
            },
        )
        .await
        .unwrap();

        assert_eq!(summary.candidate_source.as_deref(), Some("recentchanges"));
        assert_eq!(summary.candidate_count, 2);
        assert_eq!(summary.watched_candidate_count, 1);
        assert_eq!(summary.pages_checked, 1);
        assert_eq!(summary.edits_checked, 1);
        assert_eq!(summary.unresolved_count, 1);
        assert_eq!(summary.fallback_reason, None);
        assert!(summary.candidate_discovery_elapsed_ms.is_some());
    }

    #[tokio::test]
    async fn report_only_recentchanges_verifies_already_hidden_candidate() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("list", "recentchanges"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(recentchanges_response(), "application/json"),
            )
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("revids", "101"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(revision_by_id_response(101, true), "application/json"),
            )
            .expect(1)
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );
        let start = DateTime::parse_from_rfc3339("2026-05-13T11:59:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let end = DateTime::parse_from_rfc3339("2026-05-13T12:02:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let summary = run_catchup_window(
            &harness.runtime,
            CatchupRequest {
                start,
                end,
                trigger: "coverage-last-24h".to_string(),
                scope_label: "Last 24 hours".to_string(),
                report_only: true,
                allow_large_window: false,
                title_scope: None,
            },
        )
        .await
        .unwrap();

        assert_eq!(summary.edits_checked, 1);
        assert_eq!(summary.already_hidden_count, 1);
        assert_eq!(summary.unresolved_count, 0);
        assert_eq!(summary.failed_count, 0);
    }

    #[tokio::test]
    async fn catchup_counts_already_processed_candidate_as_already_hidden() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("list", "recentchanges"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(recentchanges_response(), "application/json"),
            )
            .expect(1)
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = test_env(&temp, format!("{}/w/api.php", server.uri()));
        let harness = build_test_runtime_harness_with_env(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
        );
        harness.runtime.processed.write().await.insert(101);
        let start = DateTime::parse_from_rfc3339("2026-05-13T11:59:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let end = DateTime::parse_from_rfc3339("2026-05-13T12:02:00Z")
            .unwrap()
            .with_timezone(&Utc);

        let summary = run_catchup_window(
            &harness.runtime,
            CatchupRequest {
                start,
                end,
                trigger: "startup".to_string(),
                scope_label: "recent emergency window".to_string(),
                report_only: false,
                allow_large_window: false,
                title_scope: None,
            },
        )
        .await
        .unwrap();

        assert_eq!(summary.hidden_count, 0);
        assert_eq!(summary.already_hidden_count, 1);
        assert_eq!(summary.failed_count, 0);
    }

    #[tokio::test]
    async fn full_scan_fallback_requires_candidate_failure_reason() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("list", "recentchanges"))
            .respond_with(ResponseTemplate::new(500).set_body_raw("temporary", "text/plain"))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("prop", "revisions"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(empty_revisions_response(), "application/json"),
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
        let end = Utc::now();

        let summary = run_catchup_window(
            &harness.runtime,
            CatchupRequest {
                start: end - TimeDelta::minutes(5),
                end,
                trigger: "startup".to_string(),
                scope_label: "recent emergency window".to_string(),
                report_only: true,
                allow_large_window: false,
                title_scope: None,
            },
        )
        .await
        .unwrap();

        assert_eq!(
            summary.candidate_source.as_deref(),
            Some("full-scan-fallback")
        );
        assert_eq!(
            summary.fallback_reason.as_deref(),
            Some("candidate-source-unavailable")
        );
        assert_eq!(summary.pages_checked, 2);
    }
}
