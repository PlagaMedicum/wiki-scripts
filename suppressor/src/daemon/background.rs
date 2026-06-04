use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use tokio::sync::{RwLock, mpsc};
use tracing::warn;

use crate::auth::{AuthState, authenticate, refresh_csrf_token};
use crate::cache::{
    CacheRefreshMode, RuntimeCache, SourceRefreshFollowup, SourceRefreshTriggerKind,
    plan_source_refresh_catchup, refresh_cache,
};
use crate::config::{AppConfig, EnvConfig, RuntimePaths};
use crate::daemon::persistence_for;
use crate::daemon_backlog::{HideTarget, is_terminal_hide_failure};
use crate::mw_api::{MediaWikiClient, classify_api_failure};
use crate::reconcile::revisiondelete_batch_limit;
use crate::state::{ApiFailureSnapshot, SourceListRefresh};
use suppressor_core::titles::normalize_title;

#[derive(Debug)]
pub(super) enum BackgroundTask {
    SourceRefresh {
        title: String,
        trigger_revid: Option<u64>,
        trigger_kind: SourceRefreshTriggerKind,
        refresh_mode: CacheRefreshMode,
    },
    HistorySweep {
        title: String,
        processed_revids: Vec<u64>,
    },
    RecentWindow {
        start: DateTime<Utc>,
        end: DateTime<Utc>,
        source_label: String,
        processed_revids: Vec<u64>,
    },
}

#[derive(Debug)]
pub(super) enum BackgroundEvent {
    TaskStarted(String),
    TaskFinished,
    HistorySweepFinished(String),
    SourceRefreshCompleted {
        refresh: SourceListRefresh,
        added_titles: Vec<String>,
        run_recent_window: bool,
    },
    HideSucceeded {
        target: HideTarget,
        outcome: &'static str,
    },
    HideFailed {
        target: HideTarget,
        failure: ApiFailureSnapshot,
    },
    TaskFailed {
        operation: &'static str,
        failure: ApiFailureSnapshot,
    },
}

#[derive(Default)]
pub(super) struct PriorityGate {
    high_priority_active: AtomicUsize,
}

pub(super) struct HighPriorityGuard {
    gate: Arc<PriorityGate>,
}

impl PriorityGate {
    pub(super) fn begin_high_priority(self: &Arc<Self>) -> HighPriorityGuard {
        self.high_priority_active.fetch_add(1, Ordering::AcqRel);
        HighPriorityGuard {
            gate: Arc::clone(self),
        }
    }

    pub(super) fn high_priority_active_count(&self) -> usize {
        self.high_priority_active.load(Ordering::Acquire)
    }

    async fn wait_for_high_priority_idle(&self) {
        while self.high_priority_active.load(Ordering::Acquire) > 0 {
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    }
}

impl Drop for HighPriorityGuard {
    fn drop(&mut self) {
        self.gate
            .high_priority_active
            .fetch_sub(1, Ordering::AcqRel);
    }
}

pub(super) struct BackgroundWorker {
    pub(super) config: AppConfig,
    pub(super) paths: RuntimePaths,
    pub(super) env: EnvConfig,
    pub(super) client: MediaWikiClient,
    pub(super) auth: AuthState,
    pub(super) cache: Arc<RwLock<RuntimeCache>>,
    pub(super) dry_run: bool,
    pub(super) priority_gate: Arc<PriorityGate>,
    pub(super) task_rx: mpsc::Receiver<BackgroundTask>,
    pub(super) event_tx: mpsc::Sender<BackgroundEvent>,
}

pub(super) fn spawn_background_worker(mut worker: BackgroundWorker) {
    tokio::spawn(async move {
        while let Some(task) = worker.task_rx.recv().await {
            worker.run_task(task).await;
        }
    });
}

impl BackgroundWorker {
    async fn run_task(&mut self, task: BackgroundTask) {
        match task {
            BackgroundTask::SourceRefresh {
                title,
                trigger_revid,
                trigger_kind,
                refresh_mode,
            } => {
                let label = format!("source refresh: {title}");
                self.send_event(BackgroundEvent::TaskStarted(label)).await;
                self.run_source_refresh(title, trigger_revid, trigger_kind, refresh_mode)
                    .await;
                self.send_event(BackgroundEvent::TaskFinished).await;
            }
            BackgroundTask::HistorySweep {
                title,
                processed_revids,
            } => {
                let label = format!("history sweep: {title}");
                self.send_event(BackgroundEvent::TaskStarted(label)).await;
                self.run_history_sweep(title.clone(), processed_revids)
                    .await;
                self.send_event(BackgroundEvent::HistorySweepFinished(title))
                    .await;
            }
            BackgroundTask::RecentWindow {
                start,
                end,
                source_label,
                processed_revids,
            } => {
                let label = format!("{source_label}: recentchanges window");
                self.send_event(BackgroundEvent::TaskStarted(label)).await;
                self.run_recent_window(start, end, source_label, processed_revids)
                    .await;
                self.send_event(BackgroundEvent::TaskFinished).await;
            }
        }
    }

