use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, TimeDelta, Utc};

use crate::catchup::{CatchupRequest, format_summary_lines, run_catchup_window};
use crate::config::RuntimePaths;
use crate::runtime::AppRuntime;
use crate::state::{
    CommandReportCounts, CommandReportSurface, CommandReportWindow, CompatibilityNotice,
    CoverageSummary, compatibility_notice_for_unreadable_surface, load_json, save_json_atomic,
};

fn render_command_report_lines(summary: &crate::state::CoverageSummary) -> Vec<String> {
    format_summary_lines(summary)
}

fn next_action_for_summary(summary: &CoverageSummary, report_only: bool) -> Option<String> {
    if summary.backoff_until.is_some() {
        return Some("wait for backoff to expire and rerun the command".to_string());
    }
    if report_only && summary.unresolved_count > 0 {
        return Some(
            "run emergency catch-up without report-only if hiding should proceed".to_string(),
        );
    }
    if summary.unresolved_count > 0 {
        return Some(
            "review unresolved items and rerun the command if exposure remains".to_string(),
        );
    }
    None
}

fn command_report_compatibility_notice(paths: &RuntimePaths) -> Option<CompatibilityNotice> {
    let path = paths.command_report_file();
    if !path.exists() {
        return None;
    }
    match load_json::<CommandReportSurface>(&path) {
        Ok(_) => None,
        Err(_) => Some(compatibility_notice_for_unreadable_surface(
            "command-report",
            &path,
            "bounded command-report surface",
            "review the previous command report file and trust the newly written bounded report",
            "treat the last command summary as trustworthy only after the current binary rewrites a bounded command report",
            "remove the incompatible command report and rerun the last trusted command workflow if the new report cannot be regenerated",
        )),
    }
}

fn persist_command_report(
    paths: &RuntimePaths,
    command: &str,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
    report_only: bool,
    summary: &CoverageSummary,
) -> Result<()> {
    let report = CommandReportSurface {
        command: command.to_string(),
        generated_at: Some(Utc::now()),
        report_only,
        scope_label: summary.scope_label.clone(),
        window: CommandReportWindow {
            start: Some(start),
            end: Some(end),
        },
        counts: CommandReportCounts {
            checked: summary.edits_checked,
            hidden: summary.hidden_count,
            already_hidden: summary.already_hidden_count,
            skipped: summary.skipped_count,
            failed: summary.failed_count,
            unresolved: summary.unresolved_count,
        },
        unresolved_items: summary.unresolved_items.clone(),
        stopped_early_reason: summary.stopped_early_reason.clone(),
        backoff_until: summary.backoff_until,
        next_action: next_action_for_summary(summary, report_only),
        compatibility_notice: command_report_compatibility_notice(paths),
    };
    save_json_atomic(&paths.command_report_file(), &report)
}

pub async fn run_emergency_catchup(
    config_path: PathBuf,
    start: Option<String>,
    end: Option<String>,
    allow_large_window: bool,
    dry_run: bool,
    report_only: bool,
    verbose: bool,
) -> Result<()> {
    let runtime = AppRuntime::bootstrap_for_command(config_path, dry_run, verbose).await?;
    let end = match end {
        Some(value) => parse_rfc3339_utc(&value)?,
        None => Utc::now(),
    };
    let recovery_window = runtime.default_recovery_window(end).await;
    let start = match start {
        Some(value) => parse_rfc3339_utc(&value)?,
        None => recovery_window.start,
    };
    let effective_allow_large_window =
        allow_large_window || start == recovery_window.start && recovery_window.allow_large_window;
    validate_window_bounds(
        start,
        end,
        runtime.config.catchup.max_window_seconds,
        effective_allow_large_window,
        report_only,
        "emergency-catchup",
    )?;
    let summary = run_catchup_window(
        &runtime,
        CatchupRequest {
            start,
            end,
            trigger: "operator-manual".to_string(),
            scope_label: if start == recovery_window.start {
                recovery_window.scope_label
            } else {
                "custom emergency window".to_string()
            },
            report_only,
            allow_large_window: effective_allow_large_window,
            title_scope: None,
        },
    )
    .await?;
    persist_command_report(
        &runtime.paths,
        "emergency-catchup",
        start,
        end,
        report_only,
        &summary,
    )?;
    for line in render_command_report_lines(&summary) {
        println!("{line}");
    }
    Ok(())
}

