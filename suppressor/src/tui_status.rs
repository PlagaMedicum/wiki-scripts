use std::path::PathBuf;

use chrono::Utc;

use crate::cache::SuppressionListCache;
use crate::config::RuntimePaths;
use crate::state::{
    CommandReportSurface, CompatibilityNotice, NightlySweepProgress, ProcessedRevidsState,
    RecheckFreshnessSnapshot, RuntimeStatus, compatibility_notice_for_unreadable_surface,
    load_json, load_text,
};

#[derive(Clone, Debug, Default)]
pub(crate) struct StatusSnapshot {
    pub daemon_pid: Option<i32>,
    pub daemon_running: bool,
    pub pid_file: PathBuf,
    pub last_event_id: Option<String>,
    pub source_title: Option<String>,
    pub listed_titles: usize,
    pub watched_titles: usize,
    pub processed_revids: usize,
    pub checkpoint_pages: usize,
    pub runtime_status: Option<RuntimeStatus>,
    pub command_report: Option<CommandReportSurface>,
    pub compatibility_notice: Option<CompatibilityNotice>,
    pub status_error: Option<String>,
}

fn compact_status_error(scope: &str, detail: impl std::fmt::Display) -> String {
    format!("st.err {scope}: {detail}")
}

fn stale_pid_notice(paths: &RuntimePaths, pid: i32) -> CompatibilityNotice {
    CompatibilityNotice {
        scope: "pid-file".to_string(),
        severity: "warning".to_string(),
        detected_at: Some(Utc::now()),
        previous_value: Some(paths.pid_file.display().to_string()),
        expected_value: Some(
            "running daemon pid plus a matching runtime_status.json updated by the active supervisor"
                .to_string(),
        ),
        summary: format!("pid file points to a non-running process ({pid})"),
        operator_action:
            "remove the stale pid marker or restart suppressor through the active supervisor so pid and runtime status are recreated together"
                .to_string(),
        approval_text: Some(
            "trust healthy status again only after the shown pid is running and the runtime_status.json surface is updating for that daemon"
                .to_string(),
        ),
        rollback_path: Some(
            "fall back to the last trusted launch path, remove the stale pid marker, and confirm the replacement daemon rewrites runtime_status.json"
                .to_string(),
        ),
        blocking: true,
    }
}

fn record_surface_notice(snapshot: &mut StatusSnapshot, notice: CompatibilityNotice) {
    if snapshot.compatibility_notice.is_none() {
        snapshot.compatibility_notice = Some(notice);
    }
}

