use std::fs;
use std::path::PathBuf;

use suppressor::config::{AppConfig, RuntimePaths};
use suppressor::state::{
    CommandReportSurface, ProcessedRevidsState, RuntimeStatus, SharedBackoffSnapshot,
    compatibility_notice_for_unreadable_surface, load_json, load_text, save_json_atomic,
    save_text_atomic,
};
use tempfile::{TempDir, tempdir};

fn runtime_paths_for_tempdir(temp: &TempDir) -> RuntimePaths {
    let config_path = temp.path().join("config.toml");
    fs::write(&config_path, include_str!("../config.toml")).unwrap();
    let config = AppConfig::load(&config_path).unwrap();
    RuntimePaths::resolve(&config_path, &config)
}

fn older_runtime_status_fixture() -> &'static str {
    r#"{
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
    }"#
}

fn older_command_report_fixture() -> &'static str {
    r#"{
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
    }"#
}

fn legacy_current_day_config() -> String {
    include_str!("../config.toml").replace("[daytime_verification]", "[current_day_recheck]")
}

fn command_report_fixture_path(paths: &RuntimePaths) -> PathBuf {
    paths.command_report_file()
}

fn write_stale_supervisor_artifacts(paths: &RuntimePaths) {
    fs::create_dir_all(&paths.state_dir).unwrap();
    fs::write(&paths.runtime_status_file, older_runtime_status_fixture()).unwrap();
    save_text_atomic(&paths.pid_file, "9999999").unwrap();
    fs::write(
        command_report_fixture_path(paths),
        older_command_report_fixture(),
    )
    .unwrap();
}

#[test]
fn loads_tracked_config() {
    let config = AppConfig::load(std::path::Path::new("config.toml")).unwrap();
    assert_eq!(config.wiki.wiki_code, "bewiki");
    assert_eq!(config.queue.capacity, 100);
    assert_eq!(config.realtime.stale_threshold_seconds, 10);
    assert_eq!(config.catchup.default_window_seconds, 1800);
}

#[test]
fn persists_processed_revid_state() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("processed_revids.json");
    let state = ProcessedRevidsState {
        capacity: 2,
        revids: vec![7, 9],
    };
    save_json_atomic(&path, &state).unwrap();
    let loaded: ProcessedRevidsState = load_json(&path).unwrap().unwrap();
    assert_eq!(loaded.revids, vec![7, 9]);
    fs::remove_file(path).unwrap();
}

#[test]
fn older_runtime_status_fixture_loads_with_safe_defaults() {
    let temp = tempdir().unwrap();
    let paths = runtime_paths_for_tempdir(&temp);
    fs::create_dir_all(&paths.state_dir).unwrap();
    fs::write(&paths.runtime_status_file, older_runtime_status_fixture()).unwrap();

    let loaded: RuntimeStatus = load_json(&paths.runtime_status_file).unwrap().unwrap();

    assert_eq!(loaded.daemon_state, "running");
    assert_eq!(loaded.realtime.state, "unknown");
    assert_eq!(loaded.realtime.stale_threshold_seconds, 10);
    assert!(loaded.realtime.latest_recovery_warnings.is_empty());
    assert!(loaded.realtime.backoff_until.is_none());
    assert!(loaded.realtime.shared_backoff.is_none());
    assert!(loaded.realtime.current_task.is_none());
    assert!(loaded.realtime.current_lag_millis.is_none());
    assert!(loaded.realtime.latest_actionable_issue.is_none());
}

#[test]
fn shared_backoff_runtime_status_contract_names_affected_callers_without_blocking_live_hiding() {
    let temp = tempdir().unwrap();
    let paths = runtime_paths_for_tempdir(&temp);
    fs::create_dir_all(&paths.state_dir).unwrap();
    let backoff_until = chrono::Utc::now() + chrono::TimeDelta::seconds(45);
    let status = RuntimeStatus {
        realtime: suppressor::state::RealtimeRuntimeStatus {
            state: "catching-up".to_string(),
            backoff_until: Some(backoff_until),
            shared_backoff: Some(SharedBackoffSnapshot {
                source: "recovery".to_string(),
                reason: "rate-limit-backoff".to_string(),
                backoff_until: Some(backoff_until),
                affected_paths: vec![
                    "catch-up".to_string(),
                    "reconciliation".to_string(),
                    "source-refresh".to_string(),
                    "one-shot-command".to_string(),
                ],
                live_hiding_blocked: false,
                recorded_at: Some(chrono::Utc::now()),
            }),
            ..suppressor::state::RealtimeRuntimeStatus::default()
        },
        ..RuntimeStatus::default()
    };

    save_json_atomic(&paths.runtime_status_file, &status).unwrap();
    let loaded: RuntimeStatus = load_json(&paths.runtime_status_file).unwrap().unwrap();
    let shared = loaded.realtime.shared_backoff.as_ref().unwrap();

    assert_eq!(loaded.realtime.backoff_until, Some(backoff_until));
    assert_eq!(shared.source, "recovery");
    assert_eq!(shared.reason, "rate-limit-backoff");
    assert_eq!(
        shared.affected_paths,
        vec![
            "catch-up".to_string(),
            "reconciliation".to_string(),
            "source-refresh".to_string(),
            "one-shot-command".to_string(),
        ]
    );
    assert!(!shared.live_hiding_blocked);
}

