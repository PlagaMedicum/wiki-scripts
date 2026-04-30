use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File};
use std::io::Write;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize, de::DeserializeOwned};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ProcessedRevidsState {
    pub capacity: usize,
    pub revids: Vec<u64>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct NightlySweepProgress {
    pub pages: BTreeMap<String, PageCheckpoint>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct RuntimeStatus {
    pub daemon_state: String,
    pub dry_run: bool,
    pub last_notice: Option<String>,
    pub last_notice_at: Option<DateTime<Utc>>,
    pub resource_economy: Option<ResourceEconomySnapshot>,
    pub compatibility_notice: Option<CompatibilityNotice>,
    pub realtime: RealtimeRuntimeStatus,
    pub reconciliation: ReconciliationRuntimeStatus,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CompatibilityNotice {
    pub scope: String,
    pub severity: String,
    pub detected_at: Option<DateTime<Utc>>,
    pub previous_value: Option<String>,
    pub expected_value: Option<String>,
    pub summary: String,
    pub operator_action: String,
    pub blocking: bool,
}

pub fn compatibility_notice_for_unreadable_surface(
    scope: &str,
    path: &Path,
    expected_value: &str,
    operator_action: &str,
) -> CompatibilityNotice {
    CompatibilityNotice {
        scope: scope.to_string(),
        severity: "migration-required".to_string(),
        detected_at: Some(Utc::now()),
        previous_value: Some(path.display().to_string()),
        expected_value: Some(expected_value.to_string()),
        summary: format!("existing {scope} surface could not be parsed safely"),
        operator_action: operator_action.to_string(),
        blocking: true,
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct RealtimeRuntimeStatus {
    pub state: String,
    pub last_state_changed_at: Option<DateTime<Utc>>,
    pub stale_threshold_seconds: u64,
    pub stream_read_timeout_seconds: u64,
    pub last_stream_opened_at: Option<DateTime<Utc>>,
    pub last_event_observed_at: Option<DateTime<Utc>>,
    pub last_matching_edit_at: Option<DateTime<Utc>>,
    pub last_matching_title: Option<String>,
    pub last_matching_revid: Option<u64>,
    pub last_matching_revid_url: Option<String>,
    pub last_action_queued_at: Option<DateTime<Utc>>,
    pub last_action_completed_at: Option<DateTime<Utc>>,
    pub last_successful_hide_at: Option<DateTime<Utc>>,
    pub last_successful_hide_title: Option<String>,
    pub last_successful_hide_revid: Option<u64>,
    pub last_successful_hide_url: Option<String>,
    pub last_event_id: Option<String>,
    pub current_lag_seconds: Option<i64>,
    pub current_lag_millis: Option<i64>,
    pub current_lag_source: Option<String>,
    pub queue_depth: usize,
    pub daemon_started_at: Option<DateTime<Utc>>,
    pub current_task: Option<CurrentTaskSnapshot>,
    pub last_recovery_trigger: Option<String>,
    pub last_recovery_started_at: Option<DateTime<Utc>>,
    pub last_recovery_completed_at: Option<DateTime<Utc>>,
    pub last_reconnect_reason: Option<String>,
    pub last_offline_started_at: Option<DateTime<Utc>>,
    pub last_offline_recovered_at: Option<DateTime<Utc>>,
    pub last_freshness_probe_at: Option<DateTime<Utc>>,
    pub last_freshness_probe_source: Option<String>,
    pub catchup_active: bool,
    pub backoff_until: Option<DateTime<Utc>>,
    pub latest_error_code: Option<String>,
    pub latest_error: Option<ApiFailureSnapshot>,
    pub latest_actionable_issue: Option<ActionableIssueSnapshot>,
    pub latest_notice: Option<String>,
    pub latest_outcome: Option<SuppressionOutcomeSnapshot>,
    pub latest_recovery_warnings: Vec<WarningSummary>,
    pub latest_recovery_summary: Option<CoverageSummary>,
    pub last_source_refresh: Option<SourceListRefresh>,
    pub last_daytime_verification_at: Option<DateTime<Utc>>,
    pub last_daytime_verification_window_start: Option<DateTime<Utc>>,
    pub last_daytime_verification_window_end: Option<DateTime<Utc>>,
    pub last_nightly_full_recheck_at: Option<DateTime<Utc>>,
}

impl Default for RealtimeRuntimeStatus {
    fn default() -> Self {
        Self {
            state: "unknown".to_string(),
            last_state_changed_at: None,
            stale_threshold_seconds: 10,
            stream_read_timeout_seconds: 10,
            last_stream_opened_at: None,
            last_event_observed_at: None,
            last_matching_edit_at: None,
            last_matching_title: None,
            last_matching_revid: None,
            last_matching_revid_url: None,
            last_action_queued_at: None,
            last_action_completed_at: None,
            last_successful_hide_at: None,
            last_successful_hide_title: None,
            last_successful_hide_revid: None,
            last_successful_hide_url: None,
            last_event_id: None,
            current_lag_seconds: None,
            current_lag_millis: None,
            current_lag_source: None,
            queue_depth: 0,
            daemon_started_at: None,
            current_task: None,
            last_recovery_trigger: None,
            last_recovery_started_at: None,
            last_recovery_completed_at: None,
            last_reconnect_reason: None,
            last_offline_started_at: None,
            last_offline_recovered_at: None,
            last_freshness_probe_at: None,
            last_freshness_probe_source: None,
            catchup_active: false,
            backoff_until: None,
            latest_error_code: None,
            latest_error: None,
            latest_actionable_issue: None,
            latest_notice: None,
            latest_outcome: None,
            latest_recovery_warnings: Vec::new(),
            latest_recovery_summary: None,
            last_source_refresh: None,
            last_daytime_verification_at: None,
            last_daytime_verification_window_start: None,
            last_daytime_verification_window_end: None,
            last_nightly_full_recheck_at: None,
        }
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CurrentTaskSnapshot {
    pub task_kind: String,
    pub label: String,
    pub progress_done: Option<usize>,
    pub progress_total: Option<usize>,
    pub window_start: Option<DateTime<Utc>>,
    pub window_end: Option<DateTime<Utc>>,
    pub started_at: Option<DateTime<Utc>>,
    pub expected_resume_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ActionableIssueSnapshot {
    pub severity: String,
    pub summary: String,
    pub next_action: String,
    pub detected_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ApiFailureSnapshot {
    pub class: String,
    pub api_code: Option<String>,
    pub http_status: Option<u16>,
    pub content_type: Option<String>,
    pub retryable: bool,
    pub retry_after_seconds: Option<u64>,
    pub operation: String,
    pub sample_title: Option<String>,
    pub sample_revid: Option<u64>,
    pub message: String,
    pub occurred_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct SourceListRefresh {
    pub trigger_title: String,
    pub trigger_revid: Option<u64>,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub old_source_revid: Option<u64>,
    pub new_source_revid: Option<u64>,
    pub new_titles_count: usize,
    pub removed_titles_count: usize,
    pub redirects_reused: bool,
    pub catchup_triggered: bool,
    pub catchup_title_scope: Option<String>,
    pub deferred_until: Option<DateTime<Utc>>,
    pub outcome: String,
    pub error: Option<ApiFailureSnapshot>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ResourceEconomySnapshot {
    pub queue_depth_max_recent: usize,
    pub api_concurrency_max_recent: usize,
    pub state_bytes_recent: u64,
    pub coalesced_warning_count_recent: usize,
    pub latest_measurement_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct SuppressionOutcomeSnapshot {
    pub title: String,
    pub revid: u64,
    pub revision_url: Option<String>,
    pub outcome: String,
    pub reason_code: Option<String>,
    pub mode: String,
    pub source_label: String,
    pub observed_at: Option<DateTime<Utc>>,
    pub queued_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub attempt_count: u32,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CoverageSummary {
    pub scope_label: Option<String>,
    pub started_at: Option<DateTime<Utc>>,
    pub ended_at: Option<DateTime<Utc>>,
    pub requested_by: String,
    pub pages_checked: usize,
    pub edits_checked: usize,
    pub hidden_count: usize,
    pub already_hidden_count: usize,
    pub skipped_count: usize,
    pub failed_count: usize,
    pub unresolved_count: usize,
    pub unresolved_items: Vec<UnresolvedExposureItem>,
    pub stopped_early_reason: Option<String>,
    pub backoff_until: Option<DateTime<Utc>>,
    pub warning_summaries: Vec<WarningSummary>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct UnresolvedExposureItem {
    pub title: String,
    pub revid: u64,
    pub revision_url: Option<String>,
    pub age_seconds: Option<i64>,
    pub reason: String,
    pub next_action: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct WarningSummary {
    pub class: String,
    pub api_code: Option<String>,
    pub http_status: Option<u16>,
    pub content_type: Option<String>,
    pub retryable: bool,
    pub retry_after_seconds: Option<u64>,
    pub operation: String,
    pub count: usize,
    pub sample_titles: Vec<String>,
    pub message: String,
    pub stopped_early: bool,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct BenchmarkRun {
    pub test_page_title: String,
    pub run_id: String,
    pub edit_count: usize,
    pub bot_marked: bool,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub smoke_only: bool,
    pub unresolved_items: Vec<UnresolvedExposureItem>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CommandReportSurface {
    pub command: String,
    pub generated_at: Option<DateTime<Utc>>,
    pub report_only: bool,
    pub scope_label: Option<String>,
    pub window: CommandReportWindow,
    pub counts: CommandReportCounts,
    #[serde(default, alias = "unresolved")]
    pub unresolved_items: Vec<UnresolvedExposureItem>,
    pub stopped_early_reason: Option<String>,
    pub backoff_until: Option<DateTime<Utc>>,
    pub next_action: Option<String>,
    pub compatibility_notice: Option<CompatibilityNotice>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CommandReportWindow {
    pub start: Option<DateTime<Utc>>,
    pub end: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CommandReportCounts {
    #[serde(default, alias = "checked")]
    pub checked: usize,
    #[serde(default, alias = "hidden")]
    pub hidden: usize,
    #[serde(default, alias = "already_hidden")]
    pub already_hidden: usize,
    #[serde(default, alias = "skipped")]
    pub skipped: usize,
    #[serde(default, alias = "failed")]
    pub failed: usize,
    #[serde(default, alias = "unresolved")]
    pub unresolved: usize,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ReconciliationRuntimeStatus {
    pub active: bool,
    pub mode: Option<String>,
    pub phase: Option<String>,
    pub queued_mode: Option<String>,
    pub total_titles: usize,
    pub completed_titles: usize,
    pub phase_total: usize,
    pub phase_completed: usize,
    pub current_title: Option<String>,
    pub last_started_at: Option<DateTime<Utc>>,
    pub last_completed_at: Option<DateTime<Utc>>,
    pub last_result: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PageCheckpoint {
    pub last_full_check_at: Option<DateTime<Utc>>,
    pub last_reconciled_at: Option<DateTime<Utc>>,
    pub last_reconciled_revision_timestamp: Option<DateTime<Utc>>,
    pub last_reconciled_revid: Option<u64>,
}

impl ProcessedRevidsState {
    pub fn contains(&self, revid: u64) -> bool {
        self.revids.contains(&revid)
    }

    pub fn insert(&mut self, revid: u64) {
        if self.contains(revid) {
            return;
        }
        let mut queue = VecDeque::from(self.revids.clone());
        queue.push_back(revid);
        while self.capacity > 0 && queue.len() > self.capacity {
            let _ = queue.pop_front();
        }
        self.revids = queue.into_iter().collect();
    }
}

pub fn load_json<T: DeserializeOwned>(path: &Path) -> Result<Option<T>> {
    if !path.exists() {
        return Ok(None);
    }
    let raw =
        fs::read_to_string(path).with_context(|| format!("Failed to read {}", path.display()))?;
    let value = serde_json::from_str(&raw)
        .with_context(|| format!("Failed to parse {}", path.display()))?;
    Ok(Some(value))
}

pub fn save_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let raw = serde_json::to_vec_pretty(value).context("Failed to serialize JSON state")?;
    save_bytes_atomic(path, &raw)
}

pub fn load_text(path: &Path) -> Result<Option<String>> {
    if !path.exists() {
        return Ok(None);
    }
    let raw =
        fs::read_to_string(path).with_context(|| format!("Failed to read {}", path.display()))?;
    Ok(Some(raw.trim().to_string()))
}

pub fn save_text_atomic(path: &Path, value: &str) -> Result<()> {
    save_bytes_atomic(path, value.as_bytes())
}

fn save_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create {}", parent.display()))?;
    }
    let tmp_path = path.with_extension("tmp");
    let mut file = File::create(&tmp_path)
        .with_context(|| format!("Failed to create {}", tmp_path.display()))?;
    file.write_all(bytes)
        .with_context(|| format!("Failed to write {}", tmp_path.display()))?;
    file.sync_all()
        .with_context(|| format!("Failed to flush {}", tmp_path.display()))?;
    fs::rename(&tmp_path, path)
        .with_context(|| format!("Failed to move {} into place", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;

    #[test]
    fn processed_revids_respects_capacity() {
        let mut state = ProcessedRevidsState {
            capacity: 3,
            revids: vec![],
        };
        state.insert(1);
        state.insert(2);
        state.insert(3);
        state.insert(4);
        assert_eq!(state.revids, vec![2, 3, 4]);
    }

    #[test]
    fn saves_and_loads_json_atomically() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("processed.json");
        let state = ProcessedRevidsState {
            capacity: 2,
            revids: vec![10, 20],
        };
        save_json_atomic(&path, &state).unwrap();
        let loaded: ProcessedRevidsState = load_json(&path).unwrap().unwrap();
        assert_eq!(loaded.revids, vec![10, 20]);
    }

    #[test]
    fn runtime_status_loads_with_missing_new_fields() {
        let raw = r#"{
          "daemon_state": "running",
          "dry_run": false,
          "last_notice": "received manual nightly reconciliation signal",
          "reconciliation": {
            "active": true,
            "mode": "nightly",
            "queued_mode": null,
            "total_titles": 1425,
            "completed_titles": 0,
            "current_title": null,
            "last_started_at": "2026-04-08T14:02:59Z",
            "last_completed_at": null,
            "last_result": null
          }
        }"#;

        let loaded: RuntimeStatus = serde_json::from_str(raw).unwrap();
        assert_eq!(loaded.daemon_state, "running");
        assert!(loaded.reconciliation.active);
        assert_eq!(loaded.reconciliation.mode.as_deref(), Some("nightly"));
        assert_eq!(loaded.reconciliation.total_titles, 1425);
        assert_eq!(loaded.reconciliation.completed_titles, 0);
        assert_eq!(loaded.reconciliation.phase_total, 0);
        assert_eq!(loaded.reconciliation.phase_completed, 0);
        assert_eq!(loaded.reconciliation.phase, None);
        assert_eq!(loaded.realtime.state, "unknown");
        assert_eq!(loaded.realtime.stale_threshold_seconds, 10);
        assert!(loaded.realtime.latest_recovery_warnings.is_empty());
        assert!(loaded.realtime.backoff_until.is_none());
    }

    #[test]
    fn runtime_status_round_trips_realtime_fields() {
        let status = RuntimeStatus {
            daemon_state: "running".to_string(),
            dry_run: false,
            last_notice: Some("ok".to_string()),
            last_notice_at: Some(Utc::now()),
            resource_economy: None,
            compatibility_notice: None,
            realtime: RealtimeRuntimeStatus {
                state: "healthy".to_string(),
                queue_depth: 3,
                latest_notice: Some("hidden revid 42".to_string()),
                latest_outcome: Some(SuppressionOutcomeSnapshot {
                    title: "Title".to_string(),
                    revid: 42,
                    revision_url: Some("https://be.wikipedia.org/wiki/Special:Diff/42".to_string()),
                    outcome: "hidden".to_string(),
                    mode: "live".to_string(),
                    source_label: "live hiding".to_string(),
                    ..SuppressionOutcomeSnapshot::default()
                }),
                ..RealtimeRuntimeStatus::default()
            },
            reconciliation: ReconciliationRuntimeStatus::default(),
        };

        let raw = serde_json::to_string(&status).unwrap();
        let loaded: RuntimeStatus = serde_json::from_str(&raw).unwrap();

        assert_eq!(loaded.realtime.state, "healthy");
        assert_eq!(loaded.realtime.queue_depth, 3);
        let latest_outcome = loaded.realtime.latest_outcome.unwrap();
        assert_eq!(latest_outcome.outcome, "hidden");
        assert_eq!(
            latest_outcome.revision_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/42")
        );
        assert_eq!(latest_outcome.source_label, "live hiding");
    }

    #[test]
    fn runtime_status_round_trips_recovery_error_and_resource_fields() {
        let status = RuntimeStatus {
            daemon_state: "running".to_string(),
            dry_run: false,
            last_notice: Some("source refresh catchup-started".to_string()),
            last_notice_at: Some(Utc::now()),
            resource_economy: Some(ResourceEconomySnapshot {
                queue_depth_max_recent: 3,
                coalesced_warning_count_recent: 42,
                latest_measurement_at: Some(Utc::now()),
                ..ResourceEconomySnapshot::default()
            }),
            compatibility_notice: Some(CompatibilityNotice {
                scope: "command-report".to_string(),
                severity: "warning".to_string(),
                summary: "legacy report shape detected".to_string(),
                operator_action: "trust the new report output".to_string(),
                ..CompatibilityNotice::default()
            }),
            realtime: RealtimeRuntimeStatus {
                latest_error: Some(ApiFailureSnapshot {
                    class: "api-json-error".to_string(),
                    api_code: Some("badtimestamp".to_string()),
                    http_status: Some(200),
                    retryable: false,
                    retry_after_seconds: Some(30),
                    operation: "fetch-revisions".to_string(),
                    sample_title: Some("Title".to_string()),
                    message: "invalid timestamp".to_string(),
                    occurred_at: Some(Utc::now()),
                    ..ApiFailureSnapshot::default()
                }),
                last_source_refresh: Some(SourceListRefresh {
                    trigger_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
                    new_titles_count: 2,
                    catchup_triggered: true,
                    catchup_title_scope: Some("new-titles".to_string()),
                    outcome: "catchup-started".to_string(),
                    ..SourceListRefresh::default()
                }),
                latest_recovery_summary: Some(CoverageSummary {
                    stopped_early_reason: Some("rate-limited".to_string()),
                    warning_summaries: vec![WarningSummary {
                        class: "api-json-error".to_string(),
                        api_code: Some("badtimestamp".to_string()),
                        operation: "fetch-revisions".to_string(),
                        retry_after_seconds: Some(30),
                        count: 1427,
                        sample_titles: vec!["Title".to_string()],
                        stopped_early: true,
                        ..WarningSummary::default()
                    }],
                    ..CoverageSummary::default()
                }),
                latest_recovery_warnings: vec![WarningSummary {
                    class: "api-json-error".to_string(),
                    api_code: Some("badtimestamp".to_string()),
                    operation: "fetch-revisions".to_string(),
                    retry_after_seconds: Some(30),
                    count: 1427,
                    sample_titles: vec!["Title".to_string()],
                    stopped_early: true,
                    ..WarningSummary::default()
                }],
                ..RealtimeRuntimeStatus::default()
            },
            reconciliation: ReconciliationRuntimeStatus::default(),
        };

        let raw = serde_json::to_string(&status).unwrap();
        let loaded: RuntimeStatus = serde_json::from_str(&raw).unwrap();

        assert_eq!(
            loaded
                .realtime
                .latest_error
                .as_ref()
                .and_then(|error| error.api_code.as_deref()),
            Some("badtimestamp")
        );
        assert_eq!(
            loaded
                .realtime
                .latest_error
                .as_ref()
                .and_then(|error| error.retry_after_seconds),
            Some(30)
        );
        assert_eq!(
            loaded
                .realtime
                .last_source_refresh
                .as_ref()
                .map(|refresh| refresh.new_titles_count),
            Some(2)
        );
        assert_eq!(
            loaded
                .resource_economy
                .as_ref()
                .map(|snapshot| snapshot.coalesced_warning_count_recent),
            Some(42)
        );
        assert_eq!(
            loaded
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.scope.as_str()),
            Some("command-report")
        );
        assert_eq!(
            loaded
                .realtime
                .latest_recovery_summary
                .as_ref()
                .and_then(|summary| summary.warning_summaries.first())
                .map(|warning| warning.count),
            Some(1427)
        );
        assert_eq!(
            loaded
                .realtime
                .latest_recovery_warnings
                .first()
                .and_then(|warning| warning.retry_after_seconds),
            Some(30)
        );
    }

    #[test]
    fn runtime_status_round_trips_precise_lag_current_task_and_actionable_issue() {
        let started_at = Utc::now();
        let status = RuntimeStatus {
            daemon_state: "running".to_string(),
            dry_run: false,
            compatibility_notice: Some(CompatibilityNotice {
                scope: "runtime".to_string(),
                severity: "warning".to_string(),
                summary: "older runtime artifact detected".to_string(),
                operator_action: "review compatibility guidance".to_string(),
                ..CompatibilityNotice::default()
            }),
            realtime: RealtimeRuntimeStatus {
                state: "catching-up".to_string(),
                current_lag_seconds: Some(1),
                current_lag_millis: Some(284),
                current_lag_source: Some("api-freshness-probe".to_string()),
                current_task: Some(CurrentTaskSnapshot {
                    task_kind: "catch-up".to_string(),
                    label: "since last successful hide".to_string(),
                    progress_done: Some(1),
                    progress_total: Some(3),
                    window_start: Some(started_at),
                    window_end: Some(started_at),
                    started_at: Some(started_at),
                    expected_resume_at: None,
                }),
                latest_actionable_issue: Some(ActionableIssueSnapshot {
                    severity: "error".to_string(),
                    summary: "stream stale while newer wiki edits exist".to_string(),
                    next_action: "watch the recovery window".to_string(),
                    detected_at: Some(started_at),
                }),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };

        let raw = serde_json::to_string(&status).unwrap();
        let loaded: RuntimeStatus = serde_json::from_str(&raw).unwrap();

        assert_eq!(loaded.realtime.current_lag_millis, Some(284));
        assert_eq!(
            loaded.realtime.current_lag_source.as_deref(),
            Some("api-freshness-probe")
        );
        assert_eq!(
            loaded
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.label.as_str()),
            Some("since last successful hide")
        );
        assert_eq!(
            loaded
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.summary.as_str()),
            Some("stream stale while newer wiki edits exist")
        );
        assert_eq!(
            loaded
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.summary.as_str()),
            Some("older runtime artifact detected")
        );
    }

    #[test]
    fn command_report_surface_loads_older_shape_with_aliases() {
        let raw = r#"{
          "command": "coverage-report",
          "generated_at": "2026-04-08T14:12:00Z",
          "window": {
            "start": "2026-04-08T13:30:00Z",
            "end": "2026-04-08T14:00:00Z"
          },
          "counts": {
            "checked": 12,
            "hidden": 3,
            "already_hidden": 6,
            "skipped": 2,
            "unresolved": 1
          },
          "unresolved": [
            {
              "title": "Fixture Page",
              "revid": 42,
              "reason": "throttled",
              "next_action": "retry after backoff"
            }
          ]
        }"#;

        let loaded: CommandReportSurface = serde_json::from_str(raw).unwrap();

        assert_eq!(loaded.command, "coverage-report");
        assert_eq!(loaded.counts.checked, 12);
        assert_eq!(loaded.counts.hidden, 3);
        assert_eq!(loaded.counts.already_hidden, 6);
        assert_eq!(loaded.counts.failed, 0);
        assert_eq!(loaded.counts.unresolved, 1);
        assert_eq!(loaded.unresolved_items.len(), 1);
        assert!(loaded.compatibility_notice.is_none());
    }

    #[test]
    fn unreadable_surface_notice_is_blocking_and_migration_required() {
        let notice = compatibility_notice_for_unreadable_surface(
            "runtime-status",
            Path::new("/tmp/runtime_status.json"),
            "readable runtime_status.json surface",
            "replace or remove the unreadable runtime status file before trusting suppressor status",
        );

        assert_eq!(notice.scope, "runtime-status");
        assert_eq!(notice.severity, "migration-required");
        assert_eq!(
            notice.previous_value.as_deref(),
            Some("/tmp/runtime_status.json")
        );
        assert_eq!(
            notice.expected_value.as_deref(),
            Some("readable runtime_status.json surface")
        );
        assert!(notice.blocking);
    }
}
