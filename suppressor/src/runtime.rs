use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use metrics::gauge;
use tokio::sync::{RwLock, mpsc, oneshot};
use tracing::{info, warn};

use crate::auth::{AuthState, authenticate};
use crate::cache::{CachePersistence, RuntimeCache, load_or_bootstrap};
use crate::config::{AppConfig, EnvConfig, RuntimePaths, init_logging, load_env};
use crate::locks::{KeyLockGuard, KeyLockSet};
use crate::metrics::init_metrics;
use crate::mw_api::MediaWikiClient;
use crate::reconcile::{
    ReconcileCoordinator, ReconcileMode, reconciliation_loop, revisiondelete_batch_limit,
};
use crate::state::{
    ApiFailureSnapshot, CoverageSummary, NightlySweepProgress, ProcessedRevidsState, RuntimeStatus,
    SourceListRefresh, SuppressionOutcomeSnapshot, load_json, save_json_atomic,
};

#[derive(Clone, Copy, Debug)]
pub enum RevDelMode {
    Live,
    Catchup,
    Coverage,
    Reconciliation,
    Manual,
}

impl RevDelMode {
    pub fn label(self) -> &'static str {
        match self {
            RevDelMode::Live => "live",
            RevDelMode::Catchup => "catchup",
            RevDelMode::Coverage => "coverage",
            RevDelMode::Reconciliation => "reconciliation",
            RevDelMode::Manual => "manual",
        }
    }
}

pub struct RevDelAction {
    pub title: String,
    pub revids: Vec<u64>,
    pub event_id: Option<String>,
    pub user: Option<String>,
    pub comment: Option<String>,
    pub mode: RevDelMode,
    pub enqueued_at: Instant,
    pub observed_at: Option<DateTime<Utc>>,
    pub queued_at: DateTime<Utc>,
    pub recovery_trigger: Option<String>,
    pub completion_tx: Option<oneshot::Sender<Result<(), String>>>,
    pub _revision_guards: Vec<KeyLockGuard<u64>>,
}

pub struct RevDelDispatch {
    pub title: String,
    pub revids: Vec<u64>,
    pub event_id: Option<String>,
    pub user: Option<String>,
    pub comment: Option<String>,
    pub mode: RevDelMode,
    pub observed_at: Option<DateTime<Utc>>,
    pub recovery_trigger: Option<String>,
    pub completion_tx: Option<oneshot::Sender<Result<(), String>>>,
}

pub struct ActionDispatcher {
    revision_locks: Arc<KeyLockSet<u64>>,
    processed: Arc<RwLock<ProcessedRevidsState>>,
    queue_depth: Arc<AtomicUsize>,
    work_tx: mpsc::Sender<RevDelAction>,
    runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    runtime_status_file: PathBuf,
}

impl ActionDispatcher {
    pub fn new(
        revision_locks: Arc<KeyLockSet<u64>>,
        processed: Arc<RwLock<ProcessedRevidsState>>,
        queue_depth: Arc<AtomicUsize>,
        work_tx: mpsc::Sender<RevDelAction>,
        runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
        runtime_status_file: PathBuf,
    ) -> Self {
        Self {
            revision_locks,
            processed,
            queue_depth,
            work_tx,
            runtime_status,
            runtime_status_file,
        }
    }

    pub async fn contains_processed(&self, revid: u64) -> bool {
        self.processed.read().await.contains(revid)
    }

    pub async fn dispatch_action_batch(
        &self,
        title: String,
        revids: Vec<u64>,
        event_id: Option<String>,
        user: Option<String>,
        comment: Option<String>,
        mode: RevDelMode,
    ) -> Result<()> {
        self.dispatch_action(RevDelDispatch {
            title,
            revids,
            event_id,
            user,
            comment,
            mode,
            observed_at: None,
            recovery_trigger: None,
            completion_tx: None,
        })
        .await
    }

    pub async fn dispatch_action(&self, dispatch: RevDelDispatch) -> Result<()> {
        let RevDelDispatch {
            title,
            revids,
            event_id,
            user,
            comment,
            mode,
            observed_at,
            recovery_trigger,
            mut completion_tx,
        } = dispatch;
        let mut guards = Vec::new();
        for revid in &revids {
            let Some(guard) = self.revision_locks.try_lock(*revid) else {
                tracing::debug!(
                    revid,
                    title = %title,
                    "skipping action because revision lock is already held"
                );
                self.record_latest_outcome(SuppressionOutcomeSnapshot {
                    title: title.clone(),
                    revid: *revid,
                    outcome: "skipped".to_string(),
                    reason_code: Some("duplicate-queued".to_string()),
                    mode: mode.label().to_string(),
                    observed_at,
                    queued_at: None,
                    completed_at: None,
                    attempt_count: 0,
                })
                .await;
                if let Some(completion_tx) = completion_tx.take() {
                    let _ = completion_tx.send(Ok(()));
                }
                return Ok(());
            };
            if self.processed.read().await.contains(*revid) {
                tracing::debug!(
                    revid,
                    title = %title,
                    "skipping action because revision is already processed"
                );
                self.record_latest_outcome(SuppressionOutcomeSnapshot {
                    title: title.clone(),
                    revid: *revid,
                    outcome: "already-hidden".to_string(),
                    reason_code: Some("already-processed".to_string()),
                    mode: mode.label().to_string(),
                    observed_at,
                    queued_at: None,
                    completed_at: None,
                    attempt_count: 0,
                })
                .await;
                if let Some(completion_tx) = completion_tx.take() {
                    let _ = completion_tx.send(Ok(()));
                }
                return Ok(());
            }
            guards.push(guard);
        }
        self.queue_depth.fetch_add(1, Ordering::SeqCst);
        let depth = self.queue_depth.load(Ordering::SeqCst);
        gauge!("queue_depth").set(depth as f64);
        let queued_at = Utc::now();
        tracing::debug!(
            title = %title,
            revids = ?revids,
            event_id = ?event_id,
            mode = ?mode,
            queue_depth = depth,
            "queueing revisiondelete action"
        );
        if let Some(revid) = revids.first().copied() {
            self.record_latest_outcome(SuppressionOutcomeSnapshot {
                title: title.clone(),
                revid,
                outcome: "queued".to_string(),
                reason_code: recovery_trigger.clone(),
                mode: mode.label().to_string(),
                observed_at,
                queued_at: Some(queued_at),
                completed_at: None,
                attempt_count: 0,
            })
            .await;
        }
        self.work_tx
            .send(RevDelAction {
                title,
                revids,
                event_id,
                user,
                comment,
                mode,
                enqueued_at: Instant::now(),
                observed_at,
                queued_at,
                recovery_trigger,
                completion_tx,
                _revision_guards: guards,
            })
            .await
            .context("Failed to queue revisiondelete action")
    }