pub(crate) fn collect_status(
    paths: &RuntimePaths,
    _managed_session: Option<&str>,
) -> StatusSnapshot {
    let mut snapshot = StatusSnapshot {
        pid_file: paths.pid_file.clone(),
        ..StatusSnapshot::default()
    };
    let mut checkpoint_progress = None;

    match load_text(&paths.pid_file) {
        Ok(Some(raw)) => match raw.parse::<i32>() {
            Ok(pid) if pid > 0 => {
                snapshot.daemon_pid = Some(pid);
                snapshot.daemon_running = PathBuf::from(format!("/proc/{pid}")).exists();
                if !snapshot.daemon_running {
                    snapshot.compatibility_notice = Some(stale_pid_notice(paths, pid));
                }
            }
            Ok(_) => snapshot.status_error = Some(compact_status_error("pid", "non-positive pid")),
            Err(error) => {
                snapshot.status_error = Some(compact_status_error("pid", error));
            }
        },
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(compact_status_error("pid", format!("{error:#}")))
        }
    }

    if let Ok(last_event_id) = load_text(&paths.last_event_id_file) {
        snapshot.last_event_id = last_event_id;
    }

    match load_json::<ProcessedRevidsState>(&paths.processed_revids_file) {
        Ok(Some(state)) => snapshot.processed_revids = state.revids.len(),
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(compact_status_error("processed", format!("{error:#}")))
        }
    }

    match load_json::<SuppressionListCache>(&paths.cache_file) {
        Ok(Some(cache)) => {
            snapshot.source_title = Some(cache.source_title);
            snapshot.listed_titles = cache.listed_titles_normalized.len();
            snapshot.watched_titles = cache.watched_titles_normalized.len();
        }
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(compact_status_error("cache", format!("{error:#}")))
        }
    }

    match load_json::<NightlySweepProgress>(&paths.nightly_sweep_progress_file) {
        Ok(Some(progress)) => {
            snapshot.checkpoint_pages = progress.pages.len();
            checkpoint_progress = Some(progress);
        }
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(compact_status_error("checkpoints", format!("{error:#}")))
        }
    }

    match load_json::<RuntimeStatus>(&paths.runtime_status_file) {
        Ok(Some(mut runtime_status)) => {
            populate_runtime_derivatives(
                &mut runtime_status,
                checkpoint_progress.as_ref(),
                snapshot.watched_titles,
            );
            snapshot.runtime_status = Some(runtime_status);
        }
        Ok(None) => {}
        Err(error) => {
            record_surface_notice(
                &mut snapshot,
                compatibility_notice_for_unreadable_surface(
                    "runtime-status",
                    &paths.runtime_status_file,
                    "readable runtime_status.json surface",
                    "replace or remove the unreadable runtime status file before trusting suppressor status",
                    "trust healthy status again only after the active daemon rewrites a readable runtime_status.json surface",
                    "restart the last trusted daemon workflow and verify that it writes a readable runtime_status.json surface",
                ),
            );
            snapshot.status_error = Some(compact_status_error("runtime", format!("{error:#}")))
        }
    }

    match load_json::<CommandReportSurface>(&paths.command_report_file()) {
        Ok(Some(command_report)) => snapshot.command_report = Some(command_report),
        Ok(None) => {}
        Err(error) => {
            record_surface_notice(
                &mut snapshot,
                compatibility_notice_for_unreadable_surface(
                    "command-report",
                    &paths.command_report_file(),
                    "bounded command-report surface",
                    "rerun the command or remove the unreadable command report file before trusting the last command summary",
                    "trust the last command summary again only after the current binary regenerates a readable bounded command report",
                    "remove the unreadable command report and rerun the last trusted command workflow",
                ),
            );
            snapshot.status_error =
                Some(compact_status_error("command-report", format!("{error:#}")))
        }
    }

    snapshot
}

fn populate_runtime_derivatives(
    status: &mut RuntimeStatus,
    checkpoint_progress: Option<&NightlySweepProgress>,
    watched_titles: usize,
) {
    let now = Utc::now();
    if let Some(observed_at) = status.realtime.last_event_observed_at {
        let lag_millis = (now - observed_at).num_milliseconds().max(0);
        status.realtime.current_lag_seconds = Some(lag_millis / 1000);
        status.realtime.current_lag_millis = Some(lag_millis);
        if status.realtime.current_lag_source.is_none() {
            status.realtime.current_lag_source = Some("stream".to_string());
        }
    }

    populate_live_outcome_derivatives(status);
    populate_recheck_freshness_derivatives(status, checkpoint_progress, watched_titles, now);

    if should_surface_live_queue_snapshot(&status.realtime)
        && let Some(outcome) = status.realtime.latest_outcome.as_ref()
    {
        status.realtime.current_task = Some(crate::state::CurrentTaskSnapshot {
            task_kind: "live-hide".to_string(),
            label: format!("hiding watched edit {}", outcome.title),
            progress_done: Some(0),
            progress_total: Some(1),
            window_start: None,
            window_end: None,
            started_at: outcome.queued_at.or(status.realtime.last_action_queued_at),
            expected_resume_at: None,
        });
    }

    if status.realtime.current_task.is_none() {
        let (task_kind, label, started_at) = if status.reconciliation.active {
            (
                "background".to_string(),
                status
                    .reconciliation
                    .mode
                    .clone()
                    .unwrap_or_else(|| "background verification".to_string()),
                status
                    .reconciliation
                    .last_started_at
                    .or(status.realtime.daemon_started_at),
            )
        } else if status.realtime.backoff_until.is_some() {
            (
                "backoff".to_string(),
                "waiting for backoff to expire".to_string(),
                status
                    .realtime
                    .last_recovery_completed_at
                    .or(status.realtime.daemon_started_at),
            )
        } else {
            (
                "idle".to_string(),
                "waiting for watched-page edits".to_string(),
                status.realtime.daemon_started_at,
            )
        };
        status.realtime.current_task = Some(crate::state::CurrentTaskSnapshot {
            task_kind,
            label,
            progress_done: Some(status.reconciliation.phase_completed)
                .filter(|_| status.reconciliation.active),
            progress_total: Some(
                status
                    .reconciliation
                    .phase_total
                    .max(status.reconciliation.total_titles),
            )
            .filter(|total| status.reconciliation.active && *total > 0),
            window_start: status.realtime.last_daytime_verification_window_start,
            window_end: status.realtime.last_daytime_verification_window_end,
            started_at,
            expected_resume_at: status.realtime.backoff_until,
        });
    }
}

