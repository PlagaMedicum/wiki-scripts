use std::path::PathBuf;

use anyhow::Result;

pub(crate) const LAUNCH_KIND_ENV: &str = "SUPPRESSOR_LAUNCH_KIND";
pub(crate) const LAUNCH_LOG_PATH_ENV: &str = "SUPPRESSOR_LAUNCH_LOG_PATH";
pub(crate) const LAUNCH_WRITE_PID_ENV: &str = "SUPPRESSOR_LAUNCH_WRITE_PID";
pub(crate) const SERVER_START_LAUNCH_KIND: &str = "server-start";

pub async fn run_daemon(config_path: PathBuf, dry_run: bool, verbose: bool) -> Result<()> {
    crate::simple_daemon::run_daemon(config_path, dry_run, verbose).await
}