    async fn record_latest_outcome(&self, outcome: SuppressionOutcomeSnapshot) {
        let queue_depth = self.queue_depth.load(Ordering::SeqCst);
        let mut status = self.runtime_status.lock().await;
        status.realtime.queue_depth = queue_depth;
        status.realtime.last_action_queued_at =
            outcome.queued_at.or(status.realtime.last_action_queued_at);
        status.realtime.latest_notice =
            Some(format!("{} revid {}", outcome.outcome, outcome.revid));
        status.realtime.latest_outcome = Some(outcome);
        if let Err(error) = save_json_atomic(&self.runtime_status_file, &*status) {
            warn!(
                path = %self.runtime_status_file.display(),
                error = %error,
                "failed to persist runtime status"
            );
        }
    }
}

pub struct ReconciliationRuntime {
    pub config: AppConfig,
    pub client: MediaWikiClient,
    pub auth: Arc<RwLock<AuthState>>,
    pub cache: Arc<RwLock<RuntimeCache>>,
    pub progress: Arc<tokio::sync::Mutex<NightlySweepProgress>>,
    pub runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    pub page_locks: Arc<KeyLockSet<String>>,
    pub paths: RuntimePaths,
    pub dry_run: bool,
    pub actions: Arc<ActionDispatcher>,
    reconcile_coordinator: Arc<ReconcileCoordinator>,
}

pub struct ReconcilePassContext {
    pub(crate) mode: ReconcileMode,
    pub(crate) listed_titles: Vec<String>,
    pub(crate) page_concurrency: usize,
    pub(crate) timezone: String,
    pub(crate) batch_sleep_ms: u64,
    pub(crate) batch_limit: usize,
    pub(crate) persistence: CachePersistence,
    pub(crate) client: MediaWikiClient,
    pub(crate) cache: Arc<RwLock<RuntimeCache>>,
    pub(crate) progress: Arc<tokio::sync::Mutex<NightlySweepProgress>>,
    pub(crate) runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    pub(crate) page_locks: Arc<KeyLockSet<String>>,
    pub(crate) paths: RuntimePaths,
    pub(crate) actions: Arc<ActionDispatcher>,
}

pub struct ReconciliationRuntimeInit {
    config: AppConfig,
    client: MediaWikiClient,
    auth: Arc<RwLock<AuthState>>,
    cache: Arc<RwLock<RuntimeCache>>,
    progress: Arc<tokio::sync::Mutex<NightlySweepProgress>>,
    runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    page_locks: Arc<KeyLockSet<String>>,
    paths: RuntimePaths,
    dry_run: bool,
    actions: Arc<ActionDispatcher>,
}

impl ReconciliationRuntime {
    pub fn new(init: ReconciliationRuntimeInit) -> Self {
        Self {
            config: init.config,
            client: init.client,
            auth: init.auth,
            cache: init.cache,
            progress: init.progress,
            runtime_status: init.runtime_status,
            page_locks: init.page_locks,
            paths: init.paths,
            dry_run: init.dry_run,
            actions: init.actions,
            reconcile_coordinator: Arc::new(ReconcileCoordinator::default()),
        }
    }

    pub async fn update_runtime_status<F>(&self, update: F)
    where
        F: FnOnce(&mut RuntimeStatus),
    {
        let mut status = self.runtime_status.lock().await;
        update(&mut status);
        if let Err(error) = save_json_atomic(&self.paths.runtime_status_file, &*status) {
            warn!(
                path = %self.paths.runtime_status_file.display(),
                error = %error,
                "failed to persist runtime status"
            );
        }
    }

    pub async fn record_notice<S: Into<String>>(&self, notice: S) {
        let notice = notice.into();
        self.update_runtime_status(move |status| {
            status.last_notice = Some(notice);
            status.last_notice_at = Some(Utc::now());
        })
        .await;
    }

