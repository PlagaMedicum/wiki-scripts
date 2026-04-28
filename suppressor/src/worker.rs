use std::sync::Arc;

use anyhow::{Context, Result};
use metrics::{counter, gauge, histogram};
use tokio::sync::mpsc;
use tracing::{error, info};

use crate::auth::{authenticate, refresh_csrf_token};
use crate::mw_api::{classify_api_failure, is_fatal_auth_or_permission_error};
use crate::runtime::{AppRuntime, RevDelAction};
use crate::state::{ProcessedRevidsState, save_json_atomic};

pub async fn run_worker(runtime: Arc<AppRuntime>, mut rx: mpsc::Receiver<RevDelAction>) {
    while let Some(mut action) = rx.recv().await {
        let start = std::time::Instant::now();
        if let Some(observed_at) = action.observed_at {
            let elapsed_ms = (chrono::Utc::now() - observed_at).num_milliseconds().max(0) as f64;
            histogram!("event_observed_to_api_submit_latency_ms").record(elapsed_ms);
        }
        histogram!("event_to_api_submit_latency_ms")
            .record(action.enqueued_at.elapsed().as_millis() as f64);
        runtime
            .queue_depth
            .fetch_sub(1, std::sync::atomic::Ordering::SeqCst);
        gauge!("queue_depth").set(
            runtime
                .queue_depth
                .load(std::sync::atomic::Ordering::SeqCst) as f64,
        );
        counter!("revdel_attempt_total").increment(action.revids.len() as u64);
        let result = if runtime.dry_run {
            info!(
                title = %action.title,
                revids = ?action.revids,
                event_id = ?action.event_id,
                mode = ?action.mode,
                "dry-run: would hide user/comment"
            );
            Ok(())
        } else {
            let retry = runtime.config.retry.clone();
            let reason = runtime.config.revdel.reason.clone();
            let mut csrf = runtime.auth.read().await.csrf_token.clone();
            let client = runtime.client.clone();
            let auth_lock = Arc::clone(&runtime.auth);
            client
                .revision_delete_with_retry(
                    &action.revids,
                    &reason,
                    &mut csrf,
                    &retry,
                    {
                        let client = client.clone();
                        let env = runtime.env.clone();
                        move || {
                            let client = client.clone();
                            let env = env.clone();
                            let auth_lock = Arc::clone(&auth_lock);
                            async move {
                                let auth = authenticate(&client, &env)
                                    .await
                                    .context("re-login failed")?;
                                let csrf = auth.csrf_token.clone();
                                *auth_lock.write().await = auth;
                                Ok(csrf)
                            }
                        }
                    },
                    {
                        let client = client.clone();
                        let auth_lock = Arc::clone(&runtime.auth);
                        move || {
                            let client = client.clone();
                            let auth_lock = Arc::clone(&auth_lock);
                            async move {
                                let csrf = refresh_csrf_token(&client)
                                    .await
                                    .context("CSRF refresh failed")?;
                                auth_lock.write().await.csrf_token = csrf.clone();
                                Ok(csrf)
                            }
                        }
                    },
                )
                .await
        };

        match result {
            Ok(()) => {
                counter!("revdel_success_total").increment(action.revids.len() as u64);
                histogram!("immediate_hide_latency_ms").record(start.elapsed().as_millis() as f64);
                if let Some(observed_at) = action.observed_at {
                    let elapsed_ms =
                        (chrono::Utc::now() - observed_at).num_milliseconds().max(0) as f64;
                    histogram!("event_observed_to_hide_latency_ms").record(elapsed_ms);
                }
                info!(
                    title = %action.title,
                    revids = ?action.revids,
                    event_id = ?action.event_id,
                    mode = ?action.mode,
                    latency_ms = start.elapsed().as_millis(),
                    "revisiondelete succeeded"
                );
                if !runtime.dry_run {
                    let mut processed = runtime.processed.write().await;
                    persist_processed_revids(
                        &mut processed,
                        &runtime.paths.processed_revids_file,
                        &action.revids,
                    )
                    .ok();
                }
                runtime
                    .record_action_completed(&action, "hidden", None, 1)
                    .await;
                if let Some(completion_tx) = action.completion_tx.take() {
                    let _ = completion_tx.send(Ok(()));
                }
            }
            Err(error) => {
                counter!("revdel_failure_total").increment(action.revids.len() as u64);
                let fatal = is_fatal_auth_or_permission_error(&error);
                let failure = classify_api_failure(
                    &error,
                    "revisiondelete",
                    Some(&action.title),
                    action.revids.first().copied(),
                );
                let reason_code = failure
                    .api_code
                    .clone()
                    .or_else(|| Some(failure.class.clone()));
                error!(
                    title = %action.title,
                    revids = ?action.revids,
                    event_id = ?action.event_id,
                    mode = ?action.mode,
                    latency_ms = start.elapsed().as_millis(),
                    error = %error,
                    "revisiondelete failed"
                );
                if fatal {
                    runtime.record_api_failure(failure).await;
                    runtime
                        .record_action_completed(&action, "blocked", reason_code, 1)
                        .await;
                    if let Some(completion_tx) = action.completion_tx.take() {
                        let _ = completion_tx.send(Err(error.to_string()));
                    }
                    error!("fatal auth/permission failure during revisiondelete; exiting");
                    std::process::exit(1);
                } else {
                    runtime.record_api_failure(failure).await;
                    runtime
                        .record_action_completed(&action, "failed", reason_code, 1)
                        .await;
                    if let Some(completion_tx) = action.completion_tx.take() {
                        let _ = completion_tx.send(Err(error.to_string()));
                    }
                }
            }
        }
    }
}

fn persist_processed_revids(
    processed: &mut ProcessedRevidsState,
    path: &std::path::Path,
    revids: &[u64],
) -> Result<()> {
    if processed.capacity == 0 {
        processed.capacity = 50_000;
    }
    for revid in revids {
        processed.insert(*revid);
    }
    save_json_atomic(path, processed)
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;

    #[test]
    fn persists_processed_revids_after_batch() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("processed.json");
        let mut processed = ProcessedRevidsState {
            capacity: 3,
            revids: vec![10],
        };

        persist_processed_revids(&mut processed, &path, &[20, 30, 40]).unwrap();

        let saved: ProcessedRevidsState = crate::state::load_json(&path).unwrap().unwrap();
        assert_eq!(processed.revids, vec![20, 30, 40]);
        assert_eq!(saved.revids, vec![20, 30, 40]);
    }
}
