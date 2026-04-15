use std::sync::Arc;
use std::time::Duration;

use metrics::histogram;
use tracing::{debug, info, warn};

use crate::cache::{CachePersistence, CacheRefreshMode, refresh_cache};
use crate::reconcile::{ReconcileMode, next_current_day_delay, next_nightly_delay};
use crate::runtime::AppRuntime;

pub fn spawn_metadata_refresh_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        info!(
            every_seconds = runtime.config.suppression_list.metadata_recheck_seconds,
            "metadata recheck loop started"
        );
        loop {
            if let Err(error) = refresh_cache(
                &runtime.cache,
                &runtime.client,
                &runtime.config,
                &runtime.paths,
                CacheRefreshMode::Automatic,
                if runtime.dry_run {
                    CachePersistence::Ephemeral
                } else {
                    CachePersistence::Persist
                },
            )
            .await
            {
                warn!("metadata recheck failed: {error:#}");
            }
            tokio::time::sleep(Duration::from_secs(
                runtime.config.suppression_list.metadata_recheck_seconds,
            ))
            .await;
        }
    });
}

pub fn spawn_nightly_reconciliation_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        if !runtime.config.nightly_sweep.enabled {
            info!("nightly reconciliation loop disabled");
            return;
        }
        info!(
            timezone = %runtime.config.nightly_sweep.timezone,
            start_time = %runtime.config.nightly_sweep.start_time,
            page_concurrency = runtime.config.nightly_sweep.page_concurrency,
            "nightly reconciliation loop started"
        );
        loop {
            match next_nightly_delay(
                &runtime.config.nightly_sweep.timezone,
                &runtime.config.nightly_sweep.start_time,
            )
            .await
            {
                Ok(delay) => {
                    debug!(
                        delay_seconds = delay.as_secs(),
                        "waiting for next nightly reconciliation window"
                    );
                    histogram!("nightly_scheduler_delay_seconds").record(delay.as_secs_f64());
                    tokio::time::sleep(delay).await;
                }
                Err(error) => {
                    warn!("nightly scheduler failed: {error:#}");
                    tokio::time::sleep(Duration::from_secs(60)).await;
                }
            }
            runtime.reconcile.request_run(ReconcileMode::Full).await;
        }
    });
}

pub fn spawn_current_day_reconciliation_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        if !runtime.config.current_day_recheck.enabled {
            info!("current-day reconciliation loop disabled");
            return;
        }
        info!(
            min_delay_seconds = runtime.config.current_day_recheck.min_delay_seconds,
            max_delay_seconds = runtime.config.current_day_recheck.max_delay_seconds,
            "current-day reconciliation loop started"
        );
        loop {
            let delay = next_current_day_delay(
                runtime.config.current_day_recheck.min_delay_seconds,
                runtime.config.current_day_recheck.max_delay_seconds,
            );
            debug!(
                delay_seconds = delay.as_secs(),
                "waiting for next current-day reconciliation run"
            );
            histogram!("current_day_scheduler_delay_seconds").record(delay.as_secs_f64());
            tokio::time::sleep(delay).await;
            runtime
                .reconcile
                .request_run(ReconcileMode::CurrentDay)
                .await;
        }
    });
}
