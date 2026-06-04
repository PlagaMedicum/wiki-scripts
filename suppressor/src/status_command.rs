use std::path::PathBuf;

use anyhow::{Context, Result, ensure};
use chrono::{TimeDelta, Utc};

use crate::cache::{RuntimeCache, load_cached_snapshot};
use crate::command_context::CommandContext;
use crate::config::RuntimePaths;
use crate::mw_api::MediaWikiClient;
use crate::state::{ExecutionLaneSnapshot, LatencyMetricStatus, RuntimeStatus, load_json};
use suppressor_core::titles::normalize_title;

#[derive(Debug, PartialEq, Eq)]
struct HealthVerdict {
    state: &'static str,
    exit_code: i32,
    summary: String,
}

pub fn run_status(config_path: PathBuf, json: bool) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    let status = load_runtime_status(&command.paths)?;
    if json {
        println!("{}", serde_json::to_string_pretty(&status)?);
        return Ok(());
    }
    for line in render_status_lines(&command.paths, &status) {
        println!("{line}");
    }
    Ok(())
}

pub fn run_health(config_path: PathBuf, json: bool) -> Result<i32> {
    let command = CommandContext::load(&config_path)?;
    let status = load_runtime_status(&command.paths)?;
    let verdict = health_verdict(&status);
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "state": verdict.state,
                "exit_code": verdict.exit_code,
                "summary": verdict.summary,
                "daemon_state": status.daemon_state,
                "realtime_state": status.realtime.state,
                "current_lag_millis": status.realtime.current_lag_millis,
                "current_lag_source": status.realtime.current_lag_source,
                "latest_notice": status.realtime.latest_notice,
            }))?
        );
        return Ok(verdict.exit_code);
    }
    println!("health.state={}", verdict.state);
    println!("health.exit_code={}", verdict.exit_code);
    println!("health.summary={}", verdict.summary);
    println!("daemon_state={}", empty_as_unknown(&status.daemon_state));
    println!(
        "realtime_state={}",
        empty_as_unknown(&status.realtime.state)
    );
    if let Some(lag) = status.realtime.current_lag_millis {
        println!("current_lag_millis={lag}");
    }
    Ok(verdict.exit_code)
}

pub async fn run_last_edits(config_path: PathBuf, limit: usize, json: bool) -> Result<()> {
    ensure!(limit > 0, "last-edits requires --limit greater than zero");
    let command = CommandContext::load(&config_path)?;
    let env = crate::config::load_env(&command.paths.config_path)?;
    let client = MediaWikiClient::new_with_retry(&env, &command.config.retry)?;
    let cache = load_cached_snapshot(&command.paths)
        .with_context(|| format!("failed to read {}", command.paths.cache_file.display()))?
        .map(RuntimeCache::from_snapshot)
        .with_context(|| {
            format!(
                "last-edits requires an existing watched-title cache at {}; run the daemon or reload-cache first",
                command.paths.cache_file.display()
            )
        })?;
    let end = Utc::now();
    let start = end - TimeDelta::seconds(command.config.catchup.default_window_seconds);
    let window = client
        .fetch_recent_changes_in_window(start, end, command.config.catchup.max_revisions_per_run)
        .await?;
    let watched = window
        .changes
        .into_iter()
        .filter(|change| cache.watched_set.contains(&normalize_title(&change.title)))
        .take(limit)
        .collect::<Vec<_>>();
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "window_start": start,
                "window_end": end,
                "limit": limit,
                "truncated": window.truncated,
                "chunk_count": window.chunk_count,
                "watched": watched,
            }))?
        );
        return Ok(());
    }
    println!("window_start={}", start.to_rfc3339());
    println!("window_end={}", end.to_rfc3339());
    println!("chunk_count={}", window.chunk_count);
    println!("truncated={}", window.truncated);
    println!("watched_count={}", watched.len());
    for change in watched {
        println!(
            "{} revid={} title={}",
            change.timestamp.to_rfc3339(),
            change.revid,
            change.title
        );
    }
    Ok(())
}

pub fn run_perf(config_path: PathBuf, json: bool) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    let status = load_runtime_status(&command.paths)?;
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "metrics": command.config.metrics,
                "live_lane": status.realtime.live_lane,
                "background_lane": status.realtime.background_lane,
                "latency": status.realtime.latency,
                "resource_economy": status.resource_economy,
            }))?
        );
        return Ok(());
    }
    println!("metrics.enabled={}", command.config.metrics.enabled);
    println!("metrics.bind={}", command.config.metrics.bind);
    print_lane("live", &status.realtime.live_lane);
    print_lane("background", &status.realtime.background_lane);
    print_latency(
        "observed_to_queue",
        &status.realtime.latency.observed_to_queue,
    );
    print_latency("queue_to_submit", &status.realtime.latency.queue_to_submit);
    print_latency(
        "submit_to_complete",
        &status.realtime.latency.submit_to_complete,
    );
    print_latency(
        "observed_to_hidden",
        &status.realtime.latency.observed_to_hidden,
    );
    if let Some(resource) = status.resource_economy {
        println!(
            "resource.max_depths live={} background={} total={}",
            resource.live_queue_depth_max_recent,
            resource.background_queue_depth_max_recent,
            resource.queue_depth_max_recent
        );
        println!(
            "resource.state_bytes_recent={}",
            resource.state_bytes_recent
        );
    }
    Ok(())
}

