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
                    runtime
                        .reconcile
                        .record_notice(
                            "reload watched pages requested; realtime protection is unchanged while the cache refresh runs",
                        )
                        .await;
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
                            .record_notice(format!("reload watched pages failed: {error}"))
                            .await;
                        warn!("manual cache reload failed: {error:#}");
                    } else {
                        runtime
                            .reconcile
                            .record_notice(
                                "reload watched pages completed; see the source refresh row for title changes and catch-up state",
                            )
                            .await;
                    }
                }
                _ = sweep_signal.recv() => {
                    info!("received manual reconciliation signal");
                    runtime
                        .reconcile
                        .record_notice(
                            "full watched-set recheck requested; this is fallback verification, not the primary realtime path",
                        )
                        .await;
                    runtime.reconcile.request_run(ReconcileMode::Full).await;
                }
            }
        }
    });
}
