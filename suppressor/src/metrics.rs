use std::collections::VecDeque;
use std::net::SocketAddr;
use std::sync::{Mutex, OnceLock};

use anyhow::{Context, Result};
use metrics::histogram;
use metrics_exporter_prometheus::PrometheusBuilder;

use crate::config::MetricsConfig;

static METRICS_INIT: OnceLock<()> = OnceLock::new();
static RUNTIME_LATENCY_METRICS: OnceLock<Mutex<RuntimeLatencyMetrics>> = OnceLock::new();
const RECENT_LATENCY_SAMPLE_LIMIT: usize = 256;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LatencyMetricSnapshot {
    pub sample_count: usize,
    pub latest_ms: Option<u64>,
    pub min_ms: Option<u64>,
    pub p50_ms: Option<u64>,
    pub p95_ms: Option<u64>,
    pub p99_ms: Option<u64>,
    pub max_ms: Option<u64>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RuntimeLatencyMetricsSnapshot {
    pub observed_to_queue: LatencyMetricSnapshot,
    pub observed_to_hide: LatencyMetricSnapshot,
}

#[derive(Clone, Debug, Default)]
struct RuntimeLatencyMetrics {
    observed_to_queue: BoundedLatencyMetric,
    observed_to_hide: BoundedLatencyMetric,
}

#[derive(Clone, Debug)]
struct BoundedLatencyMetric {
    samples: VecDeque<u64>,
    latest_ms: Option<u64>,
}

impl Default for BoundedLatencyMetric {
    fn default() -> Self {
        Self {
            samples: VecDeque::with_capacity(RECENT_LATENCY_SAMPLE_LIMIT),
            latest_ms: None,
        }
    }
}

impl BoundedLatencyMetric {
    fn record(&mut self, value_ms: u64) {
        if self.samples.len() == RECENT_LATENCY_SAMPLE_LIMIT {
            let _ = self.samples.pop_front();
        }
        self.samples.push_back(value_ms);
        self.latest_ms = Some(value_ms);
    }

    fn snapshot(&self) -> LatencyMetricSnapshot {
        let mut sorted = self.samples.iter().copied().collect::<Vec<_>>();
        sorted.sort_unstable();
        LatencyMetricSnapshot {
            sample_count: sorted.len(),
            latest_ms: self.latest_ms,
            min_ms: sorted.first().copied(),
            p50_ms: percentile(&sorted, 50),
            p95_ms: percentile(&sorted, 95),
            p99_ms: percentile(&sorted, 99),
            max_ms: sorted.last().copied(),
        }
    }

    #[cfg(test)]
    fn reset(&mut self) {
        self.samples.clear();
        self.latest_ms = None;
    }
}

fn runtime_latency_metrics() -> &'static Mutex<RuntimeLatencyMetrics> {
    RUNTIME_LATENCY_METRICS.get_or_init(|| Mutex::new(RuntimeLatencyMetrics::default()))
}

fn percentile(sorted: &[u64], percentile: usize) -> Option<u64> {
    if sorted.is_empty() {
        return None;
    }
    let rank = ((sorted.len() - 1) * percentile).div_ceil(100);
    sorted.get(rank).copied()
}

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

pub fn record_observed_to_queue_latency_ms(value_ms: u64) {
    histogram!("event_observed_to_queue_latency_ms").record(value_ms as f64);
    if let Ok(mut metrics) = runtime_latency_metrics().lock() {
        metrics.observed_to_queue.record(value_ms);
    }
}

pub fn record_observed_to_hide_latency_ms(value_ms: u64) {
    histogram!("event_observed_to_hide_latency_ms").record(value_ms as f64);
    if let Ok(mut metrics) = runtime_latency_metrics().lock() {
        metrics.observed_to_hide.record(value_ms);
    }
}

pub fn snapshot_runtime_latency_metrics() -> RuntimeLatencyMetricsSnapshot {
    if let Ok(metrics) = runtime_latency_metrics().lock() {
        return RuntimeLatencyMetricsSnapshot {
            observed_to_queue: metrics.observed_to_queue.snapshot(),
            observed_to_hide: metrics.observed_to_hide.snapshot(),
        };
    }
    RuntimeLatencyMetricsSnapshot::default()
}

#[cfg(test)]
pub fn reset_runtime_latency_metrics_for_tests() {
    if let Ok(mut metrics) = runtime_latency_metrics().lock() {
        metrics.observed_to_queue.reset();
        metrics.observed_to_hide.reset();
    }
}

#[cfg(test)]
pub fn latency_sample_limit_for_tests() -> usize {
    RECENT_LATENCY_SAMPLE_LIMIT
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounded_latency_metrics_keep_only_recent_samples() {
        let limit = latency_sample_limit_for_tests();
        let mut metric = BoundedLatencyMetric::default();
        for value in 1..=(limit as u64 + 8) {
            metric.record(value);
        }

        let snapshot = metric.snapshot();

        assert_eq!(snapshot.sample_count, limit);
        assert_eq!(snapshot.latest_ms, Some(limit as u64 + 8));
        assert_eq!(snapshot.min_ms, Some(9));
        assert_eq!(snapshot.max_ms, Some(limit as u64 + 8));
    }

    #[test]
    fn latency_metric_snapshot_reports_percentiles() {
        let mut metric = BoundedLatencyMetric::default();
        for value in [5_u64, 10, 15, 20, 25] {
            metric.record(value);
        }

        let snapshot = metric.snapshot();

        assert_eq!(snapshot.sample_count, 5);
        assert_eq!(snapshot.p50_ms, Some(15));
        assert_eq!(snapshot.p95_ms, Some(25));
        assert_eq!(snapshot.p99_ms, Some(25));
    }
}