pub async fn run_coverage_last_24h(
    config_path: PathBuf,
    dry_run: bool,
    report_only: bool,
    verbose: bool,
) -> Result<()> {
    let runtime = AppRuntime::bootstrap_for_command(config_path, dry_run, verbose).await?;
    let end = Utc::now();
    let start = end - TimeDelta::hours(24);
    let summary = run_catchup_window(
        &runtime,
        CatchupRequest {
            start,
            end,
            trigger: "coverage-last-24h".to_string(),
            scope_label: "Last 24 hours".to_string(),
            report_only: report_only || dry_run,
            allow_large_window: true,
            title_scope: None,
        },
    )
    .await?;
    persist_command_report(
        &runtime.paths,
        "coverage-last-24h",
        start,
        end,
        report_only || dry_run,
        &summary,
    )?;
    for line in render_command_report_lines(&summary) {
        println!("{line}");
    }
    Ok(())
}

pub async fn run_coverage_report(
    config_path: PathBuf,
    start: String,
    end: Option<String>,
    allow_large_window: bool,
    dry_run: bool,
    report_only: bool,
    verbose: bool,
) -> Result<()> {
    let runtime = AppRuntime::bootstrap_for_command(config_path, dry_run, verbose).await?;
    let start = parse_rfc3339_utc(&start)?;
    let end = match end {
        Some(value) => parse_rfc3339_utc(&value)?,
        None => Utc::now(),
    };
    validate_window_bounds(
        start,
        end,
        runtime.config.catchup.max_window_seconds,
        allow_large_window,
        report_only || dry_run,
        "coverage-report",
    )?;
    let summary = run_catchup_window(
        &runtime,
        CatchupRequest {
            start,
            end,
            trigger: "coverage".to_string(),
            scope_label: "custom coverage window".to_string(),
            report_only: report_only || dry_run,
            allow_large_window,
            title_scope: None,
        },
    )
    .await?;
    persist_command_report(
        &runtime.paths,
        "coverage-report",
        start,
        end,
        report_only || dry_run,
        &summary,
    )?;
    for line in render_command_report_lines(&summary) {
        println!("{line}");
    }
    Ok(())
}

fn parse_rfc3339_utc(value: &str) -> Result<DateTime<Utc>> {
    Ok(DateTime::parse_from_rfc3339(value)
        .with_context(|| format!("invalid RFC3339 timestamp {value}"))?
        .with_timezone(&Utc))
}

