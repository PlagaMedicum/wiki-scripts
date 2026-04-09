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
use crate::stream::spawn_stream_loop;

pub async fn run_daemon(config_path: PathBuf, dry_run: bool) -> Result<()> {
    let runtime = AppRuntime::bootstrap(config_path, dry_run).await?;
    info!(
        dry_run,
        stream_url = %runtime.client.stream_url(),
        state_dir = %runtime.paths.state_dir.display(),
        "daemon runtime started"
    );
    if !dry_run {
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
            status.last_notice = Some("daemon stopping".to_string());
            status.last_notice_at = Some(Utc::now());
        })
        .await;
    if !dry_run {
        signals::remove_pid_file(&runtime.paths.pid_file)?;
        info!("removed daemon pid file");
    }
    runtime
        .update_runtime_status(|status| {
            status.daemon_state = "stopped".to_string();
            status.reconciliation.active = false;
            status.reconciliation.current_title = None;
            status.last_notice = Some("daemon stopped".to_string());
            status.last_notice_at = Some(Utc::now());
        })
        .await;
    info!("daemon stopped");
    Ok(())
}