    async fn run_source_refresh(
        &mut self,
        title: String,
        trigger_revid: Option<u64>,
        trigger_kind: SourceRefreshTriggerKind,
        refresh_mode: CacheRefreshMode,
    ) {
        let started_at = Utc::now();
        let before = self.cache.read().await.snapshot.clone();
        match refresh_cache(
            &self.cache,
            &self.client,
            &self.config,
            &self.paths,
            refresh_mode,
            persistence_for(self.dry_run),
        )
        .await
        {
            Ok(refreshed) => {
                let after = self.cache.read().await.snapshot.clone();
                let catchup_plan = plan_source_refresh_catchup(
                    &before,
                    &after,
                    trigger_kind,
                    self.config.catchup.source_refresh_title_scope_limit,
                );
                let added_titles = match &catchup_plan.followup {
                    SourceRefreshFollowup::TitleScoped { titles, .. } => titles.clone(),
                    SourceRefreshFollowup::RecentWindow { .. } => Vec::new(),
                    SourceRefreshFollowup::None => Vec::new(),
                };
                let run_recent_window = matches!(
                    catchup_plan.followup,
                    SourceRefreshFollowup::RecentWindow { .. }
                );
                let refresh = SourceListRefresh {
                    trigger_title: title,
                    trigger_revid,
                    started_at: Some(started_at),
                    completed_at: Some(Utc::now()),
                    old_source_revid: before.source_lastrevid,
                    new_source_revid: after.source_lastrevid,
                    new_titles_count: catchup_plan.new_titles_count,
                    removed_titles_count: catchup_plan.removed_titles_count,
                    redirects_reused: catchup_plan.redirects_reused,
                    catchup_triggered: catchup_plan.catchup_requested(),
                    catchup_title_scope: catchup_plan.catchup_scope_label().map(str::to_string),
                    outcome: if catchup_plan.catchup_requested() {
                        "catchup-started".to_string()
                    } else if refreshed {
                        "refreshed".to_string()
                    } else {
                        "unchanged".to_string()
                    },
                    ..SourceListRefresh::default()
                };
                self.send_event(BackgroundEvent::SourceRefreshCompleted {
                    refresh,
                    added_titles,
                    run_recent_window,
                })
                .await;
            }
            Err(error) => {
                let failure =
                    classify_api_failure(&error, "source-refresh", Some(&title), trigger_revid);
                let refresh = SourceListRefresh {
                    trigger_title: title,
                    trigger_revid,
                    started_at: Some(started_at),
                    completed_at: Some(Utc::now()),
                    old_source_revid: before.source_lastrevid,
                    new_source_revid: before.source_lastrevid,
                    outcome: "refresh-failed".to_string(),
                    error: Some(failure),
                    ..SourceListRefresh::default()
                };
                self.send_event(BackgroundEvent::SourceRefreshCompleted {
                    refresh,
                    added_titles: Vec::new(),
                    run_recent_window: false,
                })
                .await;
            }
        }
    }