fn validate_window_bounds(
    start: DateTime<Utc>,
    end: DateTime<Utc>,
    max_window_seconds: i64,
    allow_large_window: bool,
    report_only: bool,
    command_name: &str,
) -> Result<()> {
    if end < start {
        bail!(
            "{command_name} requires start <= end; got start={} end={}",
            start.to_rfc3339(),
            end.to_rfc3339()
        );
    }

    let window_seconds = end.signed_duration_since(start).num_seconds();
    if window_seconds > max_window_seconds && !allow_large_window && !report_only {
        bail!(
            "{command_name} window {}s exceeds configured max {}s; rerun with --allow-large-window or use --report-only",
            window_seconds,
            max_window_seconds
        );
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{CommandReportSurface, UnresolvedExposureItem, load_json};

    fn test_runtime_paths(temp: &tempfile::TempDir) -> RuntimePaths {
        RuntimePaths {
            config_path: temp.path().join("config.toml"),
            state_dir: temp.path().join("state"),
            env_file: temp.path().join(".env"),
            cache_file: temp.path().join("cache.json"),
            last_event_id_file: temp.path().join("last_event_id.txt"),
            processed_revids_file: temp.path().join("processed.json"),
            nightly_sweep_progress_file: temp.path().join("progress.json"),
            runtime_status_file: temp.path().join("runtime_status.json"),
            pid_file: temp.path().join("daemon.pid"),
        }
    }

    #[test]
    fn parses_rfc3339_utc_timestamp() {
        let parsed = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        assert_eq!(parsed.to_rfc3339(), "2026-04-24T16:00:00+00:00");
    }

    #[test]
    fn rejects_timestamp_without_timezone() {
        let error = parse_rfc3339_utc("2026-04-24T16:00:00").unwrap_err();
        assert!(error.to_string().contains("invalid RFC3339 timestamp"));
    }

    #[test]
    fn rejects_inverted_windows_before_api_work() {
        let start = parse_rfc3339_utc("2026-04-24T16:30:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();

        let error =
            validate_window_bounds(start, end, 1800, false, false, "coverage-report").unwrap_err();

        assert!(error.to_string().contains("requires start <= end"));
    }

    #[test]
    fn rejects_oversized_windows_without_override_or_report_only() {
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T17:00:01Z").unwrap();

        let error = validate_window_bounds(start, end, 3600, false, false, "emergency-catchup")
            .unwrap_err();

        assert!(error.to_string().contains("--allow-large-window"));
        assert!(error.to_string().contains("--report-only"));
    }

    #[test]
    fn accepts_oversized_windows_with_explicit_override() {
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T18:00:01Z").unwrap();

        validate_window_bounds(start, end, 3600, true, false, "coverage-report").unwrap();
    }

    #[test]
    fn accepts_oversized_windows_in_report_only_mode() {
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T18:00:01Z").unwrap();

        validate_window_bounds(start, end, 3600, false, true, "coverage-report").unwrap();
    }

    #[test]
    fn command_reports_redact_sensitive_reason_and_action_text() {
        let summary = CoverageSummary {
            requested_by: "coverage".to_string(),
            unresolved_count: 1,
            unresolved_items: vec![UnresolvedExposureItem {
                title: "Sensitive Page".to_string(),
                revid: 77,
                revision_url: Some("https://example.invalid/wiki/Special:Diff/77".to_string()),
                age_seconds: Some(45),
                reason: "revisiondelete failed token=abc123 cookie=sessionid".to_string(),
                next_action: "inspect response body: <html>bad</html> password=secret".to_string(),
            }],
            ..CoverageSummary::default()
        };

        let rendered = render_command_report_lines(&summary).join("\n");

        assert!(rendered.contains("coverage.unresolved_item"));
        assert!(rendered.contains("title=Sensitive Page"));
        assert!(rendered.contains("revid=77"));
        assert!(rendered.contains("age_seconds=45"));
        assert!(!rendered.contains("abc123"));
        assert!(!rendered.contains("sessionid"));
        assert!(!rendered.contains("<html>bad</html>"));
        assert!(!rendered.contains("password=secret"));
    }

    #[test]
    fn command_report_persists_to_separate_surface() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T16:05:00Z").unwrap();
        let summary = CoverageSummary {
            requested_by: "coverage".to_string(),
            edits_checked: 3,
            hidden_count: 1,
            already_hidden_count: 1,
            unresolved_count: 1,
            unresolved_items: vec![UnresolvedExposureItem {
                title: "Page".to_string(),
                revid: 42,
                revision_url: Some("https://example.invalid/wiki/Special:Diff/42".to_string()),
                age_seconds: Some(5),
                reason: "report-only-not-hidden".to_string(),
                next_action: "run emergency catch-up without report-only".to_string(),
            }],
            ..CoverageSummary::default()
        };

        persist_command_report(&paths, "coverage-report", start, end, true, &summary).unwrap();

        let report: CommandReportSurface =
            load_json(&paths.command_report_file()).unwrap().unwrap();
        assert_eq!(report.command, "coverage-report");
        assert!(report.report_only);
        assert_eq!(report.counts.checked, 3);
        assert_eq!(report.counts.hidden, 1);
        assert_eq!(report.counts.already_hidden, 1);
        assert_eq!(report.counts.unresolved, 1);
        assert_eq!(report.unresolved_items.len(), 1);
        assert_eq!(
            report.window.start.map(|value| value.to_rfc3339()),
            Some("2026-04-24T16:00:00+00:00".to_string())
        );
        assert!(!paths.runtime_status_file.exists());
    }

    #[test]
    fn invalid_previous_command_report_emits_compatibility_notice() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        std::fs::create_dir_all(&paths.state_dir).unwrap();
        std::fs::write(
            paths.command_report_file(),
            r#"{"command":"coverage-report","counts":"not-an-object"}"#,
        )
        .unwrap();
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T16:05:00Z").unwrap();

        persist_command_report(
            &paths,
            "coverage-report",
            start,
            end,
            false,
            &CoverageSummary::default(),
        )
        .unwrap();

        let report: CommandReportSurface =
            load_json(&paths.command_report_file()).unwrap().unwrap();
        assert_eq!(
            report
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.scope.as_str()),
            Some("command-report")
        );
        assert_eq!(
            report
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.severity.as_str()),
            Some("migration-required")
        );
        assert_eq!(
            report
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.blocking),
            Some(true)
        );
    }
}