    async fn build_reconcile_pass_context(
        self: &Arc<Self>,
        mode: ReconcileMode,
    ) -> ReconcilePassContext {
        let listed_titles = {
            self.cache
                .read()
                .await
                .snapshot
                .listed_titles_normalized
                .clone()
        };
        let batch_limit = revisiondelete_batch_limit(self.auth.read().await.has_high_limits());
        ReconcilePassContext {
            mode,
            listed_titles,
            page_concurrency: self.config.nightly_sweep.page_concurrency,
            timezone: self.config.nightly_sweep.timezone.clone(),
            batch_sleep_ms: self.config.nightly_sweep.batch_sleep_ms,
            batch_limit,
            persistence: if self.dry_run {
                CachePersistence::Ephemeral
            } else {
                CachePersistence::Persist
            },
            client: self.client.clone(),
            cache: Arc::clone(&self.cache),
            progress: Arc::clone(&self.progress),
            runtime_status: Arc::clone(&self.runtime_status),
            page_locks: Arc::clone(&self.page_locks),
            paths: self.paths.clone(),
            actions: Arc::clone(&self.actions),
        }
    }
}

impl ReconcilePassContext {
    pub async fn update_runtime_status<F>(&self, update: F)
    where
        F: FnOnce(&mut RuntimeStatus),
    {
        let mut status = self.runtime_status.lock().await;
        update(&mut status);
        if let Err(error) = save_json_atomic(&self.paths.runtime_status_file, &*status) {
            warn!(
                path = %self.paths.runtime_status_file.display(),
                error = %error,
                "failed to persist runtime status"
            );
        }
    }

    pub async fn record_notice<S: Into<String>>(&self, notice: S) {
        let notice = notice.into();
        self.update_runtime_status(move |status| {
            status.last_notice = Some(notice);
            status.last_notice_at = Some(Utc::now());
        })
        .await;
    }
}

impl ReconciliationRuntime {
    pub async fn request_run(self: &Arc<Self>, mode: ReconcileMode) {
        self.reconcile_coordinator
            .request_run(Arc::clone(self), mode)
            .await;
    }

    pub async fn run_reconciliation_pass(self: &Arc<Self>, mode: ReconcileMode) -> Result<()> {
        let mode_label = mode.label().to_string();
        self.update_runtime_status(move |status| {
            status.reconciliation.active = true;
            status.reconciliation.mode = Some(mode_label);
            status.reconciliation.phase = Some("starting".to_string());
            status.reconciliation.completed_titles = 0;
            status.reconciliation.total_titles = 0;
            status.reconciliation.phase_completed = 0;
            status.reconciliation.phase_total = 0;
            status.reconciliation.current_title = None;
            status.reconciliation.last_started_at = Some(Utc::now());
            status.reconciliation.last_result = None;
            status.daemon_state = if status.dry_run {
                "dry-run-running".to_string()
            } else {
                "running".to_string()
            };
            status.last_notice = Some(format!("{} reconciliation started", mode.label()));
            status.last_notice_at = Some(Utc::now());
        })
        .await;
        if mode == ReconcileMode::CurrentDay {
            metrics::counter!("current_day_recheck_run_total").increment(1);
        }
        let pass = self.build_reconcile_pass_context(mode).await;
        let result = reconciliation_loop(Arc::new(pass)).await;
        let last_result = match &result {
            Ok(()) => "completed".to_string(),
            Err(error) => format!("failed: {error:#}"),
        };
        let notice = match &result {
            Ok(()) => format!("{} reconciliation completed", mode.label()),
            Err(error) => format!("{} reconciliation failed: {error}", mode.label()),
        };
        self.update_runtime_status(move |status| {
            status.reconciliation.active = false;
            status.reconciliation.phase = Some("idle".to_string());
            status.reconciliation.current_title = None;
            status.reconciliation.last_completed_at = Some(Utc::now());
            status.reconciliation.last_result = Some(last_result);
            status.last_notice = Some(notice);
            status.last_notice_at = Some(Utc::now());
        })
        .await;
        result
    }
}

pub struct AppRuntime {
    pub config: AppConfig,
    pub env: EnvConfig,
    pub paths: RuntimePaths,
    pub client: MediaWikiClient,
    pub auth: Arc<RwLock<AuthState>>,
    pub cache: Arc<RwLock<RuntimeCache>>,
    pub processed: Arc<RwLock<ProcessedRevidsState>>,
    pub progress: Arc<tokio::sync::Mutex<NightlySweepProgress>>,
    pub queue_depth: Arc<AtomicUsize>,
    pub reconcile: Arc<ReconciliationRuntime>,
    pub revision_locks: Arc<KeyLockSet<u64>>,
    pub page_locks: Arc<KeyLockSet<String>>,
    pub work_tx: mpsc::Sender<RevDelAction>,
    pub dry_run: bool,
}