fn populate_recheck_freshness_derivatives(
    status: &mut RuntimeStatus,
    checkpoint_progress: Option<&NightlySweepProgress>,
    watched_titles: usize,
    now: chrono::DateTime<Utc>,
) {
    let Some(progress) = checkpoint_progress else {
        return;
    };
    let freshness = derive_recheck_freshness(progress, status, watched_titles, now);
    let verification_failed = freshness
        .last_daytime_verification_result
        .as_deref()
        .is_some_and(|result| result.starts_with("failed:"))
        || freshness
            .last_nightly_full_recheck_result
            .as_deref()
            .is_some_and(|result| result.starts_with("failed:"));
    let stale_coverage = freshness.total_pages > 0 && freshness.pages_older_than_target > 0;
    status.reconciliation.freshness = Some(freshness.clone());

    if verification_failed || stale_coverage {
        let should_replace_issue =
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_none_or(|issue| {
                    matches!(
                        issue.source.as_str(),
                        "" | "last-24h-verification"
                            | "full-watched-set-recheck"
                            | "full-watched-set-freshness"
                    )
                });
        if should_replace_issue {
            status.realtime.latest_actionable_issue =
                if let Some(issue) = scheduled_verification_issue(&freshness, now) {
                    Some(issue)
                } else {
                    Some(full_recheck_freshness_issue(&freshness, now))
                };
        }
        if matches!(status.realtime.state.as_str(), "" | "unknown" | "healthy") {
            status.realtime.state = "unhealthy".to_string();
            status.realtime.last_state_changed_at = Some(now);
        }
    }
}

fn derive_recheck_freshness(
    progress: &NightlySweepProgress,
    status: &RuntimeStatus,
    watched_titles: usize,
    now: chrono::DateTime<Utc>,
) -> RecheckFreshnessSnapshot {
    let target_hours = 24u64;
    let target_age = chrono::TimeDelta::hours(target_hours as i64);
    let target_before = now - target_age;
    let checkpoint_pages = progress.pages.len();
    let total_pages = watched_titles.max(checkpoint_pages);
    let mut pages_older_than_target = watched_titles.saturating_sub(checkpoint_pages);
    let mut oldest_full_check_at = None;
    let mut oldest_full_check_title = None;
    let mut oldest_full_check_age_seconds = None;

    for (title, checkpoint) in &progress.pages {
        let is_stale = checkpoint
            .last_full_check_at
            .is_none_or(|at| at < target_before);
        if is_stale {
            pages_older_than_target += 1;
        }
        match (oldest_full_check_at, checkpoint.last_full_check_at) {
            (None, Some(at)) => {
                oldest_full_check_at = Some(at);
                oldest_full_check_title = Some(title.clone());
                oldest_full_check_age_seconds = Some((now - at).num_seconds().max(0));
            }
            (Some(previous), Some(at)) if at < previous => {
                oldest_full_check_at = Some(at);
                oldest_full_check_title = Some(title.clone());
                oldest_full_check_age_seconds = Some((now - at).num_seconds().max(0));
            }
            (None, None) if oldest_full_check_title.is_none() => {
                oldest_full_check_title = Some(title.clone());
            }
            _ => {}
        }
    }

    RecheckFreshnessSnapshot {
        target_hours,
        total_pages,
        pages_older_than_target,
        oldest_full_check_at,
        oldest_full_check_title,
        oldest_full_check_age_seconds,
        last_daytime_verification_result: status
            .realtime
            .last_daytime_verification_result
            .clone()
            .or_else(|| {
                status
                    .realtime
                    .last_daytime_verification_at
                    .map(|_| "completed".to_string())
            }),
        last_nightly_full_recheck_result: status
            .realtime
            .last_nightly_full_recheck_result
            .clone()
            .or_else(|| {
                status
                    .realtime
                    .last_nightly_full_recheck_at
                    .map(|_| "completed".to_string())
            }),
        computed_at: Some(now),
    }
}