fn load_runtime_status(paths: &RuntimePaths) -> Result<RuntimeStatus> {
    match load_json::<RuntimeStatus>(&paths.runtime_status_file) {
        Ok(Some(status)) => Ok(status),
        Ok(None) => Ok(status_surface_problem(
            "missing-status",
            format!(
                "runtime status file is missing: {}",
                paths.runtime_status_file.display()
            ),
        )),
        Err(error) => Ok(status_surface_problem(
            "unreadable-status",
            format!(
                "runtime status file is unreadable: {}: {error}",
                paths.runtime_status_file.display()
            ),
        )),
    }
}

fn status_surface_problem(daemon_state: &str, notice: String) -> RuntimeStatus {
    RuntimeStatus {
        daemon_state: daemon_state.to_string(),
        last_notice: Some(notice),
        ..RuntimeStatus::default()
    }
}

fn render_status_lines(paths: &RuntimePaths, status: &RuntimeStatus) -> Vec<String> {
    let mut lines = vec![
        format!("daemon_state={}", empty_as_unknown(&status.daemon_state)),
        format!("dry_run={}", status.dry_run),
        format!(
            "realtime_state={}",
            empty_as_unknown(&status.realtime.state)
        ),
        format!("pid_file={}", paths.pid_file.display()),
        format!("runtime_status={}", paths.runtime_status_file.display()),
    ];
    if let Some(pid) = status.launch_path.as_ref().map(|launch| launch.pid) {
        lines.push(format!("launch_pid={pid}"));
    }
    if let Some(kind) = status
        .launch_path
        .as_ref()
        .map(|launch| launch.kind.as_str())
    {
        lines.push(format!("launch_path={kind}"));
    }
    if let Some(lag) = status.realtime.current_lag_millis {
        lines.push(format!("current_lag_millis={lag}"));
    }
    if let Some(source) = status.realtime.current_lag_source.as_deref() {
        lines.push(format!("current_lag_source={source}"));
    }
    if let Some(task) = status.realtime.current_task.as_ref() {
        lines.push(format!("current_task={} {}", task.task_kind, task.label));
    }
    if let Some(outcome) = status.realtime.latest_outcome.as_ref() {
        lines.push(format!(
            "latest_outcome={} revid={} title={}",
            outcome.outcome, outcome.revid, outcome.title
        ));
    }
    if let Some(error) = status.realtime.latest_error.as_ref() {
        lines.push(format!(
            "latest_error class={} code={} retryable={} message={}",
            error.class,
            error.api_code.as_deref().unwrap_or("none"),
            error.retryable,
            error.message
        ));
    }
    if let Some(issue) = status.realtime.latest_actionable_issue.as_ref() {
        lines.push(format!(
            "actionable_issue severity={} source={} summary={}",
            issue.severity, issue.source, issue.summary
        ));
    }
    if let Some(notice) = status
        .realtime
        .latest_notice
        .as_deref()
        .or(status.last_notice.as_deref())
    {
        lines.push(format!("notice={notice}"));
    }
    lines.push(format_lane("live", &status.realtime.live_lane));
    lines.push(format_lane("background", &status.realtime.background_lane));
    if paths.command_report_file().exists() {
        lines.push(format!(
            "command_report={}",
            paths.command_report_file().display()
        ));
    }
    lines
}

fn health_verdict(status: &RuntimeStatus) -> HealthVerdict {
    let daemon = status.daemon_state.as_str();
    let realtime = status.realtime.state.as_str();
    if matches!(daemon, "missing-status" | "unreadable-status" | "stopped")
        || matches!(realtime, "blocked" | "unknown")
    {
        return HealthVerdict {
            state: "blocked",
            exit_code: 2,
            summary: status
                .last_notice
                .clone()
                .unwrap_or_else(|| "daemon status is unavailable or blocked".to_string()),
        };
    }
    if !matches!(daemon, "running" | "dry-run" | "dry-run-running") {
        return HealthVerdict {
            state: "blocked",
            exit_code: 2,
            summary: format!("daemon is not running: {}", empty_as_unknown(daemon)),
        };
    }
    if realtime == "healthy" {
        return HealthVerdict {
            state: "healthy",
            exit_code: 0,
            summary: "realtime protection is healthy".to_string(),
        };
    }
    HealthVerdict {
        state: "degraded",
        exit_code: 1,
        summary: format!("realtime protection is {realtime}"),
    }
}

fn empty_as_unknown(value: &str) -> &str {
    if value.is_empty() { "unknown" } else { value }
}