impl AppRuntime {
    pub async fn bootstrap(
        config_path: PathBuf,
        dry_run: bool,
        verbose: bool,
    ) -> Result<Arc<Self>> {
        let config = AppConfig::load(&config_path)?;
        let paths = RuntimePaths::resolve(&config_path, &config);
        init_logging(&config.logging, verbose);
        info!(
            dry_run,
            verbose,
            config_path = %paths.config_path.display(),
            "starting suppressor bootstrap"
        );
        init_metrics(&config.metrics)?;
        let env = load_env(&paths.config_path)?;
        info!(env_file = %env.env_file.display(), "loaded local environment");
        let client = MediaWikiClient::new(&env)?;
        let auth = authenticate(&client, &env).await?;
        info!(
            authenticated_as = %auth.username,
            high_limits = auth.has_high_limits(),
            rights_count = auth.rights.len(),
            "authenticated MediaWiki session"
        );
        let cache = load_or_bootstrap(
            &client,
            &config,
            &paths,
            if dry_run {
                CachePersistence::Ephemeral
            } else {
                CachePersistence::Persist
            },
        )
        .await?;

        std::fs::create_dir_all(&paths.state_dir)
            .with_context(|| format!("Failed to create {}", paths.state_dir.display()))?;
        let processed = load_json(&paths.processed_revids_file)?.unwrap_or(ProcessedRevidsState {
            capacity: 50_000,
            revids: Vec::new(),
        });
        let progress = load_json(&paths.nightly_sweep_progress_file)?.unwrap_or_default();
        let runtime_status = load_json(&paths.runtime_status_file)?.unwrap_or_default();
        let revision_locks = Arc::new(KeyLockSet::new());
        let page_locks = Arc::new(KeyLockSet::new());
        let queue_depth = Arc::new(AtomicUsize::new(0));
        let auth = Arc::new(RwLock::new(auth));
        let cache = Arc::new(RwLock::new(cache));
        let processed = Arc::new(RwLock::new(processed));
        let progress = Arc::new(tokio::sync::Mutex::new(progress));
        let runtime_status = Arc::new(tokio::sync::Mutex::new(runtime_status));
        let (work_tx, work_rx) = mpsc::channel(config.queue.capacity);
        let actions = Arc::new(ActionDispatcher::new(
            Arc::clone(&revision_locks),
            Arc::clone(&processed),
            Arc::clone(&queue_depth),
            work_tx.clone(),
            Arc::clone(&runtime_status),
            paths.runtime_status_file.clone(),
        ));
        let reconcile = Arc::new(ReconciliationRuntime::new(ReconciliationRuntimeInit {
            config: config.clone(),
            client: client.clone(),
            auth: Arc::clone(&auth),
            cache: Arc::clone(&cache),
            progress: Arc::clone(&progress),
            runtime_status: Arc::clone(&runtime_status),
            page_locks: Arc::clone(&page_locks),
            paths: paths.clone(),
            dry_run,
            actions: Arc::clone(&actions),
        }));
        let runtime = Arc::new(Self {
            config,
            env,
            paths,
            client,
            auth,
            cache,
            processed,
            progress,
            queue_depth,
            reconcile,
            revision_locks,
            page_locks,
            work_tx,
            dry_run,
        });
        runtime
            .update_runtime_status(|status| {
                status.daemon_state = if dry_run {
                    "dry-run-starting".to_string()
                } else {
                    "starting".to_string()
                };
                status.dry_run = dry_run;
                status.last_notice = Some("bootstrap completed".to_string());
                status.last_notice_at = Some(Utc::now());
                status.resource_economy = Some(crate::state::ResourceEconomySnapshot {
                    queue_depth_max_recent: 0,
                    latest_measurement_at: Some(Utc::now()),
                    ..crate::state::ResourceEconomySnapshot::default()
                });
                status.realtime.state = "starting".to_string();
                status.realtime.last_state_changed_at = Some(Utc::now());
                status.realtime.stale_threshold_seconds =
                    runtime.config.realtime.stale_threshold_seconds;
                status.realtime.stream_read_timeout_seconds =
                    runtime.config.realtime.stream_read_timeout_seconds;
                status.realtime.queue_depth = 0;
                status.realtime.latest_notice = Some("bootstrap completed".to_string());
            })
            .await;
        let cache_snapshot = runtime.cache.read().await.snapshot.clone();
        let processed_count = runtime.processed.read().await.revids.len();
        let checkpoint_pages = runtime.progress.lock().await.pages.len();
        info!(
            source_title = %cache_snapshot.source_title,
            listed_titles = cache_snapshot.listed_titles_normalized.len(),
            watched_titles = cache_snapshot.watched_titles_normalized.len(),
            processed_revids = processed_count,
            checkpoint_pages,
            queue_capacity = runtime.config.queue.capacity,
            "runtime state loaded"
        );
        tokio::spawn(crate::worker::run_worker(Arc::clone(&runtime), work_rx));
        Ok(runtime)
    }

    pub async fn update_runtime_status<F>(&self, update: F)
    where
        F: FnOnce(&mut RuntimeStatus),
    {
        self.reconcile.update_runtime_status(update).await;
    }

    pub async fn record_notice<S: Into<String>>(&self, notice: S) {
        self.reconcile.record_notice(notice).await;
    }

    pub async fn mark_realtime_stream_open(&self) {
        self.update_runtime_status(|status| {
            let now = Utc::now();
            let backoff_until = active_backoff_until(status.realtime.backoff_until, now);
            status.realtime.backoff_until = backoff_until;
            let next_state = converged_realtime_state_after_stream_open(&status.realtime, now);
            if status.realtime.state != next_state {
                status.realtime.state = next_state;
                status.realtime.last_state_changed_at = Some(now);
            }
            status.realtime.last_stream_opened_at = Some(now);
            status.realtime.stale_threshold_seconds = self.config.realtime.stale_threshold_seconds;
            status.realtime.stream_read_timeout_seconds =
                self.config.realtime.stream_read_timeout_seconds;
            if backoff_until.is_none() {
                status.realtime.latest_error_code = None;
                status.realtime.latest_error = None;
            }
            let notice = if let Some(until) = backoff_until {
                format!(
                    "real-time stream opened; catch-up backoff until {}",
                    render_runtime_time(&until)
                )
            } else {
                "real-time stream opened".to_string()
            };
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_realtime_event(&self, event_id: Option<String>) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let backoff_until = active_backoff_until(status.realtime.backoff_until, now);
            status.realtime.last_event_observed_at = Some(now);
            status.realtime.last_freshness_probe_source = Some("stream".to_string());
            status.realtime.current_lag_seconds = Some(0);
            if let Some(event_id) = event_id {
                status.realtime.last_event_id = Some(event_id);
            }
            let next_state = converged_realtime_state_after_stream_event(&status.realtime, now);
            if status.realtime.state != next_state {
                status.realtime.state = next_state;
                status.realtime.last_state_changed_at = Some(now);
            }
            status.realtime.backoff_until = backoff_until;
            status.realtime.latest_notice = Some(if let Some(until) = backoff_until {
                format!(
                    "observed target-wiki event; recovery backoff until {}",
                    render_runtime_time(&until)
                )
            } else {
                "observed target-wiki event".to_string()
            });
        })
        .await;
    }