    async fn run_history_sweep(&mut self, title: String, processed_revids: Vec<u64>) {
        let revisions = match self.client.fetch_revisions(&title, None).await {
            Ok(revisions) => revisions,
            Err(error) => {
                self.send_task_failure("history-sweep", &error, Some(&title), None)
                    .await;
                return;
            }
        };
        let mut to_hide = Vec::new();
        for revision in revisions.into_iter().rev() {
            if processed_revids.contains(&revision.revid) {
                continue;
            }
            if revision.user_hidden && revision.comment_hidden {
                self.send_event(BackgroundEvent::HideSucceeded {
                    target: HideTarget {
                        title: title.clone(),
                        revid: revision.revid,
                        observed_at: Some(revision.timestamp),
                        source_label: "source-list-history".to_string(),
                    },
                    outcome: "already-hidden",
                })
                .await;
                continue;
            }
            to_hide.push(HideTarget {
                title: title.clone(),
                revid: revision.revid,
                observed_at: Some(revision.timestamp),
                source_label: "source-list-history".to_string(),
            });
        }
        let batch_limit = revisiondelete_batch_limit(self.auth.has_high_limits());
        for batch in to_hide.chunks(batch_limit) {
            self.priority_gate.wait_for_high_priority_idle().await;
            self.hide_background_batch(batch).await;
        }
    }

    async fn run_recent_window(
        &mut self,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
        source_label: String,
        processed_revids: Vec<u64>,
    ) {
        let window = match self
            .client
            .fetch_recent_changes_in_window(start, end, self.config.catchup.max_revisions_per_run)
            .await
        {
            Ok(window) => window,
            Err(error) => {
                self.send_task_failure("recent-window", &error, None, None)
                    .await;
                return;
            }
        };
        let watched = self.cache.read().await.watched_set.clone();
        let mut changes = window.changes;
        changes.sort_by_key(|change| (change.timestamp, change.revid));
        for change in changes {
            if processed_revids.contains(&change.revid)
                || !watched.contains(&normalize_title(&change.title))
            {
                continue;
            }
            self.priority_gate.wait_for_high_priority_idle().await;
            self.hide_background_revision(HideTarget {
                title: change.title,
                revid: change.revid,
                observed_at: Some(change.timestamp),
                source_label: source_label.clone(),
            })
            .await;
        }
        if window.truncated {
            let failure = ApiFailureSnapshot {
                class: "recentchanges-limit".to_string(),
                retryable: true,
                operation: "recent-window".to_string(),
                message: "recentchanges window hit the configured revision limit".to_string(),
                occurred_at: Some(Utc::now()),
                ..ApiFailureSnapshot::default()
            };
            self.send_event(BackgroundEvent::TaskFailed {
                operation: "manual-recovery",
                failure,
            })
            .await;
        }
    }

    async fn hide_background_revision(&mut self, target: HideTarget) {
        self.hide_single_background_revision(target).await;
    }

    async fn submit_revisiondelete(&mut self, revids: &[u64]) -> Result<()> {
        let mut csrf = self.auth.csrf_token.clone();
        self.client
            .revision_delete_with_retry(
                revids,
                &self.config.revdel.reason,
                &mut csrf,
                &self.config.retry,
                {
                    let client = self.client.clone();
                    let env = self.env.clone();
                    move || {
                        let client = client.clone();
                        let env = env.clone();
                        async move {
                            let auth = authenticate(&client, &env)
                                .await
                                .context("background re-login failed")?;
                            Ok(auth.csrf_token)
                        }
                    }
                },
                {
                    let client = self.client.clone();
                    move || {
                        let client = client.clone();
                        async move {
                            refresh_csrf_token(&client)
                                .await
                                .context("background CSRF refresh failed")
                        }
                    }
                },
            )
            .await?;
        self.auth.csrf_token = csrf;
        Ok(())
    }

