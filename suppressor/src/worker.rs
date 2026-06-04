use std::sync::Arc;

use anyhow::{Context, Result};
use metrics::{counter, histogram};
use tokio::sync::mpsc;
use tracing::{error, info};

use crate::auth::{authenticate, refresh_csrf_token};
use crate::catchup::run_default_catchup;
use crate::mw_api::{classify_api_failure, is_fatal_auth_or_permission_error};
use crate::runtime::{AppRuntime, DispatchCompletion, ExecutionLaneKind, RevDelAction, RevDelMode};
use crate::state::{ProcessedRevidsState, save_json_atomic};

const LIVE_BLOCKED_RETRY_SECONDS: u64 = 30;

#[cfg(test)]
pub async fn run_worker(runtime: Arc<AppRuntime>, rx: mpsc::Receiver<RevDelAction>) {
    run_worker_for_lane(runtime, ExecutionLaneKind::Live, rx).await;
}

pub async fn run_worker_for_lane(
    runtime: Arc<AppRuntime>,
    lane_kind: ExecutionLaneKind,
    mut rx: mpsc::Receiver<RevDelAction>,
) {
    while let Some(mut action) = rx.recv().await {
        let start = std::time::Instant::now();
        if lane_kind == ExecutionLaneKind::Live
            && let Some(observed_at) = action.observed_at
        {
            let elapsed_ms = (chrono::Utc::now() - observed_at).num_milliseconds().max(0) as f64;
            histogram!("event_observed_to_api_submit_latency_ms").record(elapsed_ms);
        }
        histogram!("event_to_api_submit_latency_ms")
            .record(action.enqueued_at.elapsed().as_millis() as f64);
        action.lane = lane_kind;
        runtime.record_action_submitted(&mut action).await;
        if action
            .deadline_at
            .is_some_and(|deadline_at| deadline_at <= chrono::Utc::now())
        {
            runtime
                .record_action_completed(
                    &action,
                    "retrying",
                    Some("deadline-exceeded".to_string()),
                    1,
                )
                .await;
            spawn_live_failure_catchup_if_needed(&runtime, &action);
            if let Some(completion_tx) = action.completion_tx.take() {
                let _ = completion_tx.send(Err("live action deadline exceeded".to_string()));
            }
            continue;
        }
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
            let request = client.revision_delete_with_retry(
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
            );
            if action.lane == ExecutionLaneKind::Live {
                if let Some(deadline_at) = action.deadline_at {
                    let remaining = (deadline_at - chrono::Utc::now())
                        .to_std()
                        .unwrap_or_else(|_| std::time::Duration::from_millis(0));
                    match tokio::time::timeout(remaining, request).await {
                        Ok(result) => result,
                        Err(_) => Err(anyhow::anyhow!("live action deadline exceeded")),
                    }
                } else {
                    request.await
                }
            } else {
                request.await
            }
        };

        match result {
            Ok(()) => {
                counter!("revdel_success_total").increment(action.revids.len() as u64);
                histogram!("immediate_hide_latency_ms").record(start.elapsed().as_millis() as f64);
                info!(
                    title = %action.title,
                    revids = ?action.revids,
                    event_id = ?action.event_id,
                    mode = ?action.mode,
                    latency_ms = start.elapsed().as_millis(),
                    "revisiondelete succeeded"
                );
                if !runtime.dry_run {
                    let persistence_failure = {
                        let mut processed = runtime.processed.write().await;
                        persist_processed_revids(
                            &mut processed,
                            &runtime.paths.processed_revids_file,
                            &action.revids,
                        )
                        .err()
                    };
                    if let Some(error) = persistence_failure {
                        runtime
                            .record_state_persistence_failure(
                                "processed_revids".to_string(),
                                runtime.paths.processed_revids_file.display().to_string(),
                                error.to_string(),
                            )
                            .await;
                    }
                }
                runtime
                    .record_action_completed(&action, "hidden", None, 1)
                    .await;
                if let Some(completion_tx) = action.completion_tx.take() {
                    let _ = completion_tx.send(Ok(DispatchCompletion::Hidden));
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
                let deadline_exceeded = error.to_string().contains("live action deadline exceeded");
                let reason_code = if deadline_exceeded {
                    Some("deadline-exceeded".to_string())
                } else if fatal {
                    Some(failure.class.clone())
                } else {
                    failure
                        .api_code
                        .clone()
                        .or_else(|| Some(failure.class.clone()))
                };
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
                    error!(
                        "fatal auth/permission failure during revisiondelete; protection blocked"
                    );
                    spawn_live_failure_catchup_after_delay_if_needed(
                        &runtime,
                        &action,
                        std::time::Duration::from_secs(LIVE_BLOCKED_RETRY_SECONDS),
                    );
                } else {
                    let outcome = if deadline_exceeded
                        || (failure.retryable && failure.retry_after_seconds.is_some())
                    {
                        "retrying"
                    } else {
                        "failed"
                    };
                    runtime.record_api_failure(failure).await;
                    runtime
                        .record_action_completed(&action, outcome, reason_code, 1)
                        .await;
                    spawn_live_failure_catchup_if_needed(&runtime, &action);
                    if let Some(completion_tx) = action.completion_tx.take() {
                        let _ = completion_tx.send(Err(error.to_string()));
                    }
                }
            }
        }
    }
}