    pub async fn mark_realtime_match(&self, title: String, revid: u64) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            status.realtime.last_matching_edit_at = Some(now);
            status.realtime.last_matching_title = Some(title);
            status.realtime.last_matching_revid = Some(revid);
            status.realtime.latest_notice = Some(format!("matched watched revid {}", revid));
        })
        .await;
    }

    pub async fn mark_realtime_state(
        &self,
        state: &'static str,
        trigger: Option<String>,
        reconnect_reason: Option<String>,
        error_code: Option<String>,
        notice: String,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            status.realtime.state = state.to_string();
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.last_recovery_trigger = trigger;
            status.realtime.last_reconnect_reason = reconnect_reason;
            status.realtime.latest_error_code = error_code;
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn record_api_failure(&self, snapshot: ApiFailureSnapshot) {
        self.update_runtime_status(move |status| {
            status.realtime.latest_error_code = snapshot
                .api_code
                .clone()
                .or_else(|| Some(snapshot.class.clone()));
            status.realtime.latest_notice = Some(format!(
                "{} {} failed",
                snapshot.operation,
                status
                    .realtime
                    .latest_error_code
                    .as_deref()
                    .unwrap_or("error")
            ));
            status.realtime.latest_error = Some(snapshot);
        })
        .await;
    }

    pub async fn record_source_refresh(&self, refresh: SourceListRefresh) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let active_deferred_until = active_backoff_until(refresh.deferred_until, now);
            let notice = format!(
                "source refresh {} new={} removed={} catchup={}",
                refresh.outcome,
                refresh.new_titles_count,
                refresh.removed_titles_count,
                refresh.catchup_triggered
            );
            if active_deferred_until.is_some() {
                status.realtime.state = "catching-up".to_string();
                status.realtime.last_state_changed_at = Some(now);
                status.realtime.backoff_until = active_deferred_until;
            } else if refresh.error.is_some() || refresh.outcome.ends_with("failed") {
                status.realtime.state = "unhealthy".to_string();
                status.realtime.last_state_changed_at = Some(now);
            }
            if let Some(error) = refresh.error.clone() {
                status.realtime.latest_error_code =
                    error.api_code.clone().or_else(|| Some(error.class.clone()));
                status.realtime.latest_error = Some(error);
            }
            status.realtime.last_source_refresh = Some(refresh);
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_recovery_started(&self, trigger: String) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let notice = format!("{} catch-up started", trigger);
            status.realtime.state = "catching-up".to_string();
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.catchup_active = true;
            status.realtime.last_recovery_trigger = Some(trigger.clone());
            status.realtime.last_recovery_started_at = Some(now);
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn current_backoff_until(&self) -> Option<DateTime<Utc>> {
        let status = self.reconcile.runtime_status.lock().await;
        active_backoff_until(status.realtime.backoff_until, Utc::now())
    }

    pub async fn mark_recovery_completed(&self, summary: CoverageSummary) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let backoff_until = active_backoff_until(summary.backoff_until, now);
            let notice = render_recovery_notice(&summary);
            status.realtime.state = if backoff_until.is_some() {
                "catching-up".to_string()
            } else if summary.unresolved_count == 0 {
                "healthy".to_string()
            } else {
                "unhealthy".to_string()
            };
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.catchup_active = false;
            status.realtime.last_recovery_completed_at = Some(now);
            status.realtime.backoff_until = backoff_until;
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
            if let Some(warning) = summary.warning_summaries.first() {
                status.realtime.latest_error_code = warning
                    .api_code
                    .clone()
                    .or_else(|| Some(warning.class.clone()));
                status.realtime.latest_error = Some(ApiFailureSnapshot {
                    class: warning.class.clone(),
                    api_code: warning.api_code.clone(),
                    http_status: warning.http_status,
                    content_type: warning.content_type.clone(),
                    retryable: warning.retryable,
                    retry_after_seconds: warning.retry_after_seconds,
                    operation: warning.operation.clone(),
                    message: warning.message.clone(),
                    occurred_at: Some(now),
                    ..ApiFailureSnapshot::default()
                });
            } else if backoff_until.is_none() && summary.unresolved_count == 0 {
                status.realtime.latest_error_code = None;
                status.realtime.latest_error = None;
            }
            let warning_count = summary
                .warning_summaries
                .iter()
                .map(|warning| warning.count)
                .sum();
            if warning_count > 0 {
                let mut resource = status.resource_economy.clone().unwrap_or_default();
                resource.queue_depth_max_recent = resource
                    .queue_depth_max_recent
                    .max(status.realtime.queue_depth);
                resource.coalesced_warning_count_recent = warning_count;
                resource.latest_measurement_at = Some(now);
                status.resource_economy = Some(resource);
            }
            status.realtime.latest_recovery_warnings = summary.warning_summaries.clone();
            status.realtime.latest_recovery_summary = Some(summary);
        })
        .await;
    }

    pub async fn record_action_completed(
        &self,
        action: &RevDelAction,
        outcome: &'static str,
        reason_code: Option<String>,
        attempt_count: u32,
    ) {
        let completed_at = Utc::now();
        let queue_depth = self.queue_depth.load(Ordering::SeqCst);
        let title = action.title.clone();
        let revid = action.revids.first().copied().unwrap_or_default();
        let mode = action.mode.label().to_string();
        let observed_at = action.observed_at;
        let queued_at = action.queued_at;
        self.update_runtime_status(move |status| {
            let backoff_until = active_backoff_until(status.realtime.backoff_until, completed_at);
            status.realtime.queue_depth = queue_depth;
            status.realtime.last_action_completed_at = Some(completed_at);
            if outcome == "hidden" || outcome == "already-hidden" {
                status.realtime.last_successful_hide_at = Some(completed_at);
            }
            if outcome == "blocked" {
                status.realtime.state = "blocked".to_string();
                status.realtime.last_state_changed_at = Some(completed_at);
            } else if mode == RevDelMode::Live.label()
                && matches!(outcome, "failed" | "retrying" | "throttled" | "unresolved")
            {
                status.realtime.state = "unhealthy".to_string();
                status.realtime.last_state_changed_at = Some(completed_at);
            } else if mode == RevDelMode::Live.label()
                && matches!(outcome, "hidden" | "already-hidden")
                && !status.realtime.catchup_active
                && backoff_until.is_none()
            {
                status.realtime.state = "healthy".to_string();
                status.realtime.last_state_changed_at = Some(completed_at);
                status.realtime.latest_error_code = None;
                status.realtime.latest_error = None;
            }
            status.realtime.latest_outcome = Some(SuppressionOutcomeSnapshot {
                title,
                revid,
                outcome: outcome.to_string(),
                reason_code,
                mode,
                observed_at,
                queued_at: Some(queued_at),
                completed_at: Some(completed_at),
                attempt_count,
            });
            status.realtime.latest_notice = Some(format!("{} revid {}", outcome, revid));
        })
        .await;
    }

    pub async fn dispatch_action_batch(
        &self,
        title: String,
        revids: Vec<u64>,
        event_id: Option<String>,
        user: Option<String>,
        comment: Option<String>,
        mode: RevDelMode,
    ) -> Result<()> {
        self.reconcile
            .actions
            .dispatch_action_batch(title, revids, event_id, user, comment, mode)
            .await
    }

    pub async fn dispatch_action(&self, dispatch: RevDelDispatch) -> Result<()> {
        self.reconcile.actions.dispatch_action(dispatch).await
    }
    pub async fn run_reconciliation_pass(self: &Arc<Self>, mode: ReconcileMode) -> Result<()> {
        self.reconcile.run_reconciliation_pass(mode).await
    }
}