fn scheduled_verification_issue(
    freshness: &RecheckFreshnessSnapshot,
    detected_at: chrono::DateTime<Utc>,
) -> Option<crate::state::ActionableIssueSnapshot> {
    let daytime = freshness
        .last_daytime_verification_result
        .as_deref()
        .filter(|result| result.starts_with("failed:"))
        .map(|result| crate::state::ActionableIssueSnapshot {
            source: "last-24h-verification".to_string(),
            severity: "error".to_string(),
            summary: format!("Last 24 hours verification {result}"),
            next_action: "inspect the latest verification log or rerun Last 24 hours verification"
                .to_string(),
            detected_at: Some(detected_at),
        });
    let nightly = freshness
        .last_nightly_full_recheck_result
        .as_deref()
        .filter(|result| result.starts_with("failed:"))
        .map(|result| crate::state::ActionableIssueSnapshot {
            source: "full-watched-set-recheck".to_string(),
            severity: "error".to_string(),
            summary: format!("full watched-set recheck {result}"),
            next_action: "inspect the latest recheck log or rerun the full watched-set recheck"
                .to_string(),
            detected_at: Some(detected_at),
        });
    nightly.or(daytime)
}

fn full_recheck_freshness_issue(
    freshness: &RecheckFreshnessSnapshot,
    detected_at: chrono::DateTime<Utc>,
) -> crate::state::ActionableIssueSnapshot {
    crate::state::ActionableIssueSnapshot {
        source: "full-watched-set-freshness".to_string(),
        severity: "warning".to_string(),
        summary: format!(
            "full watched-set coverage is stale for {}/{} pages",
            freshness.pages_older_than_target, freshness.total_pages
        ),
        next_action:
            "run the full watched-set recheck and confirm stale-page count returns to zero"
                .to_string(),
        detected_at: Some(detected_at),
    }
}

fn populate_live_outcome_derivatives(status: &mut RuntimeStatus) {
    let Some(outcome) = status.realtime.latest_outcome.as_ref() else {
        return;
    };
    if outcome.mode != "live" {
        return;
    }

    if status.realtime.last_action_queued_at.is_none() {
        status.realtime.last_action_queued_at = outcome.queued_at;
    }
    if status.realtime.last_action_completed_at.is_none() {
        status.realtime.last_action_completed_at = outcome.completed_at;
    }

    if let Some(observed_at) = outcome.observed_at {
        if status.realtime.last_matching_edit_at.is_none() {
            status.realtime.last_matching_edit_at = Some(observed_at);
        }
        if status.realtime.last_matching_title.is_none() && !outcome.title.is_empty() {
            status.realtime.last_matching_title = Some(outcome.title.clone());
        }
        if status.realtime.last_matching_revid.is_none() && outcome.revid > 0 {
            status.realtime.last_matching_revid = Some(outcome.revid);
        }
        if status.realtime.last_matching_revid_url.is_none() {
            status.realtime.last_matching_revid_url = outcome.revision_url.clone();
        }
    }

    if matches!(outcome.outcome.as_str(), "hidden" | "already-hidden") {
        if status.realtime.last_successful_hide_at.is_none() {
            status.realtime.last_successful_hide_at = outcome.completed_at;
        }
        if status.realtime.last_successful_hide_title.is_none() && !outcome.title.is_empty() {
            status.realtime.last_successful_hide_title = Some(outcome.title.clone());
        }
        if status.realtime.last_successful_hide_revid.is_none() && outcome.revid > 0 {
            status.realtime.last_successful_hide_revid = Some(outcome.revid);
        }
        if status.realtime.last_successful_hide_url.is_none() {
            status.realtime.last_successful_hide_url = outcome.revision_url.clone();
        }
    }
}

