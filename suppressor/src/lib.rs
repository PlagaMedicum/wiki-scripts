pub mod app;
pub mod auth;
pub mod cache;
pub mod catchup;
pub mod cli;
mod commands;
pub mod config;
mod daemon;
pub(crate) mod effective_config;
pub mod locks;
pub mod metrics;
pub mod mw_api;
pub mod recentchange;
pub mod reconcile;
pub mod runtime;
mod scheduler;
mod signal_control;
pub mod signals;
mod simple_daemon;
pub mod state;
mod stream;
pub mod titles;
mod worker;

use anyhow::Result;

pub async fn run() -> Result<()> {
    app::run().await
}