fn active_backoff_until(
    backoff_until: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
) -> Option<DateTime<Utc>> {
    backoff_until.filter(|until| *until > now)
}

fn latest_live_outcome_is_degraded(status: &crate::state::RealtimeRuntimeStatus) -> bool {
    matches!(
        status.latest_outcome.as_ref(),
        Some(outcome)
            if outcome.mode == RevDelMode::Live.label()
                && matches!(
                    outcome.outcome.as_str(),
                    "failed" | "retrying" | "throttled" | "unresolved" | "blocked"
                )
    )
}

fn converged_realtime_state_after_stream_open(
    status: &crate::state::RealtimeRuntimeStatus,
    now: DateTime<Utc>,
) -> String {
    if status.catchup_active || active_backoff_until(status.backoff_until, now).is_some() {
        return "catching-up".to_string();
    }
    if matches!(status.state.as_str(), "blocked")
        || matches!(
            status.latest_outcome.as_ref(),
            Some(outcome)
                if outcome.mode == RevDelMode::Live.label() && outcome.outcome == "blocked"
        )
    {
        return "blocked".to_string();
    }
    if latest_live_outcome_is_degraded(status) {
        return "unhealthy".to_string();
    }
    if status.last_event_observed_at.is_none() && status.state == "starting" {
        return "starting".to_string();
    }
    if status.last_event_observed_at.is_none() && status.state == "reconnecting" {
        return "reconnecting".to_string();
    }
    "healthy".to_string()
}

fn converged_realtime_state_after_stream_event(
    status: &crate::state::RealtimeRuntimeStatus,
    now: DateTime<Utc>,
) -> String {
    if status.catchup_active || active_backoff_until(status.backoff_until, now).is_some() {
        return "catching-up".to_string();
    }
    if matches!(status.state.as_str(), "blocked")
        || matches!(
            status.latest_outcome.as_ref(),
            Some(outcome)
                if outcome.mode == RevDelMode::Live.label() && outcome.outcome == "blocked"
        )
    {
        return "blocked".to_string();
    }
    if latest_live_outcome_is_degraded(status) {
        return "unhealthy".to_string();
    }
    "healthy".to_string()
}

fn render_runtime_time(value: &DateTime<Utc>) -> String {
    value.format("%H:%M:%S UTC").to_string()
}

