use std::sync::Arc;

use tracing::{info, warn};

use crate::cache::{CachePersistence, CacheRefreshMode, refresh_cache};
use crate::reconcile::ReconcileMode;
use crate::runtime::AppRuntime;
use crate::signals;

pub fn spawn_signal_control_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        info!("signal control loop started");
        let mut reload_signal = match signals::install_reload_listener().await {
            Ok(signal) => signal,
            Err(error) => {
                warn!("reload signal listener failed: {error:#}");
                return;
            }
        };
        let mut sweep_signal = match signals::install_manual_sweep_listener().await {
            Ok(signal) => signal,
            Err(error) => {
                warn!("manual sweep signal listener failed: {error:#}");
                return;
            }
        };
        loop {
            tokio::select! {
                _ = reload_signal.recv() => {
                    info!("received manual cache reload signal");
                    runtime.reconcile.record_notice("received manual cache reload signal").await;
                    if let Err(error) = refresh_cache(
                        &runtime.cache,
                        &runtime.client,
                        &runtime.config,
                        &runtime.paths,
                        CacheRefreshMode::Forced,
                        CachePersistence::Persist,
                    ).await {
                        runtime
                            .reconcile
                            .record_notice(format!("manual cache reload failed: {error}"))
                            .await;
                        warn!("manual cache reload failed: {error:#}");
                    } else {
                        runtime.reconcile.record_notice("manual cache reload completed").await;
                    }
                }
                _ = sweep_signal.recv() => {
                    info!("received manual reconciliation signal");
                    runtime
                        .reconcile
                        .record_notice("received manual nightly reconciliation signal")
                        .await;
                    runtime.reconcile.request_run(ReconcileMode::Full).await;
                }
            }
        }
    });
}