fn format_lane(label: &str, lane: &ExecutionLaneSnapshot) -> String {
    format!(
        "{label}_lane queue_depth={} queue_capacity={} in_flight={} concurrency_limit={} saturation={}",
        lane.queue_depth,
        lane.queue_capacity,
        lane.in_flight,
        lane.concurrency_limit,
        lane.latest_saturation_reason.as_deref().unwrap_or("none")
    )
}

fn print_lane(label: &str, lane: &ExecutionLaneSnapshot) {
    println!("{label}.queue_depth={}", lane.queue_depth);
    println!("{label}.queue_capacity={}", lane.queue_capacity);
    println!("{label}.in_flight={}", lane.in_flight);
    println!("{label}.concurrency_limit={}", lane.concurrency_limit);
    if let Some(reason) = lane.latest_saturation_reason.as_deref() {
        println!("{label}.latest_saturation_reason={reason}");
    }
}

fn print_latency(label: &str, metric: &LatencyMetricStatus) {
    println!("{label}.sample_count={}", metric.sample_count);
    if let Some(value) = metric.latest_ms {
        println!("{label}.latest_ms={value}");
    }
    if let Some(value) = metric.p50_ms {
        println!("{label}.p50_ms={value}");
    }
    if let Some(value) = metric.p95_ms {
        println!("{label}.p95_ms={value}");
    }
    if let Some(value) = metric.p99_ms {
        println!("{label}.p99_ms={value}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{
        CurrentTaskSnapshot, ExecutionLaneSnapshot, LaunchPathSnapshot, RealtimeRuntimeStatus,
    };

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

    fn server_start_runtime_status(
        paths: &RuntimePaths,
        pid: i32,
        dry_run: bool,
        started_at: chrono::DateTime<Utc>,
    ) -> RuntimeStatus {
        RuntimeStatus {
            daemon_state: if dry_run {
                "dry-run-running".to_string()
            } else {
                "running".to_string()
            },
            dry_run,
            launch_path: Some(LaunchPathSnapshot {
                kind: crate::daemon::SERVER_START_LAUNCH_KIND.to_string(),
                pid,
                config_path: paths.config_path.display().to_string(),
                pid_file: paths.pid_file.display().to_string(),
                runtime_status_file: paths.runtime_status_file.display().to_string(),
                log_path: Some(paths.state_dir.join("daemon.log").display().to_string()),
                started_at: Some(started_at),
                ..LaunchPathSnapshot::default()
            }),
            last_notice: Some("daemon runtime started".to_string()),
            last_notice_at: Some(started_at),
            realtime: RealtimeRuntimeStatus {
                daemon_started_at: Some(started_at),
                live_lane: ExecutionLaneSnapshot {
                    queue_capacity: 100,
                    concurrency_limit: 1,
                    ..ExecutionLaneSnapshot::default()
                },
                background_lane: ExecutionLaneSnapshot {
                    queue_capacity: 100,
                    concurrency_limit: 1,
                    ..ExecutionLaneSnapshot::default()
                },
                current_task: Some(CurrentTaskSnapshot {
                    task_kind: "idle".to_string(),
                    label: "waiting for watched-page edits".to_string(),
                    started_at: Some(started_at),
                    ..CurrentTaskSnapshot::default()
                }),
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        }
    }

    #[test]
    fn health_verdict_reports_healthy_runtime() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let mut status = server_start_runtime_status(&paths, 42, false, Utc::now());
        status.realtime.state = "healthy".to_string();

        let verdict = health_verdict(&status);

        assert_eq!(verdict.state, "healthy");
        assert_eq!(verdict.exit_code, 0);
    }

    #[test]
    fn health_verdict_reports_degraded_runtime() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let mut status = server_start_runtime_status(&paths, 42, false, Utc::now());
        status.realtime.state = "catching-up".to_string();

        let verdict = health_verdict(&status);

        assert_eq!(verdict.state, "degraded");
        assert_eq!(verdict.exit_code, 1);
    }

    #[test]
    fn health_verdict_reports_missing_status_as_blocked() {
        let status = status_surface_problem("missing-status", "runtime status missing".to_string());

        let verdict = health_verdict(&status);

        assert_eq!(verdict.state, "blocked");
        assert_eq!(verdict.exit_code, 2);
    }

    #[test]
    fn status_lines_show_core_runtime_fields() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let mut status = server_start_runtime_status(&paths, 42, false, Utc::now());
        status.realtime.state = "healthy".to_string();
        status.realtime.current_lag_millis = Some(120);

        let lines = render_status_lines(&paths, &status);

        assert!(lines.iter().any(|line| line == "daemon_state=running"));
        assert!(lines.iter().any(|line| line == "realtime_state=healthy"));
        assert!(lines.iter().any(|line| line == "current_lag_millis=120"));
        assert!(lines.iter().any(|line| line.starts_with("live_lane ")));
    }
}
