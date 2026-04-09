use std::path::Path;

use anyhow::{Context, Result, bail};
use nix::sys::signal::{Signal, kill};
use nix::unistd::Pid;
use tokio::signal::unix::{SignalKind, signal};

use crate::state::{load_text, save_text_atomic};

pub const RELOAD_SIGNAL: Signal = Signal::SIGHUP;
pub const MANUAL_SWEEP_SIGNAL: Signal = Signal::SIGUSR1;

pub async fn install_reload_listener() -> Result<tokio::signal::unix::Signal> {
    signal(SignalKind::hangup()).context("Failed to install reload signal listener")
}

pub async fn install_manual_sweep_listener() -> Result<tokio::signal::unix::Signal> {
    signal(SignalKind::user_defined1()).context("Failed to install manual sweep signal listener")
}

pub fn write_pid_file(path: &Path) -> Result<()> {
    save_text_atomic(path, &std::process::id().to_string())
}

pub fn remove_pid_file(path: &Path) -> Result<()> {
    if path.exists() {
        std::fs::remove_file(path)
            .with_context(|| format!("Failed to remove {}", path.display()))?;
    }
    Ok(())
}

pub fn send_reload(path: &Path) -> Result<()> {
    send_signal(path, RELOAD_SIGNAL, "reload-cache")
}

pub fn send_manual_sweep(path: &Path) -> Result<()> {
    send_signal(path, MANUAL_SWEEP_SIGNAL, "nightly-sweep-now")
}

fn send_signal(path: &Path, signal: Signal, command_name: &str) -> Result<()> {
    let raw = load_text(path)?.ok_or_else(|| {
        anyhow::anyhow!(
            "`{}` requires a running daemon, but no PID file exists at {}. Start the daemon first with `make run`.",
            command_name,
            path.display()
        )
    })?;
    let pid: i32 = raw
        .parse()
        .with_context(|| format!("Invalid PID file {}", path.display()))?;
    if pid <= 0 {
        bail!("Invalid PID {}", pid);
    }
    kill(Pid::from_raw(pid), signal)
        .with_context(|| format!("Failed to send {:?} to PID {}", signal, pid))?;
    Ok(())
}