#[test]
fn older_command_report_fixture_loads_with_safe_defaults() {
    let loaded: CommandReportSurface =
        serde_json::from_str(older_command_report_fixture()).unwrap();

    assert_eq!(loaded.command, "coverage-report");
    assert_eq!(loaded.counts.checked, 12);
    assert_eq!(loaded.counts.hidden, 3);
    assert_eq!(loaded.counts.already_hidden, 6);
    assert_eq!(loaded.counts.failed, 0);
    assert_eq!(loaded.counts.unresolved, 1);
    assert_eq!(loaded.unresolved_items[0].revid, 42);
    assert!(loaded.unresolved_items[0].revision_url.is_none());
    assert!(loaded.scope_label.is_none());
    assert!(loaded.compatibility_notice.is_none());
}

#[test]
fn stale_supervisor_artifact_fixture_writes_pid_runtime_and_command_report() {
    let temp = tempdir().unwrap();
    let paths = runtime_paths_for_tempdir(&temp);
    write_stale_supervisor_artifacts(&paths);

    let pid = load_text(&paths.pid_file).unwrap();
    let runtime_status: RuntimeStatus = load_json(&paths.runtime_status_file).unwrap().unwrap();
    let command_report: CommandReportSurface = load_json(&command_report_fixture_path(&paths))
        .unwrap()
        .unwrap();

    assert_eq!(pid.as_deref(), Some("9999999"));
    assert_eq!(runtime_status.daemon_state, "running");
    assert_eq!(runtime_status.realtime.state, "unknown");
    assert_eq!(
        command_report.window.start.map(|value| value.to_rfc3339()),
        Some("2026-04-08T13:30:00+00:00".to_string())
    );
}

#[test]
fn tracked_config_accepts_legacy_current_day_recheck_alias() {
    let temp = tempdir().unwrap();
    let config_path = temp.path().join("legacy-config.toml");
    fs::write(&config_path, legacy_current_day_config()).unwrap();

    let config = AppConfig::load(&config_path).unwrap();

    assert!(config.daytime_verification.enabled);
    assert_eq!(config.daytime_verification.min_delay_seconds, 3600);
    assert_eq!(config.daytime_verification.max_delay_seconds, 21600);
    assert_eq!(config.daytime_verification.window_hours, 24);
}

#[test]
fn unreadable_runtime_status_surface_maps_to_migration_notice() {
    let temp = tempdir().unwrap();
    let paths = runtime_paths_for_tempdir(&temp);
    fs::create_dir_all(&paths.state_dir).unwrap();
    fs::write(&paths.runtime_status_file, "{").unwrap();

    let error = load_json::<RuntimeStatus>(&paths.runtime_status_file).unwrap_err();
    assert!(error.to_string().contains("Failed to parse"));

    let notice = compatibility_notice_for_unreadable_surface(
        "runtime-status",
        &paths.runtime_status_file,
        "readable runtime_status.json surface",
        "replace or remove the unreadable runtime status file before trusting suppressor status",
        "trust healthy status again only after the active daemon rewrites a readable runtime_status.json surface",
        "restart the last trusted daemon workflow and verify that it writes a readable runtime_status.json surface",
    );

    assert_eq!(notice.scope, "runtime-status");
    assert_eq!(notice.severity, "migration-required");
    assert!(notice.approval_text.is_some());
    assert!(notice.rollback_path.is_some());
    assert!(notice.blocking);
}

#[test]
fn unreadable_command_report_surface_maps_to_migration_notice() {
    let temp = tempdir().unwrap();
    let paths = runtime_paths_for_tempdir(&temp);
    fs::create_dir_all(&paths.state_dir).unwrap();
    fs::write(command_report_fixture_path(&paths), "{").unwrap();

    let error =
        load_json::<CommandReportSurface>(&command_report_fixture_path(&paths)).unwrap_err();
    assert!(error.to_string().contains("Failed to parse"));

    let notice = compatibility_notice_for_unreadable_surface(
        "command-report",
        &command_report_fixture_path(&paths),
        "bounded command-report surface",
        "rerun the command or remove the unreadable command report file before trusting the last command summary",
        "trust the last command summary again only after the current binary regenerates a readable bounded command report",
        "remove the unreadable command report and rerun the last trusted command workflow",
    );

    assert_eq!(notice.scope, "command-report");
    assert_eq!(notice.severity, "migration-required");
    assert!(notice.approval_text.is_some());
    assert!(notice.rollback_path.is_some());
    assert!(notice.blocking);
}