    async fn hide_background_batch(&mut self, targets: &[HideTarget]) {
        if targets.is_empty() {
            return;
        }
        if self.dry_run {
            for target in targets {
                self.send_event(BackgroundEvent::HideSucceeded {
                    target: target.clone(),
                    outcome: "dry-run",
                })
                .await;
            }
            return;
        }
        let revids = targets
            .iter()
            .map(|target| target.revid)
            .collect::<Vec<_>>();
        let result = self.submit_revisiondelete(&revids).await;
        match result {
            Ok(()) => {
                for target in targets {
                    self.send_event(BackgroundEvent::HideSucceeded {
                        target: target.clone(),
                        outcome: "hidden",
                    })
                    .await;
                }
            }
            Err(error) => {
                if targets.len() > 1 {
                    for target in targets {
                        self.hide_single_background_revision(target.clone()).await;
                    }
                    return;
                }
                let target = targets
                    .first()
                    .expect("empty targets returned before revisiondelete");
                let failure = classify_api_failure(
                    &error,
                    "revisiondelete",
                    Some(&target.title),
                    Some(target.revid),
                );
                if is_terminal_hide_failure(&failure)
                    && let Ok(Some(revision)) = self.client.fetch_revision_by_id(target.revid).await
                    && revision.user_hidden
                    && revision.comment_hidden
                {
                    self.send_event(BackgroundEvent::HideSucceeded {
                        target: target.clone(),
                        outcome: "already-hidden-after-terminal-failure",
                    })
                    .await;
                    return;
                }
                self.send_event(BackgroundEvent::HideFailed {
                    target: target.clone(),
                    failure,
                })
                .await;
            }
        }
    }

    async fn hide_single_background_revision(&mut self, target: HideTarget) {
        if self.dry_run {
            self.send_event(BackgroundEvent::HideSucceeded {
                target,
                outcome: "dry-run",
            })
            .await;
            return;
        }
        match self.submit_revisiondelete(&[target.revid]).await {
            Ok(()) => {
                self.send_event(BackgroundEvent::HideSucceeded {
                    target,
                    outcome: "hidden",
                })
                .await;
            }
            Err(error) => {
                let failure = classify_api_failure(
                    &error,
                    "revisiondelete",
                    Some(&target.title),
                    Some(target.revid),
                );
                if is_terminal_hide_failure(&failure)
                    && let Ok(Some(revision)) = self.client.fetch_revision_by_id(target.revid).await
                    && revision.user_hidden
                    && revision.comment_hidden
                {
                    self.send_event(BackgroundEvent::HideSucceeded {
                        target,
                        outcome: "already-hidden-after-terminal-failure",
                    })
                    .await;
                    return;
                }
                self.send_event(BackgroundEvent::HideFailed { target, failure })
                    .await;
            }
        }
    }

    async fn send_task_failure(
        &self,
        operation: &'static str,
        error: &anyhow::Error,
        sample_title: Option<&str>,
        sample_revid: Option<u64>,
    ) {
        let failure = classify_api_failure(error, operation, sample_title, sample_revid);
        self.send_event(BackgroundEvent::TaskFailed { operation, failure })
            .await;
    }

    async fn send_event(&self, event: BackgroundEvent) {
        if let Err(error) = self.event_tx.send(event).await {
            warn!(error = %error, "failed to send background daemon event");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn priority_gate_counts_active_high_priority_work() {
        let gate = Arc::new(PriorityGate::default());
        assert_eq!(gate.high_priority_active_count(), 0);
        let first = gate.begin_high_priority();
        let second = gate.begin_high_priority();
        assert_eq!(gate.high_priority_active_count(), 2);
        drop(first);
        assert_eq!(gate.high_priority_active_count(), 1);
        drop(second);
        assert_eq!(gate.high_priority_active_count(), 0);
    }

    #[tokio::test]
    async fn low_priority_waits_until_high_priority_work_finishes() {
        let gate = Arc::new(PriorityGate::default());
        let guard = gate.begin_high_priority();

        let waiting = tokio::time::timeout(
            Duration::from_millis(10),
            gate.wait_for_high_priority_idle(),
        )
        .await;
        assert!(waiting.is_err());

        drop(guard);
        tokio::time::timeout(
            Duration::from_millis(100),
            gate.wait_for_high_priority_idle(),
        )
        .await
        .expect("low-priority wait should finish after high-priority work drops");
    }
}
