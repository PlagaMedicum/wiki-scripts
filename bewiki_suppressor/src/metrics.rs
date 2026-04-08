use std::net::SocketAddr;
use std::sync::OnceLock;

use anyhow::{Context, Result};
use metrics_exporter_prometheus::PrometheusBuilder;

use crate::config::MetricsConfig;

static METRICS_INIT: OnceLock<()> = OnceLock::new();

pub fn init_metrics(config: &MetricsConfig) -> Result<()> {
    if !config.enabled {
        return Ok(());
    }
    if METRICS_INIT.get().is_some() {
        return Ok(());
    }
    let addr: SocketAddr = config
        .bind
        .parse()
        .with_context(|| format!("Invalid metrics bind address {}", config.bind))?;
    PrometheusBuilder::new()
        .with_http_listener(addr)
        .install_recorder()
        .context("Failed to install Prometheus recorder")?;
    let _ = METRICS_INIT.set(());
    Ok(())
}
