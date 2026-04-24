use std::sync::Arc;

use anyhow::{Result, bail};
use chrono::{DateTime, TimeDelta, Utc};
use tokio::sync::oneshot;
use tracing::{info, warn};

use crate::runtime::{AppRuntime, RevDelDispatch, RevDelMode};
use crate::state::{CoverageSummary, UnresolvedExposureItem};

#[derive(Clone, Debug)]
pub struct CatchupRequest {
    pub start: DateTime<Utc>,
    pub end: DateTime<Utc>,
    pub trigger: String,
    pub report_only: bool,
}

pub async fn run_default_catchup(
    runtime: &Arc<AppRuntime>,
    trigger: String,
) -> Result<CoverageSummary> {
    let end = Utc::now();
    let start = end - TimeDelta::seconds(runtime.config.catchup.default_window_seconds);
    run_catchup_window(
        runtime,
        CatchupRequest {
            start,
            end,
            trigger,
            report_only: false,
        },
    )
    .await
}

pub async fn run_catchup_window(
    runtime: &Arc<AppRuntime>,
    request: CatchupRequest,
) -> Result<CoverageSummary> {
    validate_window(runtime, request.start, request.end)?;
    runtime.mark_recovery_started(request.trigger.clone()).await;
    let titles = runtime.cache.read().await.watched_titles().to_vec();
    let mut summary = CoverageSummary {
        started_at: Some(request.start),
        ended_at: Some(request.end),
        requested_by: request.trigger.clone(),
        pages_checked: titles.len(),
        ..CoverageSummary::default()
    };

    info!(
        trigger = %request.trigger,
        pages = titles.len(),
        start = %request.start,
        end = %request.end,
        report_only = request.report_only,
        "starting bounded catch-up"
    );

    'titles: for title in titles {
        let revisions = match runtime
            .client
            .fetch_revisions_in_window(&title, request.start, request.end)
            .await
        {
            Ok(revisions) => revisions,
            Err(error) => {
                summary.failed_count += 1;
                summary.unresolved_count += 1;
                summary.unresolved_items.push(UnresolvedExposureItem {
                    title: title.clone(),
                    revid: 0,
                    age_seconds: None,
                    reason: "revision-query-failed".to_string(),
                    next_action: "check API/network and rerun catch-up".to_string(),
                });
                warn!(title = %title, error = %error, "catch-up page query failed");
                continue;
            }
        };

        for revision in revisions {
            if summary.edits_checked >= runtime.config.catchup.max_revisions_per_run {
                summary.unresolved_count += 1;
                summary.unresolved_items.push(UnresolvedExposureItem {
                    title: title.clone(),
                    revid: revision.revid,
                    age_seconds: Some((Utc::now() - revision.timestamp).num_seconds()),
                    reason: "max-revisions-reached".to_string(),
                    next_action: "rerun catch-up with a narrower window".to_string(),
                });
                break 'titles;
            }
            summary.edits_checked += 1;
            if revision.user_hidden && revision.comment_hidden {
                summary.already_hidden_count += 1;
                continue;
            }
            if request.report_only {
                summary.unresolved_count += 1;
                summary.unresolved_items.push(UnresolvedExposureItem {
                    title: title.clone(),
                    revid: revision.revid,
                    age_seconds: Some((Utc::now() - revision.timestamp).num_seconds()),
                    reason: "report-only-not-hidden".to_string(),
                    next_action: "run emergency catch-up without report-only".to_string(),
                });
                continue;
            }
            let (completion_tx, completion_rx) = oneshot::channel();
            runtime
                .dispatch_action(RevDelDispatch {
                    title: title.clone(),
                    revids: vec![revision.revid],
                    event_id: None,
                    user: None,
                    comment: None,
                    mode: RevDelMode::Catchup,
                    observed_at: Some(Utc::now()),
                    recovery_trigger: Some(request.trigger.clone()),
                    completion_tx: Some(completion_tx),
                })
                .await?;
            match tokio::time::timeout(std::time::Duration::from_secs(60), completion_rx).await {
                Ok(Ok(Ok(()))) => summary.hidden_count += 1,
                Ok(Ok(Err(reason))) => {
                    summary.failed_count += 1;
                    summary.unresolved_count += 1;
                    summary.unresolved_items.push(UnresolvedExposureItem {
                        title: title.clone(),
                        revid: revision.revid,
                        age_seconds: Some((Utc::now() - revision.timestamp).num_seconds()),
                        reason,
                        next_action: "review auth/API state and rerun catch-up".to_string(),
                    });
                }
                Ok(Err(_)) | Err(_) => {
                    summary.unresolved_count += 1;
                    summary.unresolved_items.push(UnresolvedExposureItem {
                        title: title.clone(),
                        revid: revision.revid,
                        age_seconds: Some((Utc::now() - revision.timestamp).num_seconds()),
                        reason: "worker-completion-timeout".to_string(),
                        next_action: "check worker status and rerun catch-up".to_string(),
                    });
                }
            }
        }
    }

    runtime.mark_recovery_completed(summary.clone()).await;
    Ok(summary)
}

pub fn validate_window(
    runtime: &AppRuntime,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
) -> Result<()> {
    if end < start {
        bail!("catch-up window end must be >= start");
    }
    let seconds = (end - start).num_seconds();
    if seconds > runtime.config.catchup.max_window_seconds {
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
        format!("coverage.requested_by={}", summary.requested_by),
        format!("coverage.pages_checked={}", summary.pages_checked),
        format!("coverage.edits_checked={}", summary.edits_checked),
        format!("coverage.hidden={}", summary.hidden_count),
        format!("coverage.already_hidden={}", summary.already_hidden_count),
        format!("coverage.skipped={}", summary.skipped_count),
        format!("coverage.failed={}", summary.failed_count),
        format!("coverage.unresolved={}", summary.unresolved_count),
    ];
    for item in &summary.unresolved_items {
        lines.push(format!(
            "coverage.unresolved_item title={} revid={} age_seconds={} reason={} next_action={}",
            item.title,
            item.revid,
            item.age_seconds
                .map(|value| value.to_string())
                .unwrap_or_else(|| "unknown".to_string()),
            item.reason,
            item.next_action
        ));
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