fn should_surface_live_queue_snapshot(status: &crate::state::RealtimeRuntimeStatus) -> bool {
    matches!(
        status.latest_outcome.as_ref(),
        Some(outcome)
            if outcome.mode == "live"
                && outcome.outcome == "queued"
                && !matches!(
                    status.current_task.as_ref(),
                    Some(task) if task.task_kind == "live-hide"
                )
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use chrono::Utc;
    use tempfile::tempdir;

    use super::*;
    use crate::config::{AppConfig, RuntimePaths};
    use crate::state::{
        CommandReportCounts, CommandReportSurface, CommandReportWindow, CurrentTaskSnapshot,
        PageCheckpoint, RealtimeRuntimeStatus, ReconciliationRuntimeStatus, RuntimeStatus,
        SuppressionOutcomeSnapshot, save_json_atomic, save_text_atomic,
    };

    #[test]
    fn collect_status_reads_supervisor_files() {
        let temp = tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);

        save_text_atomic(&paths.pid_file, &std::process::id().to_string()).unwrap();
        save_text_atomic(&paths.last_event_id_file, "evt-1").unwrap();
        save_json_atomic(
            &paths.processed_revids_file,
            &ProcessedRevidsState {
                capacity: 10,
                revids: vec![1, 2, 3],
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.cache_file,
            &SuppressionListCache {
                source_title: "Source".to_string(),
                source_pageid: Some(1),
                source_lastrevid: Some(2),
                source_last_timestamp: Some(Utc::now()),
                fetched_at: Utc::now(),
                listed_titles_normalized: vec!["a".to_string(), "b".to_string()],
                watched_titles_normalized: vec!["a".to_string(), "b".to_string(), "c".to_string()],
                redirect_map: BTreeMap::new(),
                titles_hash_sha256: "hash".to_string(),
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.nightly_sweep_progress_file,
            &NightlySweepProgress {
                pages: BTreeMap::from([("Page".to_string(), PageCheckpoint::default())]),
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &RuntimeStatus {
                daemon_state: "running".to_string(),
                dry_run: false,
                last_notice: Some("ok".to_string()),
                last_notice_at: Some(Utc::now()),
                resource_economy: None,
                compatibility_notice: None,
                realtime: crate::state::RealtimeRuntimeStatus::default(),
                reconciliation: ReconciliationRuntimeStatus::default(),
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.command_report_file(),
            &CommandReportSurface {
                command: "coverage-report".to_string(),
                counts: CommandReportCounts {
                    checked: 4,
                    hidden: 1,
                    unresolved: 1,
                    ..CommandReportCounts::default()
                },
                window: CommandReportWindow {
                    start: Some(Utc::now()),
                    end: Some(Utc::now()),
                },
                ..CommandReportSurface::default()
            },
        )
        .unwrap();

        let snapshot = collect_status(&paths, Some("daemon"));

        assert!(snapshot.daemon_running);
        assert_eq!(snapshot.last_event_id.as_deref(), Some("evt-1"));
        assert_eq!(snapshot.processed_revids, 3);
        assert_eq!(snapshot.listed_titles, 2);
        assert_eq!(snapshot.watched_titles, 3);
        assert_eq!(snapshot.checkpoint_pages, 1);
        assert_eq!(
            snapshot
                .runtime_status
                .as_ref()
                .map(|status| status.daemon_state.as_str()),
            Some("running")
        );
        assert_eq!(
            snapshot
                .command_report
                .as_ref()
                .map(|report| report.command.as_str()),
            Some("coverage-report")
        );
    }

    #[test]
    fn collect_status_compacts_pid_errors() {
        let temp = tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);

        save_text_atomic(&paths.pid_file, "0").unwrap();

        let snapshot = collect_status(&paths, None);

        assert_eq!(
            snapshot.status_error.as_deref(),
            Some("st.err pid: non-positive pid")
        );
    }

    #[test]
    fn collect_status_emits_stale_pid_notice() {
        let temp = tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);

        save_text_atomic(&paths.pid_file, "999999").unwrap();

        let snapshot = collect_status(&paths, None);

        assert_eq!(snapshot.daemon_pid, Some(999999));
        assert!(!snapshot.daemon_running);
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.scope.as_str()),
            Some("pid-file")
        );
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.severity.as_str()),
            Some("warning")
        );
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.blocking),
            Some(true)
        );
        assert!(
            snapshot
                .compatibility_notice
                .as_ref()
                .and_then(|notice| notice.approval_text.as_deref())
                .is_some()
        );
        assert!(
            snapshot
                .compatibility_notice
                .as_ref()
                .and_then(|notice| notice.rollback_path.as_deref())
                .is_some()
        );
    }

    #[test]
    fn collect_status_maps_unreadable_runtime_status_to_migration_notice() {
        let temp = tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);
        std::fs::create_dir_all(&paths.state_dir).unwrap();
        std::fs::write(&paths.runtime_status_file, "{").unwrap();

        let snapshot = collect_status(&paths, None);

        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.scope.as_str()),
            Some("runtime-status")
        );
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.severity.as_str()),
            Some("migration-required")
        );
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.blocking),
            Some(true)
        );
        assert!(
            snapshot
                .compatibility_notice
                .as_ref()
                .and_then(|notice| notice.approval_text.as_deref())
                .is_some()
        );
        assert!(
            snapshot
                .compatibility_notice
                .as_ref()
                .and_then(|notice| notice.rollback_path.as_deref())
                .is_some()
        );
        assert!(
            snapshot
                .status_error
                .as_deref()
                .is_some_and(|value| value.contains("st.err runtime"))
        );
    }

    #[test]
    fn collect_status_maps_unreadable_command_report_to_migration_notice() {
        let temp = tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);
        std::fs::create_dir_all(&paths.state_dir).unwrap();
        std::fs::write(paths.command_report_file(), "{").unwrap();

        let snapshot = collect_status(&paths, None);

        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.scope.as_str()),
            Some("command-report")
        );
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.severity.as_str()),
            Some("migration-required")
        );
        assert_eq!(
            snapshot
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.blocking),
            Some(true)
        );
        assert!(
            snapshot
                .compatibility_notice
                .as_ref()
                .and_then(|notice| notice.approval_text.as_deref())
                .is_some()
        );
        assert!(
            snapshot
                .compatibility_notice
                .as_ref()
                .and_then(|notice| notice.rollback_path.as_deref())
                .is_some()
        );
        assert!(
            snapshot
                .status_error
                .as_deref()
                .is_some_and(|value| value.contains("st.err command-report"))
        );
    }

    #[test]
    fn populate_runtime_derivatives_restores_live_queue_snapshot() {
        let observed_at = Utc::now();
        let queued_at = observed_at + chrono::TimeDelta::milliseconds(250);
        let mut status = RuntimeStatus {
            realtime: RealtimeRuntimeStatus {
                current_task: Some(CurrentTaskSnapshot {
                    task_kind: "idle".to_string(),
                    label: "waiting for watched-page edits".to_string(),
                    ..CurrentTaskSnapshot::default()
                }),
                latest_outcome: Some(SuppressionOutcomeSnapshot {
                    title: "Sensitive".to_string(),
                    revid: 77,
                    revision_url: Some("https://be.wikipedia.org/wiki/Special:Diff/77".to_string()),
                    outcome: "queued".to_string(),
                    mode: "live".to_string(),
                    source_label: "live hiding".to_string(),
                    observed_at: Some(observed_at),
                    queued_at: Some(queued_at),
                    ..SuppressionOutcomeSnapshot::default()
                }),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };

        populate_runtime_derivatives(&mut status, None, 0);

        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("live-hide")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.label.as_str()),
            Some("hiding watched edit Sensitive")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .and_then(|task| task.started_at),
            Some(queued_at)
        );
        assert_eq!(status.realtime.last_action_queued_at, Some(queued_at));
        assert_eq!(status.realtime.last_matching_edit_at, Some(observed_at));
        assert_eq!(
            status.realtime.last_matching_title.as_deref(),
            Some("Sensitive")
        );
        assert_eq!(status.realtime.last_matching_revid, Some(77));
        assert_eq!(
            status.realtime.last_matching_revid_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/77")
        );
    }

    #[test]
    fn populate_runtime_derivatives_restores_last_successful_hide_snapshot() {
        let observed_at = Utc::now();
        let completed_at = observed_at + chrono::TimeDelta::milliseconds(800);
        let mut status = RuntimeStatus {
            realtime: RealtimeRuntimeStatus {
                latest_outcome: Some(SuppressionOutcomeSnapshot {
                    title: "Sensitive".to_string(),
                    revid: 88,
                    revision_url: Some("https://be.wikipedia.org/wiki/Special:Diff/88".to_string()),
                    outcome: "hidden".to_string(),
                    mode: "live".to_string(),
                    source_label: "live hiding".to_string(),
                    observed_at: Some(observed_at),
                    completed_at: Some(completed_at),
                    ..SuppressionOutcomeSnapshot::default()
                }),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };

        populate_runtime_derivatives(&mut status, None, 0);

        assert_eq!(status.realtime.last_action_completed_at, Some(completed_at));
        assert_eq!(status.realtime.last_successful_hide_at, Some(completed_at));
        assert_eq!(
            status.realtime.last_successful_hide_title.as_deref(),
            Some("Sensitive")
        );
        assert_eq!(status.realtime.last_successful_hide_revid, Some(88));
        assert_eq!(
            status.realtime.last_successful_hide_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/88")
        );
    }

    #[test]
    fn populate_runtime_derivatives_surfaces_backoff_as_current_work() {
        let backoff_until = Utc::now() + chrono::TimeDelta::seconds(45);
        let completed_at = Utc::now();
        let mut status = RuntimeStatus {
            realtime: RealtimeRuntimeStatus {
                backoff_until: Some(backoff_until),
                last_recovery_completed_at: Some(completed_at),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };

        populate_runtime_derivatives(&mut status, None, 0);

        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("backoff")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.label.as_str()),
            Some("waiting for backoff to expire")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .and_then(|task| task.expected_resume_at),
            Some(backoff_until)
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .and_then(|task| task.started_at),
            Some(completed_at)
        );
    }

    #[test]
    fn populate_runtime_derivatives_derives_checkpoint_freshness_issue() {
        let now = Utc::now();
        let stale_checkpoint = NightlySweepProgress {
            pages: BTreeMap::from([(
                "Old page".to_string(),
                PageCheckpoint {
                    last_full_check_at: Some(now - chrono::TimeDelta::days(2)),
                    ..PageCheckpoint::default()
                },
            )]),
        };
        let mut status = RuntimeStatus {
            realtime: RealtimeRuntimeStatus {
                state: "healthy".to_string(),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };

        populate_runtime_derivatives(&mut status, Some(&stale_checkpoint), 2);

        let freshness = status.reconciliation.freshness.as_ref().unwrap();
        assert_eq!(freshness.total_pages, 2);
        assert_eq!(freshness.pages_older_than_target, 2);
        assert_eq!(
            freshness.oldest_full_check_title.as_deref(),
            Some("Old page")
        );
        assert_eq!(status.realtime.state, "unhealthy");
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("full-watched-set-freshness")
        );
    }

    #[test]
    fn populate_runtime_derivatives_restores_failed_scheduled_verification_issue() {
        let now = Utc::now();
        let checkpoint = NightlySweepProgress {
            pages: BTreeMap::from([(
                "Fresh page".to_string(),
                PageCheckpoint {
                    last_full_check_at: Some(now),
                    ..PageCheckpoint::default()
                },
            )]),
        };
        let mut status = RuntimeStatus {
            realtime: RealtimeRuntimeStatus {
                state: "healthy".to_string(),
                last_daytime_verification_at: Some(now),
                last_daytime_verification_result: Some("failed: non-json-response".to_string()),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };

        populate_runtime_derivatives(&mut status, Some(&checkpoint), 1);

        assert_eq!(status.realtime.state, "unhealthy");
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("last-24h-verification")
        );
        assert!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_some_and(|issue| issue.summary.contains("Last 24 hours verification failed"))
        );
    }
}
