use std::path::PathBuf;

use anyhow::{Context, Result};
use chrono::Utc;
use tracing::info;

use crate::runtime::AppRuntime;
use crate::scheduler::{
    spawn_current_day_reconciliation_loop, spawn_metadata_refresh_loop,
    spawn_nightly_reconciliation_loop,
};
use crate::signal_control::spawn_signal_control_loop;
use crate::signals;
use crate::state::LaunchPathSnapshot;
use crate::stream::spawn_stream_loop;

pub(crate) const LAUNCH_KIND_ENV: &str = "SUPPRESSOR_LAUNCH_KIND";
pub(crate) const LAUNCH_LOG_PATH_ENV: &str = "SUPPRESSOR_LAUNCH_LOG_PATH";
pub(crate) const LAUNCH_WRITE_PID_ENV: &str = "SUPPRESSOR_LAUNCH_WRITE_PID";
pub(crate) const SERVER_START_LAUNCH_KIND: &str = "server-start";

pub async fn run_daemon(config_path: PathBuf, dry_run: bool, verbose: bool) -> Result<()> {
    let runtime = AppRuntime::bootstrap(config_path, dry_run, verbose).await?;
    let started_at = Utc::now();
    let launch_path = launch_path_snapshot(&runtime, started_at);
    let write_pid = !dry_run || server_start_should_write_pid();
    info!(
        dry_run,
        verbose,
        stream_url = %runtime.client.stream_url(),
        state_dir = %runtime.paths.state_dir.display(),
        "daemon runtime started"
    );
    if write_pid {
        signals::write_pid_file(&runtime.paths.pid_file)?;
        info!(pid_file = %runtime.paths.pid_file.display(), "wrote daemon pid file");
    }
    runtime
        .update_runtime_status(|status| {
            status.daemon_state = if dry_run {
                "dry-run-running".to_string()
            } else {
                "running".to_string()
            };
            status.dry_run = dry_run;
            status.launch_path = Some(launch_path);
            status.last_notice = Some("daemon runtime started".to_string());
            status.last_notice_at = Some(Utc::now());
        })
        .await;

    spawn_stream_loop(std::sync::Arc::clone(&runtime));
    spawn_metadata_refresh_loop(std::sync::Arc::clone(&runtime));
    spawn_nightly_reconciliation_loop(std::sync::Arc::clone(&runtime));
    spawn_current_day_reconciliation_loop(std::sync::Arc::clone(&runtime));
    if !dry_run {
        spawn_signal_control_loop(std::sync::Arc::clone(&runtime));
    }

    info!("daemon is running; press Ctrl-C to stop");
    tokio::signal::ctrl_c()
        .await
        .context("Failed to wait for Ctrl-C")?;
    runtime
        .update_runtime_status(|status| {
            status.daemon_state = "stopping".to_string();
            status.realtime.state = "stopped".to_string();
            status.realtime.last_state_changed_at = Some(Utc::now());
            status.last_notice = Some("daemon stopping".to_string());
            status.last_notice_at = Some(Utc::now());
        })
        .await;
    if write_pid {
        signals::remove_pid_file(&runtime.paths.pid_file)?;
        info!("removed daemon pid file");
    }
    runtime
        .update_runtime_status(|status| {
            status.daemon_state = "stopped".to_string();
            status.realtime.state = "stopped".to_string();
            status.realtime.last_state_changed_at = Some(Utc::now());
            status.reconciliation.active = false;
            status.reconciliation.current_title = None;
            status.last_notice = Some("daemon stopped".to_string());
            status.last_notice_at = Some(Utc::now());
        })
        .await;
    info!("daemon stopped");
    Ok(())
}

fn launch_path_snapshot(
    runtime: &std::sync::Arc<AppRuntime>,
    started_at: chrono::DateTime<Utc>,
) -> LaunchPathSnapshot {
    let kind = std::env::var(LAUNCH_KIND_ENV).unwrap_or_else(|_| "foreground".to_string());
    let binary_path = std::env::current_exe()
        .ok()
        .map(|path| path.display().to_string());
    let log_path = std::env::var(LAUNCH_LOG_PATH_ENV).ok();
    LaunchPathSnapshot {
        kind,
        pid: std::process::id() as i32,
        binary_path,
        config_path: runtime.paths.config_path.display().to_string(),
        pid_file: runtime.paths.pid_file.display().to_string(),
        runtime_status_file: runtime.paths.runtime_status_file.display().to_string(),
        log_path,
        started_at: Some(started_at),
    }
}

fn server_start_should_write_pid() -> bool {
    std::env::var(LAUNCH_WRITE_PID_ENV)
        .map(|value| value == "1")
        .unwrap_or(false)
}
