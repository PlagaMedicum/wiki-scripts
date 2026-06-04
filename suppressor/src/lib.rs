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
pub mod metrics;
pub mod mw_api;
pub mod recentchange;
pub mod reconcile;
pub mod runtime;
mod scheduler;
mod server_start;
mod signal_control;
pub mod signals;
pub mod state;
mod status_command;
mod stream;
pub mod titles;
mod worker;

use anyhow::Result;

pub async fn run() -> Result<()> {
    app::run().await
}
