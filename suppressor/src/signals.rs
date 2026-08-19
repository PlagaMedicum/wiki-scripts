use std::io::ErrorKind;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use tokio::signal::unix::{SignalKind, signal};

use crate::state::save_text_atomic;

pub const RELOAD_COMMAND: &str = "reload-cache";
pub const MANUAL_SWEEP_COMMAND: &str = "manual-sweep";

pub struct ClaimedControlCommand {
    processing_path: PathBuf,
}

impl ClaimedControlCommand {
    pub fn acknowledge(self) -> Result<()> {
        std::fs::remove_file(&self.processing_path)
            .with_context(|| format!("Failed to acknowledge {}", self.processing_path.display()))
    }
}

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

pub fn request_control_command(path: &Path) -> Result<()> {
    save_text_atomic(path, "requested\n")
}

pub fn claim_control_command(path: &Path) -> Result<Option<ClaimedControlCommand>> {
    let processing_path = path.with_extension(format!("processing.{}", std::process::id()));
    match std::fs::rename(path, &processing_path) {
        Ok(()) => Ok(Some(ClaimedControlCommand { processing_path })),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error)
            .with_context(|| format!("Failed to claim control request {}", path.display())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn control_request_is_atomically_claimed_and_acknowledged() {
        let temp = tempfile::tempdir().unwrap();
        let request = temp.path().join("commands/reload-cache");
        request_control_command(&request).unwrap();

        let claim = claim_control_command(&request).unwrap().unwrap();
        assert!(!request.exists());
        assert!(claim_control_command(&request).unwrap().is_none());

        claim.acknowledge().unwrap();
        assert_eq!(
            std::fs::read_dir(temp.path().join("commands"))
                .unwrap()
                .count(),
            0
        );
    }
}
