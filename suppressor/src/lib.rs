pub mod app;
pub mod auth;
pub mod cache;
pub mod catchup;
pub mod cli;
mod command_context;
mod commands;
pub mod config;
mod coverage_command;
mod daemon;
mod daemon_backlog;
mod daemon_windows;
pub(crate) mod effective_config;
pub mod locks;
pub mod memory;
pub mod metrics;
pub mod mw_api;
pub mod reconcile;
pub mod runtime;
mod server_start;
pub mod signals;
pub mod state;
mod status_command;
mod worker;

use anyhow::Result;

pub async fn run() -> Result<()> {
    app::run().await
}