fn render_recovery_notice(summary: &CoverageSummary) -> String {
    if let Some(until) = summary.backoff_until.as_ref() {
        if let Some(reason) = summary.stopped_early_reason.as_deref() {
            return format!(
                "catch-up paused until {} ({})",
                render_runtime_time(until),
                reason
            );
        }
        return format!("catch-up paused until {}", render_runtime_time(until));
    }
    if let Some(reason) = summary.stopped_early_reason.as_deref() {
        return format!("catch-up stopped early: {}", reason);
    }
    format!(
        "catch-up completed checked={} unresolved={}",
        summary.edits_checked, summary.unresolved_count
    )
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use tempfile::tempdir;

    use super::*;
    use crate::auth::AuthState;
    use crate::cache::RuntimeCache;
    use crate::cache::SuppressionListCache;
    use crate::config::{
        AppConfig, AuthConfig, CatchupConfig, CurrentDayRecheckConfig, LoggingConfig,
        MatchingConfig, MetricsConfig, NightlySweepConfig, QueueConfig, RealtimeConfig,
        RetryConfig, RevDelConfig, StateConfig, SuppressionListConfig, WikiConfig,
    };
    use crate::state::RuntimeStatus;

    fn test_config() -> AppConfig {
        AppConfig {
            wiki: WikiConfig {
                api_url: "https://example.invalid/api.php".to_string(),
                stream_url: "https://example.invalid/stream".to_string(),
                wiki_code: "bewiki".to_string(),
                server_name: "be.wikipedia.org".to_string(),
                user_agent: "bewiki-test/1.0".to_string(),
            },
            auth: AuthConfig {
                username_env: "BOT_USERNAME".to_string(),
                password_env: "BOT_PASSWORD".to_string(),
            },
            suppression_list: SuppressionListConfig {
                title: "List".to_string(),
                cache_file: "./state/cache.json".to_string(),
                metadata_recheck_seconds: 60,
                request_pages: vec!["Вікіпедыя:Запыты да схавальнікаў".to_string()],
            },
            matching: MatchingConfig {
                drop_canary: true,
                exact_title_match: true,
            },
            revdel: RevDelConfig {
                hide: vec!["user".to_string(), "comment".to_string()],
                suppress: false,
                reason: "reason".to_string(),
            },
            queue: QueueConfig { capacity: 4 },
            state: StateConfig {
                dir: "./state".to_string(),
                last_event_id_file: "./state/last_event_id.txt".to_string(),
                processed_revids_file: "./state/processed_revids.json".to_string(),
                nightly_sweep_progress_file: "./state/nightly_sweep_progress.json".to_string(),
                runtime_status_file: "./state/runtime_status.json".to_string(),
                pid_file: "./state/daemon.pid".to_string(),
            },
            retry: RetryConfig {
                stream_backoff_initial_ms: 1000,
                stream_backoff_max_ms: 10000,
                api_max_retries: 3,
                since_recovery_seconds: 60,
            },
            realtime: RealtimeConfig {
                stale_threshold_seconds: 10,
                stream_read_timeout_seconds: 10,
                freshness_probe_seconds: 30,
            },
            catchup: CatchupConfig {
                default_window_seconds: 1800,
                max_window_seconds: 7200,
                max_revisions_per_run: 1000,
                warning_sample_limit: 5,
                source_refresh_title_scope_limit: 250,
                rate_limit_backoff_default_seconds: 30,
                rate_limit_stop_after_failures: 3,
                unresolved_sample_limit: 25,
            },
            nightly_sweep: NightlySweepConfig {
                enabled: true,
                timezone: "Europe/Warsaw".to_string(),
                start_time: "02:00".to_string(),
                page_concurrency: 3,
                batch_sleep_ms: 17,
            },
            current_day_recheck: CurrentDayRecheckConfig {
                enabled: true,
                min_delay_seconds: 1,
                max_delay_seconds: 2,
            },
            logging: LoggingConfig {
                level: "info".to_string(),
                format: "text".to_string(),
            },
            metrics: MetricsConfig {
                enabled: false,
                bind: "127.0.0.1:0".to_string(),
            },
        }
    }

    fn test_runtime_paths(temp: &tempfile::TempDir) -> RuntimePaths {
        RuntimePaths {
            config_path: temp.path().join("config.toml"),
            state_dir: temp.path().join("state"),
            env_file: temp.path().join(".env"),
            cache_file: temp.path().join("cache.json"),
            last_event_id_file: temp.path().join("last_event_id.txt"),
            processed_revids_file: temp.path().join("processed.json"),
            nightly_sweep_progress_file: temp.path().join("progress.json"),
            runtime_status_file: temp.path().join("status.json"),
            pid_file: temp.path().join("daemon.pid"),
        }
    }

    #[tokio::test]
    async fn action_dispatcher_skips_processed_revisions() {
        let processed = Arc::new(RwLock::new(ProcessedRevidsState {
            capacity: 10,
            revids: vec![42],
        }));
        let revision_locks = Arc::new(KeyLockSet::new());
        let queue_depth = Arc::new(AtomicUsize::new(0));
        let (work_tx, mut work_rx) = mpsc::channel(1);
        let temp = tempdir().unwrap();
        let runtime_status = Arc::new(tokio::sync::Mutex::new(RuntimeStatus::default()));
        let dispatcher = ActionDispatcher::new(
            revision_locks,
            processed,
            queue_depth.clone(),
            work_tx,
            runtime_status,
            temp.path().join("status.json"),
        );

        dispatcher
            .dispatch_action_batch(
                "Title".to_string(),
                vec![42],
                None,
                None,
                None,
                RevDelMode::Live,
            )
            .await
            .unwrap();

        assert!(work_rx.try_recv().is_err());
        assert_eq!(queue_depth.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn reconcile_pass_context_captures_explicit_inputs() {
        let temp = tempdir().unwrap();
        let config = test_config();
        let paths = test_runtime_paths(&temp);
        let env = EnvConfig {
            api_url: "https://example.invalid/api.php".to_string(),
            stream_url: "https://example.invalid/stream".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "pw".to_string(),
            user_agent: "bewiki-test/1.0".to_string(),
            env_file: temp.path().join(".env"),
        };
        let client = MediaWikiClient::new(&env).unwrap();
        let auth = Arc::new(RwLock::new(AuthState {
            username: "bot".to_string(),
            csrf_token: "csrf".to_string(),
            rights: HashSet::from([String::from("apihighlimits")]),
        }));
        let cache = Arc::new(RwLock::new(RuntimeCache::from_snapshot(
            SuppressionListCache {
                source_title: "List".to_string(),
                source_pageid: Some(1),
                source_lastrevid: Some(2),
                source_last_timestamp: None,
                fetched_at: chrono::Utc::now(),
                listed_titles_normalized: vec!["Foo".to_string(), "Bar".to_string()],
                watched_titles_normalized: vec!["Foo".to_string(), "Bar".to_string()],
                redirect_map: Default::default(),
                titles_hash_sha256: "hash".to_string(),
            },
        )));
        let progress = Arc::new(tokio::sync::Mutex::new(NightlySweepProgress::default()));
        let runtime_status = Arc::new(tokio::sync::Mutex::new(RuntimeStatus::default()));
        let page_locks = Arc::new(KeyLockSet::new());
        let revision_locks = Arc::new(KeyLockSet::new());
        let queue_depth = Arc::new(AtomicUsize::new(0));
        let (work_tx, _work_rx) = mpsc::channel(config.queue.capacity);
        let runtime_status_for_actions = Arc::clone(&runtime_status);
        let actions = Arc::new(ActionDispatcher::new(
            revision_locks,
            Arc::new(RwLock::new(ProcessedRevidsState::default())),
            queue_depth,
            work_tx,
            runtime_status_for_actions,
            temp.path().join("status.json"),
        ));
        let runtime = Arc::new(ReconciliationRuntime::new(ReconciliationRuntimeInit {
            config: config.clone(),
            client,
            auth,
            cache,
            progress,
            runtime_status,
            page_locks,
            paths,
            dry_run: true,
            actions,
        }));

        let pass = runtime
            .build_reconcile_pass_context(ReconcileMode::CurrentDay)
            .await;

        assert_eq!(pass.mode, ReconcileMode::CurrentDay);
        assert_eq!(
            pass.listed_titles,
            vec!["Foo".to_string(), "Bar".to_string()]
        );
        assert_eq!(pass.page_concurrency, config.nightly_sweep.page_concurrency);
        assert_eq!(pass.timezone, config.nightly_sweep.timezone);
        assert_eq!(pass.batch_sleep_ms, config.nightly_sweep.batch_sleep_ms);
        assert_eq!(pass.batch_limit, 500);
        assert_eq!(pass.persistence, CachePersistence::Ephemeral);
    }

    #[test]
    fn active_backoff_filters_expired_values() {
        let now = DateTime::parse_from_rfc3339("2026-04-25T17:10:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let expired = DateTime::parse_from_rfc3339("2026-04-25T17:09:59Z")
            .unwrap()
            .with_timezone(&Utc);
        let active = DateTime::parse_from_rfc3339("2026-04-25T17:10:30Z")
            .unwrap()
            .with_timezone(&Utc);

        assert_eq!(active_backoff_until(Some(expired), now), None);
        assert_eq!(active_backoff_until(Some(active), now), Some(active));
    }

    #[test]
    fn recovery_notice_prefers_backoff_and_stop_reason() {
        let summary = CoverageSummary {
            stopped_early_reason: Some("rate-limited".to_string()),
            backoff_until: Some(
                DateTime::parse_from_rfc3339("2026-04-25T17:11:00Z")
                    .unwrap()
                    .with_timezone(&Utc),
            ),
            edits_checked: 7,
            unresolved_count: 3,
            ..CoverageSummary::default()
        };

        assert_eq!(
            render_recovery_notice(&summary),
            "catch-up paused until 17:11:00 UTC (rate-limited)"
        );
    }

    #[test]
    fn stream_event_converges_idle_catchup_to_healthy() {
        let now = DateTime::parse_from_rfc3339("2026-04-28T11:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let status = crate::state::RealtimeRuntimeStatus {
            state: "catching-up".to_string(),
            catchup_active: false,
            backoff_until: None,
            latest_outcome: Some(SuppressionOutcomeSnapshot {
                title: "Title".to_string(),
                revid: 42,
                outcome: "hidden".to_string(),
                mode: RevDelMode::Live.label().to_string(),
                ..SuppressionOutcomeSnapshot::default()
            }),
            ..crate::state::RealtimeRuntimeStatus::default()
        };

        assert_eq!(
            converged_realtime_state_after_stream_event(&status, now),
            "healthy"
        );
    }

    #[test]
    fn stream_event_keeps_failed_live_protection_unhealthy() {
        let now = DateTime::parse_from_rfc3339("2026-04-28T11:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let status = crate::state::RealtimeRuntimeStatus {
            state: "catching-up".to_string(),
            catchup_active: false,
            backoff_until: None,
            latest_outcome: Some(SuppressionOutcomeSnapshot {
                title: "Title".to_string(),
                revid: 42,
                outcome: "failed".to_string(),
                mode: RevDelMode::Live.label().to_string(),
                ..SuppressionOutcomeSnapshot::default()
            }),
            ..crate::state::RealtimeRuntimeStatus::default()
        };

        assert_eq!(
            converged_realtime_state_after_stream_event(&status, now),
            "unhealthy"
        );
    }

    #[test]
    fn stream_open_keeps_starting_before_first_event() {
        let now = DateTime::parse_from_rfc3339("2026-04-28T11:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let status = crate::state::RealtimeRuntimeStatus {
            state: "starting".to_string(),
            ..crate::state::RealtimeRuntimeStatus::default()
        };

        assert_eq!(
            converged_realtime_state_after_stream_open(&status, now),
            "starting"
        );
    }
}