fn spawn_live_failure_catchup_if_needed(runtime: &Arc<AppRuntime>, action: &RevDelAction) {
    spawn_live_failure_catchup_after_delay_if_needed(runtime, action, std::time::Duration::ZERO);
}

fn spawn_live_failure_catchup_after_delay_if_needed(
    runtime: &Arc<AppRuntime>,
    action: &RevDelAction,
    delay: std::time::Duration,
) {
    if action.mode != RevDelMode::Live {
        return;
    }
    let runtime = Arc::clone(runtime);
    tokio::spawn(async move {
        if !delay.is_zero() {
            tokio::time::sleep(delay).await;
        }
        let trigger = "live-failure".to_string();
        if !runtime.should_start_recovery(&trigger).await {
            return;
        }
        if let Err(error) = run_default_catchup(&runtime, trigger.clone()).await {
            let error = error.context("bounded catch-up failed after live hide failure");
            runtime
                .mark_recovery_failed(trigger, "catchup-failed".to_string(), error.to_string())
                .await;
        }
    });
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
    use std::sync::Arc;

    use chrono::{TimeDelta, Utc};
    use tempfile::tempdir;
    use tokio::sync::oneshot;
    use tokio::time::{Duration, timeout};

    use super::*;
    use crate::config::EnvConfig;
    use crate::metrics::snapshot_runtime_latency_metrics;
    use crate::runtime::{
        ExecutionLaneKind, RevDelDispatch, RevDelMode, RuntimeStatusSurfaceMode,
        build_test_runtime_harness, build_test_runtime_harness_with_env_and_dry_run,
    };
    use wiremock::matchers::{body_string_contains, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

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

    #[tokio::test]
    async fn worker_marks_live_action_hidden_and_updates_last_successful_hide() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let runtime = Arc::clone(&harness.runtime);
        let runtime_status = Arc::clone(&harness.runtime_status);
        let worker = tokio::spawn(run_worker(Arc::clone(&runtime), harness.work_rx));
        let observed_at = Utc::now() - TimeDelta::seconds(2);
        let (completion_tx, completion_rx) = oneshot::channel();
        runtime
            .mark_recentchanges_poll_succeeded(
                Some(Utc::now() - TimeDelta::milliseconds(250)),
                "recentchanges poll completed".to_string(),
            )
            .await;

        runtime
            .reconcile
            .actions
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![0],
                event_id: Some("evt-0".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(observed_at),
                recovery_trigger: None,
                completion_tx: Some(completion_tx),
            })
            .await
            .unwrap();

        let completion = timeout(Duration::from_secs(1), completion_rx)
            .await
            .unwrap();
        assert!(completion.unwrap().is_ok());

        let status = runtime_status.lock().await.clone();
        let latest_outcome = status.realtime.latest_outcome.as_ref().unwrap();

        assert_eq!(status.realtime.state, "healthy");
        assert_eq!(status.realtime.queue_depth, 0);
        assert_eq!(
            status.realtime.last_successful_hide_title.as_deref(),
            Some("Foo")
        );
        assert_eq!(status.realtime.last_successful_hide_revid, Some(0));
        assert_eq!(
            status.realtime.last_successful_hide_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/0")
        );
        assert_eq!(status.realtime.last_successful_hide_at, Some(observed_at));
        assert_eq!(latest_outcome.outcome, "hidden");
        assert_eq!(latest_outcome.mode, RevDelMode::Live.label());
        assert_eq!(latest_outcome.source_label, RevDelMode::Live.source_label());
        assert_eq!(
            latest_outcome.revision_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/0")
        );
        assert_eq!(latest_outcome.observed_at, Some(observed_at));
        assert!(latest_outcome.completed_at.is_some());
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("idle")
        );

        let latency = snapshot_runtime_latency_metrics();
        assert!(latency.observed_to_queue.sample_count >= 1);
        assert!(latency.observed_to_queue.latest_ms.unwrap() >= 1_000);
        assert!(latency.observed_to_hide.sample_count >= 1);
        assert!(latency.observed_to_hide.latest_ms.unwrap() >= 1_000);

        worker.abort();
    }

    #[tokio::test]
    async fn worker_defers_expired_live_action_deadline_without_api_wait() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let runtime = Arc::clone(&harness.runtime);
        let (completion_tx, completion_rx) = oneshot::channel();

        runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![77],
                event_id: Some("evt-77".to_string()),
                user: Some("SyntheticOperator".to_string()),
                comment: Some("synthetic edit".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now() - TimeDelta::seconds(1)),
                recovery_trigger: None,
                completion_tx: Some(completion_tx),
            })
            .await
            .unwrap();
        let mut action = harness.work_rx.try_recv().unwrap();
        action.deadline_at = Some(Utc::now() - TimeDelta::seconds(1));
        let (tx, rx) = mpsc::channel(1);
        tx.send(action).await.unwrap();
        drop(tx);

        let worker = tokio::spawn(run_worker_for_lane(
            Arc::clone(&runtime),
            ExecutionLaneKind::Live,
            rx,
        ));
        let completion = timeout(Duration::from_secs(1), completion_rx)
            .await
            .unwrap()
            .unwrap();
        assert!(completion.unwrap_err().contains("deadline exceeded"));

        let status = harness.runtime_status.lock().await.clone();
        let outcome = status.realtime.latest_outcome.as_ref().unwrap();
        assert_eq!(status.realtime.state, "catching-up");
        assert_eq!(status.realtime.live_lane.queue_depth, 0);
        assert_eq!(status.realtime.live_lane.in_flight, 0);
        assert_eq!(outcome.outcome, "retrying");
        assert_eq!(outcome.reason_code.as_deref(), Some("deadline-exceeded"));
        assert_eq!(outcome.lane.as_deref(), Some("live"));

        worker.await.unwrap();
    }

    #[tokio::test]
    async fn worker_blocks_permission_failure_without_exiting_process() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("ids=91"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"permissiondenied","info":"synthetic denied"}}"#,
                "application/json",
            ))
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = EnvConfig {
            api_url: format!("{}/w/api.php", server.uri()),
            stream_url: "https://example.invalid/stream".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "pw".to_string(),
            user_agent: "bewiki-test/1.0".to_string(),
            env_file: temp.path().join(".env"),
        };
        let harness = build_test_runtime_harness_with_env_and_dry_run(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
            false,
        );
        let runtime = Arc::clone(&harness.runtime);
        let worker = tokio::spawn(run_worker_for_lane(
            Arc::clone(&runtime),
            ExecutionLaneKind::Live,
            harness.work_rx,
        ));
        let (completion_tx, completion_rx) = oneshot::channel();

        runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![91],
                event_id: Some("evt-91".to_string()),
                user: Some("SyntheticOperator".to_string()),
                comment: Some("synthetic edit".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now()),
                recovery_trigger: None,
                completion_tx: Some(completion_tx),
            })
            .await
            .unwrap();

        let completion = timeout(Duration::from_secs(2), completion_rx)
            .await
            .unwrap()
            .unwrap();
        assert!(completion.unwrap_err().contains("Permission failure"));

        let status = harness.runtime_status.lock().await.clone();
        let outcome = status.realtime.latest_outcome.as_ref().unwrap();
        assert_eq!(status.realtime.state, "blocked");
        assert_eq!(outcome.outcome, "blocked");
        assert_eq!(outcome.reason_code.as_deref(), Some("permission"));
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("live-hide")
        );

        worker.abort();
    }

    #[tokio::test]
    async fn background_permission_failure_surfaces_reconciliation_source() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("ids=92"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"permissiondenied","info":"synthetic denied"}}"#,
                "application/json",
            ))
            .mount(&server)
            .await;

        let temp = tempdir().unwrap();
        let env = EnvConfig {
            api_url: format!("{}/w/api.php", server.uri()),
            stream_url: "https://example.invalid/stream".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "pw".to_string(),
            user_agent: "bewiki-test/1.0".to_string(),
            env_file: temp.path().join(".env"),
        };
        let harness = build_test_runtime_harness_with_env_and_dry_run(
            &temp,
            RuntimeStatusSurfaceMode::DetachedCommand,
            env,
            false,
        );
        let runtime = Arc::clone(&harness.runtime);
        let worker = tokio::spawn(run_worker_for_lane(
            Arc::clone(&runtime),
            ExecutionLaneKind::Background,
            harness.background_work_rx,
        ));
        let (completion_tx, completion_rx) = oneshot::channel();

        runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![92],
                event_id: Some("evt-92".to_string()),
                user: Some("SyntheticOperator".to_string()),
                comment: Some("synthetic edit".to_string()),
                mode: RevDelMode::Reconciliation,
                observed_at: Some(Utc::now()),
                recovery_trigger: None,
                completion_tx: Some(completion_tx),
            })
            .await
            .unwrap();

        let completion = timeout(Duration::from_secs(2), completion_rx)
            .await
            .unwrap()
            .unwrap();
        assert!(completion.unwrap_err().contains("Permission failure"));

        let status = harness.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "blocked");
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("reconciliation")
        );

        worker.abort();
    }
}
