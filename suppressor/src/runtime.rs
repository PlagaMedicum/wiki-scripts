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
use crate::metrics::{
    init_metrics, record_observed_to_hide_latency_ms, record_observed_to_queue_latency_ms,
};
use crate::mw_api::MediaWikiClient;
use crate::reconcile::{
    ReconcileCoordinator, ReconcileMode, reconciliation_loop, revisiondelete_batch_limit,
};
use crate::state::{
    ActionableIssueSnapshot, ApiFailureSnapshot, CoverageSummary, CurrentTaskSnapshot,
    NightlySweepProgress, ProcessedRevidsState, RuntimeStatus, SharedBackoffSnapshot,
    SourceListRefresh, SuppressionOutcomeSnapshot, load_json, save_json_atomic,
};

pub struct RecoveryWindowSelection {
    pub start: DateTime<Utc>,
    pub scope_label: String,
    pub allow_large_window: bool,
}

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

    pub fn source_label(self) -> &'static str {
        match self {
            RevDelMode::Live => "live hiding",
            RevDelMode::Catchup => "recovery catch-up",
            RevDelMode::Coverage => "coverage verification",
            RevDelMode::Reconciliation => "reconciliation",
            RevDelMode::Manual => "manual operator action",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeStatusSurfaceMode {
    DaemonOwned,
    DetachedCommand,
}

impl RuntimeStatusSurfaceMode {
    fn persists_runtime_status(self) -> bool {
        matches!(self, Self::DaemonOwned)
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
    wiki_server_name: String,
    revision_locks: Arc<KeyLockSet<u64>>,
    processed: Arc<RwLock<ProcessedRevidsState>>,
    queue_depth: Arc<AtomicUsize>,
    work_tx: mpsc::Sender<RevDelAction>,
    runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    runtime_status_file: PathBuf,
    runtime_status_surface_mode: RuntimeStatusSurfaceMode,
}

impl ActionDispatcher {
    pub fn new(
        wiki_server_name: String,
        revision_locks: Arc<KeyLockSet<u64>>,
        processed: Arc<RwLock<ProcessedRevidsState>>,
        queue_depth: Arc<AtomicUsize>,
        work_tx: mpsc::Sender<RevDelAction>,
        runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
        runtime_status_file: PathBuf,
        runtime_status_surface_mode: RuntimeStatusSurfaceMode,
    ) -> Self {
        Self {
            wiki_server_name,
            revision_locks,
            processed,
            queue_depth,
            work_tx,
            runtime_status,
            runtime_status_file,
            runtime_status_surface_mode,
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
        let revision_url = revids
            .first()
            .copied()
            .map(|revid| crate::mw_api::revision_url(&self.wiki_server_name, revid));
        let source_label = mode.source_label().to_string();
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
                    revision_url: Some(crate::mw_api::revision_url(&self.wiki_server_name, *revid)),
                    outcome: "skipped".to_string(),
                    reason_code: Some("duplicate-queued".to_string()),
                    mode: mode.label().to_string(),
                    source_label: source_label.clone(),
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
                    revision_url: Some(crate::mw_api::revision_url(&self.wiki_server_name, *revid)),
                    outcome: "already-hidden".to_string(),
                    reason_code: Some("already-processed".to_string()),
                    mode: mode.label().to_string(),
                    source_label: source_label.clone(),
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
        if let Some(observed_at) = observed_at {
            let elapsed_ms = (queued_at - observed_at).num_milliseconds().max(0) as u64;
            record_observed_to_queue_latency_ms(elapsed_ms);
        }
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
                revision_url: revision_url.clone(),
                outcome: "queued".to_string(),
                reason_code: recovery_trigger.clone(),
                mode: mode.label().to_string(),
                source_label,
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
        let queued_title = outcome.title.clone();
        let queued_at = outcome.queued_at;
        let outcome_name = outcome.outcome.clone();
        let mut status = self.runtime_status.lock().await;
        status.realtime.queue_depth = queue_depth;
        status.realtime.last_action_queued_at =
            outcome.queued_at.or(status.realtime.last_action_queued_at);
        status.realtime.latest_notice =
            Some(format!("{} revid {}", outcome.outcome, outcome.revid));
        status.realtime.latest_outcome = Some(outcome);
        if outcome_name == "queued" {
            status.realtime.current_task = Some(CurrentTaskSnapshot {
                task_kind: "live-hide".to_string(),
                label: format!("hiding watched edit {queued_title}"),
                progress_done: Some(0),
                progress_total: Some(1),
                window_start: None,
                window_end: None,
                started_at: queued_at,
                expected_resume_at: None,
            });
        }
        if self.runtime_status_surface_mode.persists_runtime_status()
            && let Err(error) = save_json_atomic(&self.runtime_status_file, &*status)
        {
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
    runtime_status_surface_mode: RuntimeStatusSurfaceMode,
    reconcile_coordinator: Arc<ReconcileCoordinator>,
}

pub struct ReconcilePassContext {
    pub(crate) mode: ReconcileMode,
    pub(crate) listed_titles: Vec<String>,
    pub(crate) daytime_window_hours: u64,
    pub(crate) page_concurrency: usize,
    pub(crate) timezone: String,
    pub(crate) batch_sleep_ms: u64,
    pub(crate) batch_limit: usize,
    pub(crate) warning_sample_limit: usize,
    pub(crate) rate_limit_backoff_default_seconds: u64,
    pub(crate) persistence: CachePersistence,
    pub(crate) client: MediaWikiClient,
    pub(crate) cache: Arc<RwLock<RuntimeCache>>,
    pub(crate) progress: Arc<tokio::sync::Mutex<NightlySweepProgress>>,
    pub(crate) runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    pub(crate) page_locks: Arc<KeyLockSet<String>>,
    pub(crate) paths: RuntimePaths,
    pub(crate) actions: Arc<ActionDispatcher>,
    pub(crate) runtime_status_surface_mode: RuntimeStatusSurfaceMode,
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
    runtime_status_surface_mode: RuntimeStatusSurfaceMode,
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
            runtime_status_surface_mode: init.runtime_status_surface_mode,
            reconcile_coordinator: Arc::new(ReconcileCoordinator::default()),
        }
    }

    pub async fn update_runtime_status<F>(&self, update: F)
    where
        F: FnOnce(&mut RuntimeStatus),
    {
        let mut status = self.runtime_status.lock().await;
        update(&mut status);
        if self.runtime_status_surface_mode.persists_runtime_status()
            && let Err(error) = save_json_atomic(&self.paths.runtime_status_file, &*status)
        {
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
            daytime_window_hours: self.config.daytime_verification.window_hours,
            page_concurrency: self.config.nightly_sweep.page_concurrency,
            timezone: self.config.nightly_sweep.timezone.clone(),
            batch_sleep_ms: self.config.nightly_sweep.batch_sleep_ms,
            batch_limit,
            warning_sample_limit: self.config.catchup.warning_sample_limit,
            rate_limit_backoff_default_seconds: self
                .config
                .catchup
                .rate_limit_backoff_default_seconds,
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
            runtime_status_surface_mode: self.runtime_status_surface_mode,
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
        if self.runtime_status_surface_mode.persists_runtime_status()
            && let Err(error) = save_json_atomic(&self.paths.runtime_status_file, &*status)
        {
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
        let started_at = Utc::now();
        let daytime_window_start = if mode == ReconcileMode::CurrentDay {
            Some(
                started_at
                    - chrono::TimeDelta::hours(
                        self.config.daytime_verification.window_hours as i64,
                    ),
            )
        } else {
            None
        };
        self.update_runtime_status(move |status| {
            apply_reconciliation_started_status(status, mode, started_at, daytime_window_start);
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
            Ok(()) => format!("{} completed", mode.operator_label()),
            Err(error) => format!("{} failed: {error}", mode.operator_label()),
        };
        let completed_at = Utc::now();
        self.update_runtime_status(move |status| {
            apply_reconciliation_completed_status(
                status,
                mode,
                completed_at,
                daytime_window_start,
                last_result,
                notice,
            );
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

#[cfg(test)]
pub struct TestRuntimeHarness {
    pub runtime: Arc<AppRuntime>,
    pub runtime_status: Arc<tokio::sync::Mutex<RuntimeStatus>>,
    pub work_rx: mpsc::Receiver<RevDelAction>,
}

#[cfg(test)]
pub(crate) fn build_test_runtime_harness(
    temp: &tempfile::TempDir,
    runtime_status_surface_mode: RuntimeStatusSurfaceMode,
) -> TestRuntimeHarness {
    let config_path = temp.path().join("config.toml");
    std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
    let config = AppConfig::load(&config_path).unwrap();
    let env = default_test_env(temp, &config);
    build_test_runtime_harness_with_env(temp, runtime_status_surface_mode, env)
}

#[cfg(test)]
pub(crate) fn build_test_runtime_harness_with_env(
    temp: &tempfile::TempDir,
    runtime_status_surface_mode: RuntimeStatusSurfaceMode,
    env: EnvConfig,
) -> TestRuntimeHarness {
    use std::collections::HashSet;
    use std::sync::atomic::AtomicUsize;

    use crate::auth::AuthState;
    use crate::cache::{RuntimeCache, SuppressionListCache};

    let config_path = temp.path().join("config.toml");
    std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
    let config = AppConfig::load(&config_path).unwrap();
    let paths = RuntimePaths::resolve(&config_path, &config);
    let client = MediaWikiClient::new(&env).unwrap();
    let auth = Arc::new(RwLock::new(AuthState {
        username: "bot".to_string(),
        csrf_token: "csrf".to_string(),
        rights: HashSet::from([String::from("apihighlimits")]),
    }));
    let cache = Arc::new(RwLock::new(RuntimeCache::from_snapshot(
        SuppressionListCache {
            source_title: config.suppression_list.title.clone(),
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
    let processed = Arc::new(RwLock::new(ProcessedRevidsState::default()));
    let progress = Arc::new(tokio::sync::Mutex::new(NightlySweepProgress::default()));
    let runtime_status = Arc::new(tokio::sync::Mutex::new(RuntimeStatus::default()));
    let page_locks = Arc::new(KeyLockSet::new());
    let revision_locks = Arc::new(KeyLockSet::new());
    let queue_depth = Arc::new(AtomicUsize::new(0));
    let (work_tx, work_rx) = mpsc::channel(config.queue.capacity);
    let actions = Arc::new(ActionDispatcher::new(
        config.wiki.server_name.clone(),
        Arc::clone(&revision_locks),
        Arc::clone(&processed),
        Arc::clone(&queue_depth),
        work_tx.clone(),
        Arc::clone(&runtime_status),
        paths.runtime_status_file.clone(),
        runtime_status_surface_mode,
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
        dry_run: true,
        actions: Arc::clone(&actions),
        runtime_status_surface_mode,
    }));
    let runtime = Arc::new(AppRuntime {
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
        dry_run: true,
    });
    TestRuntimeHarness {
        runtime,
        runtime_status,
        work_rx,
    }
}

#[cfg(test)]
fn default_test_env(temp: &tempfile::TempDir, config: &AppConfig) -> EnvConfig {
    EnvConfig {
        api_url: config.wiki.api_url.clone(),
        stream_url: config.wiki.stream_url.clone(),
        bot_username: "bot".to_string(),
        bot_password: "pw".to_string(),
        user_agent: config.wiki.user_agent.clone(),
        env_file: temp.path().join(".env"),
    }
}

impl AppRuntime {
    pub async fn bootstrap(
        config_path: PathBuf,
        dry_run: bool,
        verbose: bool,
    ) -> Result<Arc<Self>> {
        Self::bootstrap_with_status_surface(
            config_path,
            dry_run,
            verbose,
            RuntimeStatusSurfaceMode::DaemonOwned,
        )
        .await
    }

    pub async fn bootstrap_for_command(
        config_path: PathBuf,
        dry_run: bool,
        verbose: bool,
    ) -> Result<Arc<Self>> {
        Self::bootstrap_with_status_surface(
            config_path,
            dry_run,
            verbose,
            RuntimeStatusSurfaceMode::DetachedCommand,
        )
        .await
    }

    async fn bootstrap_with_status_surface(
        config_path: PathBuf,
        dry_run: bool,
        verbose: bool,
        runtime_status_surface_mode: RuntimeStatusSurfaceMode,
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
            config.wiki.server_name.clone(),
            Arc::clone(&revision_locks),
            Arc::clone(&processed),
            Arc::clone(&queue_depth),
            work_tx.clone(),
            Arc::clone(&runtime_status),
            paths.runtime_status_file.clone(),
            runtime_status_surface_mode,
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
            runtime_status_surface_mode,
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
                let now = Utc::now();
                status.daemon_state = if dry_run {
                    "dry-run-starting".to_string()
                } else {
                    "starting".to_string()
                };
                status.dry_run = dry_run;
                status.last_notice = Some("bootstrap completed".to_string());
                status.last_notice_at = Some(now);
                status.resource_economy = Some(crate::state::ResourceEconomySnapshot {
                    queue_depth_max_recent: 0,
                    latest_measurement_at: Some(now),
                    ..crate::state::ResourceEconomySnapshot::default()
                });
                status.realtime.state = "starting".to_string();
                status.realtime.last_state_changed_at = Some(now);
                status.realtime.stale_threshold_seconds =
                    runtime.config.realtime.stale_threshold_seconds;
                status.realtime.stream_read_timeout_seconds =
                    runtime.config.realtime.stream_read_timeout_seconds;
                status.realtime.queue_depth = 0;
                status.realtime.daemon_started_at = Some(now);
                status.realtime.current_task =
                    Some(idle_task("waiting for watched-page edits", now));
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
            let backoff_until = retain_runtime_backoff(status, now);
            let next_state = converged_realtime_state_after_stream_open(&status.realtime, now);
            if status.realtime.state != next_state {
                status.realtime.state = next_state.clone();
                status.realtime.last_state_changed_at = Some(now);
            }
            status.realtime.last_stream_opened_at = Some(now);
            status.realtime.stale_threshold_seconds = self.config.realtime.stale_threshold_seconds;
            status.realtime.stream_read_timeout_seconds =
                self.config.realtime.stream_read_timeout_seconds;
            if backoff_until.is_none() && next_state == "healthy" {
                status.realtime.latest_error_code = None;
                status.realtime.latest_error = None;
                clear_actionable_issue_if_source(&mut status.realtime, &["stream"]);
            } else if backoff_until.is_none()
                && matches!(next_state.as_str(), "unhealthy" | "blocked")
            {
                restore_persistent_issue(status, now);
            }
            if next_state != "reconnecting"
                && next_state != "catching-up"
                && next_state != "starting"
            {
                status.realtime.last_reconnect_reason = None;
                end_offline_interval_if_active(&mut status.realtime, now);
            }
            let notice = if let Some(until) = backoff_until {
                format!(
                    "real-time stream opened; catch-up backoff until {}",
                    render_runtime_time(&until)
                )
            } else {
                "real-time stream opened".to_string()
            };
            if backoff_until.is_none()
                && !status.reconciliation.active
                && !status.realtime.catchup_active
            {
                set_background_current_task(
                    status,
                    idle_task("waiting for watched-page edits", now),
                );
            }
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_realtime_event(
        &self,
        event_id: Option<String>,
        observed_at: Option<DateTime<Utc>>,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let observed_at = observed_at.unwrap_or(now);
            let lag_millis = (now - observed_at).num_milliseconds().max(0);
            let backoff_until = retain_runtime_backoff(status, now);
            status.realtime.last_event_observed_at = Some(observed_at);
            status.realtime.last_freshness_probe_source = Some("stream".to_string());
            status.realtime.current_lag_seconds = Some(lag_millis / 1000);
            status.realtime.current_lag_millis = Some(lag_millis);
            status.realtime.current_lag_source = Some("stream".to_string());
            if let Some(event_id) = event_id {
                status.realtime.last_event_id = Some(event_id);
            }
            let next_state = converged_realtime_state_after_stream_event(&status.realtime, now);
            if status.realtime.state != next_state {
                status.realtime.state = next_state;
                status.realtime.last_state_changed_at = Some(now);
            }
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

    pub async fn mark_realtime_match(
        &self,
        title: String,
        revid: u64,
        revid_url: String,
        observed_at: Option<DateTime<Utc>>,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            status.realtime.last_matching_edit_at = Some(observed_at.unwrap_or(now));
            status.realtime.last_matching_title = Some(title);
            status.realtime.last_matching_revid = Some(revid);
            status.realtime.last_matching_revid_url = Some(revid_url);
            status.realtime.latest_notice = Some(format!("matched watched revid {}", revid));
        })
        .await;
    }

    pub async fn last_event_observed_at(&self) -> Option<DateTime<Utc>> {
        let status = self.reconcile.runtime_status.lock().await;
        status.realtime.last_event_observed_at
    }

    pub async fn record_freshness_probe(
        &self,
        latest_event_at: DateTime<Utc>,
        source: String,
        notice: String,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let lag_millis = (now - latest_event_at).num_milliseconds().max(0);
            status.realtime.last_event_observed_at = Some(
                status
                    .realtime
                    .last_event_observed_at
                    .map(|previous| previous.max(latest_event_at))
                    .unwrap_or(latest_event_at),
            );
            status.realtime.last_freshness_probe_at = Some(now);
            status.realtime.last_freshness_probe_source = Some(source.clone());
            status.realtime.current_lag_seconds = Some(lag_millis / 1000);
            status.realtime.current_lag_millis = Some(lag_millis);
            status.realtime.current_lag_source = Some(source);
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_stream_quiet_without_gap(&self, silence_seconds: u64, notice: String) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let next_state = converged_realtime_state_after_stream_event(&status.realtime, now);
            if status.realtime.state != next_state {
                status.realtime.state = next_state.clone();
                status.realtime.last_state_changed_at = Some(now);
            }
            if next_state == "healthy" {
                status.realtime.latest_error_code = None;
                status.realtime.latest_error = None;
                clear_actionable_issue_if_source(&mut status.realtime, &["stream"]);
            } else if matches!(next_state.as_str(), "unhealthy" | "blocked") {
                restore_persistent_issue(status, now);
            }
            status.realtime.last_recovery_trigger = None;
            status.realtime.last_reconnect_reason = None;
            end_offline_interval_if_active(&mut status.realtime, now);
            if !status.realtime.catchup_active && !status.reconciliation.active {
                set_background_current_task(
                    status,
                    idle_task("waiting for watched-page edits", now),
                );
            }
            let notice = if notice.is_empty() {
                format!(
                    "stream quiet for {}s; freshness probe found no newer target-wiki edits",
                    silence_seconds
                )
            } else {
                notice
            };
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_stream_reconnecting(
        &self,
        error_code: String,
        reconnect_reason: String,
        notice: String,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            status.realtime.state = "reconnecting".to_string();
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.last_recovery_trigger = None;
            status.realtime.last_reconnect_reason = Some(reconnect_reason);
            status.realtime.latest_error_code = Some(error_code);
            begin_offline_interval_if_needed(&mut status.realtime, now);
            if !status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_some_and(actionable_issue_blocks_stream_healthy)
            {
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "stream".to_string(),
                    severity: "error".to_string(),
                    summary: notice.clone(),
                    next_action: "wait for the stream to reopen and verify the next watched edit"
                        .to_string(),
                    detected_at: Some(now),
                });
            }
            status.realtime.current_task = Some(CurrentTaskSnapshot {
                task_kind: "reconnecting".to_string(),
                label: notice.clone(),
                progress_done: None,
                progress_total: None,
                window_start: None,
                window_end: None,
                started_at: Some(now),
                expected_resume_at: None,
            });
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_stream_gap_detected(
        &self,
        trigger: String,
        error_code: String,
        notice: String,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            status.realtime.state = "stale".to_string();
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.last_recovery_trigger = Some(trigger);
            status.realtime.latest_error_code = Some(error_code);
            begin_offline_interval_if_needed(&mut status.realtime, now);
            status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                source: "stream".to_string(),
                severity: "warning".to_string(),
                summary: notice.clone(),
                next_action: "watch the recovery window and the next successful hide".to_string(),
                detected_at: Some(now),
            });
            status.realtime.current_task = Some(CurrentTaskSnapshot {
                task_kind: "stale".to_string(),
                label: notice.clone(),
                progress_done: None,
                progress_total: None,
                window_start: None,
                window_end: None,
                started_at: Some(now),
                expected_resume_at: None,
            });
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_recovery_failed(&self, trigger: String, error_code: String, notice: String) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            status.realtime.state = "unhealthy".to_string();
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.last_recovery_trigger = Some(trigger.clone());
            status.realtime.latest_error_code = Some(error_code);
            if is_gap_recovery_trigger(&trigger) {
                begin_offline_interval_if_needed(&mut status.realtime, now);
            }
            status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                source: "recovery".to_string(),
                severity: "error".to_string(),
                summary: notice.clone(),
                next_action: "watch the recovery window and confirm the next successful hide"
                    .to_string(),
                detected_at: Some(now),
            });
            status.realtime.current_task = Some(CurrentTaskSnapshot {
                task_kind: "unhealthy".to_string(),
                label: notice.clone(),
                progress_done: None,
                progress_total: None,
                window_start: None,
                window_end: None,
                started_at: Some(now),
                expected_resume_at: None,
            });
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn should_start_recovery(&self, trigger: &str) -> bool {
        let status = self.reconcile.runtime_status.lock().await;
        !(status.realtime.catchup_active
            && status.realtime.last_recovery_trigger.as_deref() == Some(trigger))
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
            if matches!(state, "stale" | "reconnecting" | "unhealthy") {
                if status.realtime.last_offline_started_at.is_none() {
                    status.realtime.last_offline_started_at = Some(now);
                }
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "stream".to_string(),
                    severity: if state == "stale" {
                        "warning".to_string()
                    } else {
                        "error".to_string()
                    },
                    summary: notice.clone(),
                    next_action: "watch the recovery window and the next successful hide"
                        .to_string(),
                    detected_at: Some(now),
                });
                status.realtime.current_task = Some(CurrentTaskSnapshot {
                    task_kind: state.to_string(),
                    label: notice.clone(),
                    progress_done: None,
                    progress_total: None,
                    window_start: None,
                    window_end: None,
                    started_at: Some(now),
                    expected_resume_at: None,
                });
            }
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn record_api_failure(&self, snapshot: ApiFailureSnapshot) {
        self.update_runtime_status(move |status| {
            let now = snapshot.occurred_at.unwrap_or_else(Utc::now);
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
            status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                source: snapshot.operation.clone(),
                severity: if snapshot.retryable {
                    "warning".to_string()
                } else {
                    "error".to_string()
                },
                summary: format!("{} failed: {}", snapshot.operation, snapshot.message),
                next_action: snapshot
                    .retry_after_seconds
                    .map(|seconds| format!("wait {seconds}s for backoff, then recheck"))
                    .unwrap_or_else(|| "inspect auth, API, or network state".to_string()),
                detected_at: Some(now),
            });
            if snapshot.retryable
                && let Some(seconds) = snapshot.retry_after_seconds
            {
                let until = now + chrono::TimeDelta::seconds(seconds as i64);
                set_shared_backoff(
                    status,
                    snapshot.operation.as_str(),
                    "api-retry-after",
                    until,
                    now,
                );
            }
            status.realtime.latest_error = Some(snapshot);
        })
        .await;
    }

    pub async fn record_source_refresh(&self, refresh: SourceListRefresh) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let active_deferred_until = refresh.deferred_until.and_then(|until| {
                set_shared_backoff(
                    status,
                    "source-refresh",
                    "source-refresh-deferred",
                    until,
                    now,
                )
            });
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
                set_background_current_task(
                    status,
                    CurrentTaskSnapshot {
                        task_kind: "source-refresh-backoff".to_string(),
                        label: "watched-page reload deferred by backoff".to_string(),
                        progress_done: None,
                        progress_total: None,
                        window_start: None,
                        window_end: None,
                        started_at: Some(now),
                        expected_resume_at: active_deferred_until,
                    },
                );
            } else if refresh.error.is_some() || refresh.outcome.ends_with("failed") {
                status.realtime.state = "unhealthy".to_string();
                status.realtime.last_state_changed_at = Some(now);
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "source-refresh".to_string(),
                    severity: "error".to_string(),
                    summary: "watched-page reload failed".to_string(),
                    next_action: "check the latest reload log and rerun reload watched pages"
                        .to_string(),
                    detected_at: Some(now),
                });
            }
            if let Some(error) = refresh.error.clone() {
                status.realtime.latest_error_code =
                    error.api_code.clone().or_else(|| Some(error.class.clone()));
                status.realtime.latest_error = Some(error);
            }
            if active_deferred_until.is_none()
                && !status.reconciliation.active
                && !status.realtime.catchup_active
            {
                set_background_current_task(
                    status,
                    idle_task("waiting for watched-page edits", now),
                );
            }
            status.realtime.last_source_refresh = Some(refresh);
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn mark_recovery_started(
        &self,
        trigger: String,
        scope_label: String,
        window_start: DateTime<Utc>,
        window_end: DateTime<Utc>,
    ) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let notice = format!("{scope_label} catch-up started ({trigger})");
            status.realtime.state = "catching-up".to_string();
            status.realtime.last_state_changed_at = Some(now);
            status.realtime.catchup_active = true;
            status.realtime.last_recovery_trigger = Some(trigger.clone());
            status.realtime.last_recovery_started_at = Some(now);
            set_background_current_task(
                status,
                CurrentTaskSnapshot {
                    task_kind: "catch-up".to_string(),
                    label: scope_label,
                    progress_done: Some(0),
                    progress_total: None,
                    window_start: Some(window_start),
                    window_end: Some(window_end),
                    started_at: Some(now),
                    expected_resume_at: None,
                },
            );
            status.realtime.latest_actionable_issue = None;
            status.realtime.latest_notice = Some(notice.clone());
            status.last_notice = Some(notice);
            status.last_notice_at = Some(now);
        })
        .await;
    }

    pub async fn current_backoff_until(&self) -> Option<DateTime<Utc>> {
        let status = self.reconcile.runtime_status.lock().await;
        active_runtime_backoff_until(&status.realtime, Utc::now())
    }

    pub async fn default_recovery_window(&self, end: DateTime<Utc>) -> RecoveryWindowSelection {
        let status = self.reconcile.runtime_status.lock().await;
        if let Some(anchor) = status.realtime.last_successful_hide_at
            && anchor < end
        {
            return RecoveryWindowSelection {
                start: anchor,
                scope_label: "since last successful hide".to_string(),
                allow_large_window: true,
            };
        }
        RecoveryWindowSelection {
            start: end - chrono::TimeDelta::seconds(self.config.catchup.default_window_seconds),
            scope_label: "recent emergency window".to_string(),
            allow_large_window: false,
        }
    }

    pub async fn mark_recovery_completed(&self, summary: CoverageSummary) {
        self.update_runtime_status(move |status| {
            let now = Utc::now();
            let backoff_until = summary
                .backoff_until
                .and_then(|until| {
                    set_shared_backoff(status, "recovery", "rate-limit-backoff", until, now)
                })
                .or_else(|| retain_runtime_backoff(status, now));
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
            set_background_current_task(
                status,
                if let Some(until) = backoff_until {
                    CurrentTaskSnapshot {
                        task_kind: "backoff".to_string(),
                        label: "waiting for backoff to expire".to_string(),
                        progress_done: None,
                        progress_total: None,
                        window_start: summary.started_at,
                        window_end: summary.ended_at,
                        started_at: Some(now),
                        expected_resume_at: Some(until),
                    }
                } else {
                    idle_task("waiting for watched-page edits", now)
                },
            );
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
            status.realtime.latest_actionable_issue = if let Some(until) = backoff_until {
                Some(ActionableIssueSnapshot {
                    source: "recovery".to_string(),
                    severity: "warning".to_string(),
                    summary: render_recovery_notice(&summary),
                    next_action: format!(
                        "wait for recovery backoff until {}",
                        render_runtime_time(&until)
                    ),
                    detected_at: Some(now),
                })
            } else if summary.unresolved_count > 0 {
                Some(ActionableIssueSnapshot {
                    source: "recovery".to_string(),
                    severity: "error".to_string(),
                    summary: format!(
                        "{} unresolved revisions remain after {}",
                        summary.unresolved_count,
                        summary.scope_label.as_deref().unwrap_or("recovery")
                    ),
                    next_action: "review the unresolved revision link and rerun recovery"
                        .to_string(),
                    detected_at: Some(now),
                })
            } else {
                None
            };
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
            status.realtime.last_offline_recovered_at = Some(now);
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
        let source_label = action.mode.source_label().to_string();
        let revision_url = crate::mw_api::revision_url(&self.config.wiki.server_name, revid);
        let observed_at = action.observed_at;
        let queued_at = action.queued_at;
        if outcome == "hidden"
            && let Some(observed_at) = observed_at
        {
            let elapsed_ms = (completed_at - observed_at).num_milliseconds().max(0) as u64;
            record_observed_to_hide_latency_ms(elapsed_ms);
        }
        self.update_runtime_status(move |status| {
            let backoff_until = retain_runtime_backoff(status, completed_at);
            status.realtime.queue_depth = queue_depth;
            status.realtime.last_action_completed_at = Some(completed_at);
            if outcome == "hidden" || outcome == "already-hidden" {
                status.realtime.last_successful_hide_at = Some(completed_at);
                status.realtime.last_successful_hide_title = Some(title.clone());
                status.realtime.last_successful_hide_revid = Some(revid);
                status.realtime.last_successful_hide_url = Some(crate::mw_api::revision_url(
                    &self.config.wiki.server_name,
                    revid,
                ));
            }
            if outcome == "blocked" {
                status.realtime.state = "blocked".to_string();
                status.realtime.last_state_changed_at = Some(completed_at);
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "live-hide".to_string(),
                    severity: "error".to_string(),
                    summary: format!("cannot hide revid {} because protection is blocked", revid),
                    next_action: "check auth and wiki-side rights immediately".to_string(),
                    detected_at: Some(completed_at),
                });
            } else if mode == RevDelMode::Live.label()
                && matches!(outcome, "failed" | "retrying" | "throttled" | "unresolved")
            {
                status.realtime.state = "unhealthy".to_string();
                status.realtime.last_state_changed_at = Some(completed_at);
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "live-hide".to_string(),
                    severity: "error".to_string(),
                    summary: format!("live hide failed for revid {}", revid),
                    next_action: "watch the recovery window and confirm a later successful hide"
                        .to_string(),
                    detected_at: Some(completed_at),
                });
            } else if mode == RevDelMode::Live.label()
                && matches!(outcome, "hidden" | "already-hidden")
                && !status.realtime.catchup_active
                && backoff_until.is_none()
            {
                let next_state =
                    converged_realtime_state_after_stream_event(&status.realtime, completed_at);
                status.realtime.state = next_state.clone();
                status.realtime.last_state_changed_at = Some(completed_at);
                if next_state == "healthy" {
                    status.realtime.latest_error_code = None;
                    status.realtime.latest_error = None;
                    clear_actionable_issue_if_source(
                        &mut status.realtime,
                        &["live-hide", "stream", "recovery"],
                    );
                    if !status.reconciliation.active {
                        status.realtime.current_task =
                            Some(idle_task("waiting for watched-page edits", completed_at));
                    }
                } else {
                    restore_persistent_issue(status, completed_at);
                }
            }
            status.realtime.latest_outcome = Some(SuppressionOutcomeSnapshot {
                title,
                revid,
                revision_url: Some(revision_url),
                outcome: outcome.to_string(),
                reason_code,
                mode,
                source_label,
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

    pub async fn contains_processed_revid(&self, revid: u64) -> bool {
        self.reconcile.actions.contains_processed(revid).await
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

fn active_runtime_backoff_until(
    status: &crate::state::RealtimeRuntimeStatus,
    now: DateTime<Utc>,
) -> Option<DateTime<Utc>> {
    let legacy_until = active_backoff_until(status.backoff_until, now);
    let shared_until = status
        .shared_backoff
        .as_ref()
        .and_then(|snapshot| active_backoff_until(snapshot.backoff_until, now));
    match (legacy_until, shared_until) {
        (Some(left), Some(right)) => Some(left.max(right)),
        (Some(until), None) | (None, Some(until)) => Some(until),
        (None, None) => None,
    }
}

pub(crate) fn shared_backoff_paths() -> Vec<String> {
    [
        "catch-up",
        "reconciliation",
        "source-refresh",
        "one-shot-command",
    ]
    .into_iter()
    .map(str::to_string)
    .collect()
}

pub(crate) fn set_shared_backoff(
    status: &mut RuntimeStatus,
    source: &str,
    reason: &str,
    until: DateTime<Utc>,
    now: DateTime<Utc>,
) -> Option<DateTime<Utc>> {
    let active_until = active_backoff_until(Some(until), now)?;
    let selected_until = active_runtime_backoff_until(&status.realtime, now)
        .map(|existing| existing.max(active_until))
        .unwrap_or(active_until);
    status.realtime.backoff_until = Some(selected_until);
    status.realtime.shared_backoff = Some(SharedBackoffSnapshot {
        source: source.to_string(),
        reason: reason.to_string(),
        backoff_until: Some(selected_until),
        affected_paths: shared_backoff_paths(),
        live_hiding_blocked: false,
        recorded_at: Some(now),
    });
    Some(selected_until)
}

fn retain_runtime_backoff(status: &mut RuntimeStatus, now: DateTime<Utc>) -> Option<DateTime<Utc>> {
    let active_until = active_runtime_backoff_until(&status.realtime, now);
    status.realtime.backoff_until = active_until;
    if active_until.is_none() {
        status.realtime.shared_backoff = None;
    } else if status
        .realtime
        .shared_backoff
        .as_ref()
        .and_then(|snapshot| active_backoff_until(snapshot.backoff_until, now))
        .is_none()
    {
        status.realtime.shared_backoff = active_until.map(|until| SharedBackoffSnapshot {
            source: "legacy-runtime".to_string(),
            reason: "legacy-backoff-until".to_string(),
            backoff_until: Some(until),
            affected_paths: shared_backoff_paths(),
            live_hiding_blocked: false,
            recorded_at: Some(now),
        });
    }
    active_until
}

fn offline_interval_active(status: &crate::state::RealtimeRuntimeStatus) -> bool {
    match (
        status.last_offline_started_at,
        status.last_offline_recovered_at,
    ) {
        (Some(started_at), Some(recovered_at)) => started_at > recovered_at,
        (Some(_), None) => true,
        _ => false,
    }
}

fn begin_offline_interval_if_needed(
    status: &mut crate::state::RealtimeRuntimeStatus,
    now: DateTime<Utc>,
) {
    if !offline_interval_active(status) {
        status.last_offline_started_at = Some(now);
    }
}

fn end_offline_interval_if_active(
    status: &mut crate::state::RealtimeRuntimeStatus,
    now: DateTime<Utc>,
) {
    if offline_interval_active(status) {
        status.last_offline_recovered_at = Some(now);
    }
}

fn is_gap_recovery_trigger(trigger: &str) -> bool {
    matches!(trigger, "startup" | "silent-starvation" | "invalid-resume")
}

fn current_task_is_live_hide(status: &crate::state::RealtimeRuntimeStatus) -> bool {
    matches!(
        status.current_task.as_ref(),
        Some(task) if task.task_kind == "live-hide"
    )
}

fn set_background_current_task(status: &mut RuntimeStatus, task: CurrentTaskSnapshot) {
    if !current_task_is_live_hide(&status.realtime) {
        status.realtime.current_task = Some(task);
    }
}

fn idle_task(label: &str, started_at: DateTime<Utc>) -> CurrentTaskSnapshot {
    CurrentTaskSnapshot {
        task_kind: "idle".to_string(),
        label: label.to_string(),
        progress_done: None,
        progress_total: None,
        window_start: None,
        window_end: None,
        started_at: Some(started_at),
        expected_resume_at: None,
    }
}

fn reconciliation_task(
    mode: ReconcileMode,
    started_at: DateTime<Utc>,
    daytime_window_start: Option<DateTime<Utc>>,
) -> CurrentTaskSnapshot {
    match mode {
        ReconcileMode::CurrentDay => CurrentTaskSnapshot {
            task_kind: "last-24h-verification".to_string(),
            label: "verifying the last 24 hours".to_string(),
            progress_done: Some(0),
            progress_total: None,
            window_start: daytime_window_start,
            window_end: Some(started_at),
            started_at: Some(started_at),
            expected_resume_at: None,
        },
        ReconcileMode::Full => CurrentTaskSnapshot {
            task_kind: "full-watched-set-recheck".to_string(),
            label: "running full watched-set recheck".to_string(),
            progress_done: Some(0),
            progress_total: None,
            window_start: None,
            window_end: None,
            started_at: Some(started_at),
            expected_resume_at: None,
        },
    }
}

fn apply_reconciliation_started_status(
    status: &mut RuntimeStatus,
    mode: ReconcileMode,
    started_at: DateTime<Utc>,
    daytime_window_start: Option<DateTime<Utc>>,
) {
    status.reconciliation.active = true;
    status.reconciliation.mode = Some(mode.label().to_string());
    status.reconciliation.phase = Some("starting".to_string());
    status.reconciliation.completed_titles = 0;
    status.reconciliation.total_titles = 0;
    status.reconciliation.phase_completed = 0;
    status.reconciliation.phase_total = 0;
    status.reconciliation.current_title = None;
    status.reconciliation.last_started_at = Some(started_at);
    status.reconciliation.last_result = None;
    status.daemon_state = if status.dry_run {
        "dry-run-running".to_string()
    } else {
        "running".to_string()
    };
    set_background_current_task(
        status,
        reconciliation_task(mode, started_at, daytime_window_start),
    );
    status.reconciliation.freshness = None;
    status.last_notice = Some(format!("{} started", mode.operator_label()));
    status.last_notice_at = Some(started_at);
}

fn apply_reconciliation_completed_status(
    status: &mut RuntimeStatus,
    mode: ReconcileMode,
    completed_at: DateTime<Utc>,
    daytime_window_start: Option<DateTime<Utc>>,
    last_result: String,
    notice: String,
) {
    let verification_failed = last_result.starts_with("failed:");
    status.reconciliation.active = false;
    status.reconciliation.phase = Some("idle".to_string());
    status.reconciliation.current_title = None;
    status.reconciliation.last_completed_at = Some(completed_at);
    status.reconciliation.last_result = Some(last_result.clone());
    set_background_current_task(
        status,
        idle_task("waiting for watched-page edits", completed_at),
    );
    if mode == ReconcileMode::CurrentDay {
        status.realtime.last_daytime_verification_at = Some(completed_at);
        status.realtime.last_daytime_verification_window_start = daytime_window_start;
        status.realtime.last_daytime_verification_window_end = Some(completed_at);
        status.realtime.last_daytime_verification_result = Some(last_result.clone());
    } else {
        status.realtime.last_nightly_full_recheck_at = Some(completed_at);
        status.realtime.last_nightly_full_recheck_result = Some(last_result.clone());
    }
    if verification_failed {
        status.realtime.state = "unhealthy".to_string();
        status.realtime.last_state_changed_at = Some(completed_at);
        status.realtime.latest_actionable_issue = Some(verification_failure_issue_for_mode(
            mode,
            &last_result,
            completed_at,
        ));
    } else if !status.realtime.catchup_active
        && active_runtime_backoff_until(&status.realtime, completed_at).is_none()
        && !latest_live_outcome_is_degraded(&status.realtime)
        && !latest_recovery_summary_is_degraded(&status.realtime)
        && !has_scheduled_verification_failure(&status.realtime)
        && !latest_persistent_issue_is_degraded(&status.realtime, mode)
    {
        status.realtime.state = "healthy".to_string();
        status.realtime.last_state_changed_at = Some(completed_at);
        if mode == ReconcileMode::Full {
            clear_actionable_issue_if_source(
                &mut status.realtime,
                &[
                    "last-24h-verification",
                    "full-watched-set-recheck",
                    "full-watched-set-freshness",
                    "recovery",
                    "stream",
                ],
            );
        } else {
            clear_actionable_issue_if_source(
                &mut status.realtime,
                &[
                    "last-24h-verification",
                    "full-watched-set-recheck",
                    "recovery",
                    "stream",
                ],
            );
        }
    } else if latest_persistent_issue_blocks_stream_healthy(&status.realtime)
        && matches!(status.realtime.state.as_str(), "" | "unknown" | "healthy")
    {
        status.realtime.state = "unhealthy".to_string();
        status.realtime.last_state_changed_at = Some(completed_at);
    }
    status.last_notice = Some(notice);
    status.last_notice_at = Some(completed_at);
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

fn latest_recovery_summary_is_degraded(status: &crate::state::RealtimeRuntimeStatus) -> bool {
    status
        .latest_recovery_summary
        .as_ref()
        .is_some_and(|summary| {
            summary.unresolved_count > 0 || summary.stopped_early_reason.is_some()
        })
}

fn has_scheduled_verification_failure(status: &crate::state::RealtimeRuntimeStatus) -> bool {
    status
        .last_daytime_verification_result
        .as_deref()
        .is_some_and(|result| result.starts_with("failed:"))
        || status
            .last_nightly_full_recheck_result
            .as_deref()
            .is_some_and(|result| result.starts_with("failed:"))
}

fn latest_persistent_issue_is_degraded(
    status: &crate::state::RealtimeRuntimeStatus,
    completed_mode: ReconcileMode,
) -> bool {
    status
        .latest_actionable_issue
        .as_ref()
        .is_some_and(|issue| {
            if completed_mode == ReconcileMode::Full && issue.source == "full-watched-set-freshness"
            {
                return false;
            }
            actionable_issue_blocks_stream_healthy(issue)
        })
}

fn latest_persistent_issue_blocks_stream_healthy(
    status: &crate::state::RealtimeRuntimeStatus,
) -> bool {
    status
        .latest_actionable_issue
        .as_ref()
        .is_some_and(actionable_issue_blocks_stream_healthy)
}

fn actionable_issue_blocks_stream_healthy(issue: &ActionableIssueSnapshot) -> bool {
    matches!(
        issue.source.as_str(),
        "full-watched-set-freshness" | "launch-path" | "pid-file" | "runtime-status"
    )
}

fn clear_actionable_issue_if_source(
    status: &mut crate::state::RealtimeRuntimeStatus,
    clearable_sources: &[&str],
) {
    if status
        .latest_actionable_issue
        .as_ref()
        .is_some_and(|issue| clearable_sources.contains(&issue.source.as_str()))
    {
        status.latest_actionable_issue = None;
    }
}

fn restore_persistent_issue(status: &mut RuntimeStatus, detected_at: DateTime<Utc>) {
    let Some(outcome) = status.realtime.latest_outcome.as_ref() else {
        if latest_recovery_summary_is_degraded(&status.realtime) {
            if let Some(summary) = status.realtime.latest_recovery_summary.as_ref() {
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "recovery".to_string(),
                    severity: "error".to_string(),
                    summary: render_recovery_notice(summary),
                    next_action: "review the recovery window and rerun catch-up if needed"
                        .to_string(),
                    detected_at: Some(detected_at),
                });
            }
        } else if let Some(issue) =
            scheduled_verification_failure_issue(&status.realtime, detected_at)
        {
            status.realtime.latest_actionable_issue = Some(issue);
        }
        return;
    };
    if outcome.mode == RevDelMode::Live.label() && outcome.outcome == "blocked" {
        status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
            source: "live-hide".to_string(),
            severity: "error".to_string(),
            summary: format!(
                "cannot hide revid {} because protection is blocked",
                outcome.revid
            ),
            next_action: "check auth and wiki-side rights immediately".to_string(),
            detected_at: Some(detected_at),
        });
    } else if outcome.mode == RevDelMode::Live.label()
        && matches!(
            outcome.outcome.as_str(),
            "failed" | "retrying" | "throttled" | "unresolved"
        )
    {
        status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
            source: "live-hide".to_string(),
            severity: "error".to_string(),
            summary: format!("live hide failed for revid {}", outcome.revid),
            next_action: "watch the recovery window and confirm a later successful hide"
                .to_string(),
            detected_at: Some(detected_at),
        });
    } else if latest_recovery_summary_is_degraded(&status.realtime) {
        if let Some(summary) = status.realtime.latest_recovery_summary.as_ref() {
            status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                source: "recovery".to_string(),
                severity: "error".to_string(),
                summary: render_recovery_notice(summary),
                next_action: "review the recovery window and rerun catch-up if needed".to_string(),
                detected_at: Some(detected_at),
            });
        }
    } else if let Some(issue) = scheduled_verification_failure_issue(&status.realtime, detected_at)
    {
        status.realtime.latest_actionable_issue = Some(issue);
    }
}

fn verification_failure_issue_for_mode(
    mode: ReconcileMode,
    result: &str,
    detected_at: DateTime<Utc>,
) -> ActionableIssueSnapshot {
    let (source, label, next_action) = match mode {
        ReconcileMode::CurrentDay => (
            "last-24h-verification",
            "Last 24 hours verification",
            "inspect the latest verification log or rerun Last 24 hours verification",
        ),
        ReconcileMode::Full => (
            "full-watched-set-recheck",
            "full watched-set recheck",
            "inspect the latest recheck log or rerun the full watched-set recheck",
        ),
    };
    ActionableIssueSnapshot {
        source: source.to_string(),
        severity: "error".to_string(),
        summary: format!("{label} {}", result),
        next_action: next_action.to_string(),
        detected_at: Some(detected_at),
    }
}

fn scheduled_verification_failure_issue(
    status: &crate::state::RealtimeRuntimeStatus,
    detected_at: DateTime<Utc>,
) -> Option<ActionableIssueSnapshot> {
    let daytime = status
        .last_daytime_verification_result
        .as_deref()
        .filter(|result| result.starts_with("failed:"))
        .map(|result| {
            (
                status.last_daytime_verification_at,
                verification_failure_issue_for_mode(ReconcileMode::CurrentDay, result, detected_at),
            )
        });
    let nightly = status
        .last_nightly_full_recheck_result
        .as_deref()
        .filter(|result| result.starts_with("failed:"))
        .map(|result| {
            (
                status.last_nightly_full_recheck_at,
                verification_failure_issue_for_mode(ReconcileMode::Full, result, detected_at),
            )
        });
    match (daytime, nightly) {
        (Some((daytime_at, daytime_issue)), Some((nightly_at, nightly_issue))) => {
            if nightly_at >= daytime_at {
                Some(nightly_issue)
            } else {
                Some(daytime_issue)
            }
        }
        (Some((_, issue)), None) | (None, Some((_, issue))) => Some(issue),
        (None, None) => None,
    }
}

fn converged_realtime_state_after_stream_open(
    status: &crate::state::RealtimeRuntimeStatus,
    now: DateTime<Utc>,
) -> String {
    if status.catchup_active || active_runtime_backoff_until(status, now).is_some() {
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
    if latest_recovery_summary_is_degraded(status)
        || has_scheduled_verification_failure(status)
        || latest_persistent_issue_blocks_stream_healthy(status)
    {
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
    if status.catchup_active || active_runtime_backoff_until(status, now).is_some() {
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
    if latest_recovery_summary_is_degraded(status)
        || has_scheduled_verification_failure(status)
        || latest_persistent_issue_blocks_stream_healthy(status)
    {
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

    use chrono::{TimeDelta, TimeZone};
    use tempfile::tempdir;

    use super::*;
    use crate::auth::AuthState;
    use crate::cache::RuntimeCache;
    use crate::cache::SuppressionListCache;
    use crate::config::{
        AppConfig, AuthConfig, CatchupConfig, DaytimeVerificationConfig, LoggingConfig,
        MatchingConfig, MetricsConfig, NightlySweepConfig, QueueConfig, RealtimeConfig,
        RetryConfig, RevDelConfig, StateConfig, SuppressionListConfig, WikiConfig,
    };
    use crate::metrics::snapshot_runtime_latency_metrics;
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
                randomized_window_minutes: 180,
                page_concurrency: 3,
                batch_sleep_ms: 17,
            },
            daytime_verification: DaytimeVerificationConfig {
                enabled: true,
                min_delay_seconds: 1,
                max_delay_seconds: 2,
                window_hours: 24,
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

    fn build_test_runtime(
        temp: &tempfile::TempDir,
        runtime_status_surface_mode: RuntimeStatusSurfaceMode,
    ) -> Arc<AppRuntime> {
        super::build_test_runtime_harness(temp, runtime_status_surface_mode).runtime
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
            "be.wikipedia.org".to_string(),
            revision_locks,
            processed,
            queue_depth.clone(),
            work_tx,
            runtime_status,
            temp.path().join("status.json"),
            RuntimeStatusSurfaceMode::DaemonOwned,
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
    async fn detached_command_dispatcher_does_not_persist_runtime_status_file() {
        let processed = Arc::new(RwLock::new(ProcessedRevidsState::default()));
        let revision_locks = Arc::new(KeyLockSet::new());
        let queue_depth = Arc::new(AtomicUsize::new(0));
        let (work_tx, mut work_rx) = mpsc::channel(1);
        let temp = tempdir().unwrap();
        let status_path = temp.path().join("status.json");
        let runtime_status = Arc::new(tokio::sync::Mutex::new(RuntimeStatus::default()));
        let dispatcher = ActionDispatcher::new(
            "be.wikipedia.org".to_string(),
            revision_locks,
            processed,
            queue_depth,
            work_tx,
            runtime_status,
            status_path.clone(),
            RuntimeStatusSurfaceMode::DetachedCommand,
        );

        dispatcher
            .dispatch_action_batch(
                "Title".to_string(),
                vec![7],
                None,
                None,
                None,
                RevDelMode::Catchup,
            )
            .await
            .unwrap();

        assert!(work_rx.try_recv().is_ok());
        assert!(!status_path.exists());
    }

    #[tokio::test]
    async fn dispatch_action_records_live_queue_timestamps_and_current_task() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let observed_at = Utc::now() - TimeDelta::seconds(2);

        harness
            .runtime
            .reconcile
            .actions
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![88],
                event_id: Some("evt-88".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(observed_at),
                recovery_trigger: None,
                completion_tx: None,
            })
            .await
            .unwrap();

        let action = harness.work_rx.try_recv().unwrap();
        let status = harness.runtime_status.lock().await.clone();
        let latest_outcome = status.realtime.latest_outcome.as_ref().unwrap();

        assert_eq!(action.title, "Foo");
        assert_eq!(action.revids, vec![88]);
        assert_eq!(action.event_id.as_deref(), Some("evt-88"));
        assert_eq!(action.observed_at, Some(observed_at));
        assert_eq!(status.realtime.queue_depth, 1);
        assert_eq!(
            status.realtime.last_action_queued_at,
            latest_outcome.queued_at
        );
        assert_eq!(latest_outcome.outcome, "queued");
        assert_eq!(latest_outcome.mode, RevDelMode::Live.label());
        assert_eq!(latest_outcome.source_label, RevDelMode::Live.source_label());
        assert_eq!(
            latest_outcome.revision_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/88")
        );
        assert_eq!(latest_outcome.observed_at, Some(observed_at));
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("live-hide")
        );
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.label.as_str()),
            Some("hiding watched edit Foo")
        );

        let latency = snapshot_runtime_latency_metrics();
        assert!(latency.observed_to_queue.sample_count >= 1);
        assert!(latency.observed_to_queue.latest_ms.unwrap() >= 1_000);
    }

    #[tokio::test]
    async fn dispatch_action_records_processed_live_revision_as_already_hidden() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        harness.runtime.processed.write().await.insert(88);

        harness
            .runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![88],
                event_id: Some("evt-88".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now()),
                recovery_trigger: None,
                completion_tx: None,
            })
            .await
            .unwrap();

        let status = harness.runtime_status.lock().await.clone();
        let outcome = status.realtime.latest_outcome.as_ref().unwrap();
        assert!(harness.work_rx.try_recv().is_err());
        assert_eq!(outcome.outcome, "already-hidden");
        assert_eq!(outcome.reason_code.as_deref(), Some("already-processed"));
        assert_eq!(outcome.mode, RevDelMode::Live.label());
    }

    #[tokio::test]
    async fn dispatch_action_records_duplicate_live_revision_as_skipped() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);

        harness
            .runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![88],
                event_id: Some("evt-88-a".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now()),
                recovery_trigger: None,
                completion_tx: None,
            })
            .await
            .unwrap();
        harness
            .runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![88],
                event_id: Some("evt-88-b".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now()),
                recovery_trigger: None,
                completion_tx: None,
            })
            .await
            .unwrap();

        let status = harness.runtime_status.lock().await.clone();
        let outcome = status.realtime.latest_outcome.as_ref().unwrap();
        assert!(harness.work_rx.try_recv().is_ok());
        assert!(harness.work_rx.try_recv().is_err());
        assert_eq!(outcome.outcome, "skipped");
        assert_eq!(outcome.reason_code.as_deref(), Some("duplicate-queued"));
        assert_eq!(outcome.mode, RevDelMode::Live.label());
    }

    #[tokio::test]
    async fn record_action_completed_surfaces_blocked_and_retrying_live_outcomes() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);

        harness
            .runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![88],
                event_id: Some("evt-88".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now()),
                recovery_trigger: None,
                completion_tx: None,
            })
            .await
            .unwrap();
        let action = harness.work_rx.try_recv().unwrap();

        harness
            .runtime
            .record_action_completed(&action, "blocked", Some("permissiondenied".to_string()), 1)
            .await;
        let blocked = harness.runtime_status.lock().await.clone();
        assert_eq!(blocked.realtime.state, "blocked");
        assert_eq!(
            blocked
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("live-hide")
        );
        assert_eq!(
            blocked
                .realtime
                .latest_outcome
                .as_ref()
                .map(|outcome| outcome.outcome.as_str()),
            Some("blocked")
        );

        harness
            .runtime
            .record_action_completed(&action, "retrying", Some("rate-limited".to_string()), 2)
            .await;
        let retrying = harness.runtime_status.lock().await.clone();
        assert_eq!(retrying.realtime.state, "unhealthy");
        assert_eq!(
            retrying
                .realtime
                .latest_outcome
                .as_ref()
                .map(|outcome| outcome.outcome.as_str()),
            Some("retrying")
        );
    }

    #[test]
    fn reconciliation_status_updates_preserve_active_live_hide_task() {
        let started_at = Utc.with_ymd_and_hms(2026, 4, 30, 9, 0, 0).unwrap();
        let completed_at = Utc.with_ymd_and_hms(2026, 4, 30, 9, 5, 0).unwrap();
        let daytime_window_start = Some(Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap());
        let mut status = RuntimeStatus::default();
        status.realtime.current_task = Some(CurrentTaskSnapshot {
            task_kind: "live-hide".to_string(),
            label: "hiding watched edit Foo".to_string(),
            progress_done: Some(0),
            progress_total: Some(1),
            window_start: None,
            window_end: None,
            started_at: Some(started_at),
            expected_resume_at: None,
        });

        apply_reconciliation_started_status(
            &mut status,
            ReconcileMode::CurrentDay,
            started_at,
            daytime_window_start,
        );

        assert!(status.reconciliation.active);
        assert_eq!(status.reconciliation.mode.as_deref(), Some("last-24h"));
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("live-hide")
        );

        apply_reconciliation_completed_status(
            &mut status,
            ReconcileMode::CurrentDay,
            completed_at,
            daytime_window_start,
            "completed".to_string(),
            "Last 24 hours verification completed".to_string(),
        );

        assert!(!status.reconciliation.active);
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("live-hide")
        );
        assert_eq!(
            status.realtime.last_daytime_verification_window_start,
            daytime_window_start
        );
        assert_eq!(
            status.realtime.last_daytime_verification_at,
            Some(completed_at)
        );
    }

    #[tokio::test]
    async fn source_refresh_status_does_not_overwrite_active_live_hide_task() {
        let temp = tempdir().unwrap();
        let mut harness =
            build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);

        harness
            .runtime
            .dispatch_action(RevDelDispatch {
                title: "Foo".to_string(),
                revids: vec![88],
                event_id: Some("evt-88".to_string()),
                user: Some("User".to_string()),
                comment: Some("Comment".to_string()),
                mode: RevDelMode::Live,
                observed_at: Some(Utc::now() - TimeDelta::seconds(1)),
                recovery_trigger: None,
                completion_tx: None,
            })
            .await
            .unwrap();

        let _action = harness.work_rx.try_recv().unwrap();
        harness
            .runtime
            .record_source_refresh(SourceListRefresh {
                trigger_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
                trigger_revid: Some(99),
                started_at: Some(Utc::now()),
                completed_at: Some(Utc::now()),
                outcome: "refreshed".to_string(),
                ..SourceListRefresh::default()
            })
            .await;

        let status = harness.runtime_status.lock().await.clone();
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("live-hide")
        );
        assert_eq!(
            status
                .realtime
                .last_source_refresh
                .as_ref()
                .map(|refresh| refresh.outcome.as_str()),
            Some("refreshed")
        );
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
            config.wiki.server_name.clone(),
            revision_locks,
            Arc::new(RwLock::new(ProcessedRevidsState::default())),
            queue_depth,
            work_tx,
            runtime_status_for_actions,
            temp.path().join("status.json"),
            RuntimeStatusSurfaceMode::DaemonOwned,
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
            runtime_status_surface_mode: RuntimeStatusSurfaceMode::DaemonOwned,
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
        assert_eq!(
            pass.daytime_window_hours,
            config.daytime_verification.window_hours
        );
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
    fn active_runtime_backoff_uses_shared_snapshot_and_filters_expired_values() {
        let now = DateTime::parse_from_rfc3339("2026-04-25T17:10:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let shared_until = now + TimeDelta::seconds(45);
        let legacy_until = now + TimeDelta::seconds(5);
        let expired = now - TimeDelta::seconds(1);

        let status = crate::state::RealtimeRuntimeStatus {
            backoff_until: Some(legacy_until),
            shared_backoff: Some(SharedBackoffSnapshot {
                source: "recovery".to_string(),
                reason: "rate-limit-backoff".to_string(),
                backoff_until: Some(shared_until),
                affected_paths: shared_backoff_paths(),
                live_hiding_blocked: false,
                recorded_at: Some(now),
            }),
            ..crate::state::RealtimeRuntimeStatus::default()
        };

        assert_eq!(
            active_runtime_backoff_until(&status, now),
            Some(shared_until)
        );

        let expired_status = crate::state::RealtimeRuntimeStatus {
            backoff_until: Some(expired),
            shared_backoff: Some(SharedBackoffSnapshot {
                backoff_until: Some(expired),
                ..SharedBackoffSnapshot::default()
            }),
            ..crate::state::RealtimeRuntimeStatus::default()
        };

        assert_eq!(active_runtime_backoff_until(&expired_status, now), None);
    }

    #[tokio::test]
    async fn api_retry_after_records_shared_backoff_without_blocking_live_hiding_contract() {
        let temp = tempdir().unwrap();
        let harness = build_test_runtime_harness(&temp, RuntimeStatusSurfaceMode::DetachedCommand);

        harness
            .runtime
            .record_api_failure(ApiFailureSnapshot {
                class: "http-status".to_string(),
                http_status: Some(429),
                retryable: true,
                retry_after_seconds: Some(30),
                operation: "revisiondelete".to_string(),
                message: "rate limited".to_string(),
                occurred_at: Some(Utc::now()),
                ..ApiFailureSnapshot::default()
            })
            .await;

        let status = harness.runtime_status.lock().await.clone();
        let shared = status.realtime.shared_backoff.as_ref().unwrap();
        assert_eq!(shared.source, "revisiondelete");
        assert_eq!(shared.reason, "api-retry-after");
        assert_eq!(shared.affected_paths, shared_backoff_paths());
        assert!(!shared.live_hiding_blocked);
        assert_eq!(status.realtime.backoff_until, shared.backoff_until);
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("revisiondelete")
        );
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
                source_label: RevDelMode::Live.source_label().to_string(),
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
                source_label: RevDelMode::Live.source_label().to_string(),
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

    #[test]
    fn offline_interval_helpers_track_active_gap_window() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();
        let recovered = now + TimeDelta::seconds(20);
        let mut status = crate::state::RealtimeRuntimeStatus::default();

        assert!(!offline_interval_active(&status));
        begin_offline_interval_if_needed(&mut status, now);
        assert!(offline_interval_active(&status));
        assert_eq!(status.last_offline_started_at, Some(now));

        end_offline_interval_if_active(&mut status, recovered);
        assert!(!offline_interval_active(&status));
        assert_eq!(status.last_offline_recovered_at, Some(recovered));
    }

    #[tokio::test]
    async fn mark_stream_reconnecting_starts_offline_interval_without_recovery_trigger() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);

        runtime
            .mark_stream_reconnecting(
                "stream-error".to_string(),
                "temporary network timeout".to_string(),
                "real-time stream reconnecting after error".to_string(),
            )
            .await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "reconnecting");
        assert_eq!(status.realtime.last_recovery_trigger, None);
        assert_eq!(
            status.realtime.last_reconnect_reason.as_deref(),
            Some("temporary network timeout")
        );
        assert!(status.realtime.last_offline_started_at.is_some());
        assert!(status.realtime.last_offline_recovered_at.is_none());
    }

    #[tokio::test]
    async fn stream_open_recovers_reconnect_noise_without_clearing_live_failure() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        runtime
            .update_runtime_status(|status| {
                status.realtime.latest_outcome = Some(SuppressionOutcomeSnapshot {
                    title: "Title".to_string(),
                    revid: 42,
                    outcome: "failed".to_string(),
                    mode: RevDelMode::Live.label().to_string(),
                    source_label: RevDelMode::Live.source_label().to_string(),
                    ..SuppressionOutcomeSnapshot::default()
                });
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "live-hide".to_string(),
                    severity: "error".to_string(),
                    summary: "live hide failed for revid 42".to_string(),
                    next_action: "watch the recovery window".to_string(),
                    detected_at: Some(Utc::now()),
                });
            })
            .await;
        runtime
            .mark_stream_reconnecting(
                "stream-error".to_string(),
                "temporary network timeout".to_string(),
                "real-time stream reconnecting after error".to_string(),
            )
            .await;

        runtime.mark_realtime_stream_open().await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "unhealthy");
        assert_eq!(status.realtime.last_reconnect_reason, None);
        assert!(status.realtime.last_offline_recovered_at.is_some());
        assert!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_some_and(|issue| issue.summary.contains("live hide failed"))
        );
    }

    #[tokio::test]
    async fn stream_open_keeps_failed_scheduled_verification_unhealthy() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        runtime
            .update_runtime_status(|status| {
                status.realtime.last_daytime_verification_at = Some(Utc::now());
                status.realtime.last_daytime_verification_result =
                    Some("failed: non-json-response".to_string());
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "last-24h-verification".to_string(),
                    severity: "error".to_string(),
                    summary: "Last 24 hours verification failed: non-json-response".to_string(),
                    next_action: "rerun Last 24 hours verification".to_string(),
                    detected_at: Some(Utc::now()),
                });
            })
            .await;
        runtime
            .mark_stream_reconnecting(
                "stream-error".to_string(),
                "temporary network timeout".to_string(),
                "real-time stream reconnecting after error".to_string(),
            )
            .await;

        runtime.mark_realtime_stream_open().await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "unhealthy");
        assert!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_some_and(|issue| issue.source == "last-24h-verification")
        );
        assert!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_some_and(|issue| issue.summary.contains("Last 24 hours verification failed"))
        );
    }

    #[tokio::test]
    async fn stream_open_keeps_stale_full_recheck_freshness_unhealthy() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        runtime
            .update_runtime_status(|status| {
                status.realtime.last_event_observed_at = Some(Utc::now() - TimeDelta::seconds(2));
                status.realtime.latest_actionable_issue = Some(ActionableIssueSnapshot {
                    source: "full-watched-set-freshness".to_string(),
                    severity: "warning".to_string(),
                    summary: "full watched-set coverage is stale for 7/10 pages".to_string(),
                    next_action: "run the full watched-set recheck".to_string(),
                    detected_at: Some(Utc::now()),
                });
            })
            .await;
        runtime
            .mark_stream_reconnecting(
                "stream-error".to_string(),
                "temporary network timeout".to_string(),
                "real-time stream reconnecting after error".to_string(),
            )
            .await;

        runtime.mark_realtime_stream_open().await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "unhealthy");
        assert_eq!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .map(|issue| issue.source.as_str()),
            Some("full-watched-set-freshness")
        );
    }

    #[tokio::test]
    async fn default_recovery_window_prefers_last_successful_hide() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let anchor = Utc.with_ymd_and_hms(2026, 4, 29, 8, 0, 0).unwrap();
        runtime
            .update_runtime_status(move |status| {
                status.realtime.last_successful_hide_at = Some(anchor);
            })
            .await;

        let end = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();
        let window = runtime.default_recovery_window(end).await;

        assert_eq!(window.start, anchor);
        assert_eq!(window.scope_label, "since last successful hide");
        assert!(window.allow_large_window);
    }

    #[tokio::test]
    async fn default_recovery_window_falls_back_to_configured_recent_window() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let end = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();

        let window = runtime.default_recovery_window(end).await;

        assert_eq!(
            window.start,
            end - chrono::TimeDelta::seconds(runtime.config.catchup.default_window_seconds)
        );
        assert_eq!(window.scope_label, "recent emergency window");
        assert!(!window.allow_large_window);
    }

    #[tokio::test]
    async fn mark_recovery_completed_converges_stale_state_to_healthy_when_clear() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        runtime
            .update_runtime_status(|status| {
                status.realtime.state = "stale".to_string();
                status.realtime.catchup_active = true;
                status.realtime.latest_actionable_issue =
                    Some(crate::state::ActionableIssueSnapshot {
                        source: "stream".to_string(),
                        severity: "warning".to_string(),
                        summary: "stream went stale".to_string(),
                        next_action: "watch the recovery window".to_string(),
                        detected_at: Some(Utc::now()),
                    });
            })
            .await;
        let summary = CoverageSummary {
            scope_label: Some("since last successful hide".to_string()),
            started_at: Some(Utc::now() - TimeDelta::minutes(5)),
            ended_at: Some(Utc::now()),
            requested_by: "stream-gap".to_string(),
            edits_checked: 4,
            ..CoverageSummary::default()
        };

        runtime.mark_recovery_completed(summary.clone()).await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "healthy");
        assert!(!status.realtime.catchup_active);
        assert!(status.realtime.latest_actionable_issue.is_none());
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("idle")
        );
        assert_eq!(status.realtime.latest_recovery_summary, Some(summary));
    }

    #[tokio::test]
    async fn mark_recovery_completed_converges_stale_state_to_unhealthy_when_unresolved_remain() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        runtime
            .update_runtime_status(|status| {
                status.realtime.state = "stale".to_string();
                status.realtime.catchup_active = true;
            })
            .await;
        let summary = CoverageSummary {
            scope_label: Some("recent emergency window".to_string()),
            started_at: Some(Utc::now() - TimeDelta::minutes(10)),
            ended_at: Some(Utc::now()),
            requested_by: "startup".to_string(),
            edits_checked: 2,
            unresolved_count: 2,
            ..CoverageSummary::default()
        };

        runtime.mark_recovery_completed(summary.clone()).await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "unhealthy");
        assert!(!status.realtime.catchup_active);
        assert!(
            status
                .realtime
                .latest_actionable_issue
                .as_ref()
                .is_some_and(|issue| issue.summary.contains("2 unresolved revisions remain"))
        );
        assert_eq!(status.realtime.latest_recovery_summary, Some(summary));
    }

    #[tokio::test]
    async fn freshness_probe_updates_precise_lag_and_source() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        let event_at = Utc::now() - chrono::TimeDelta::milliseconds(450);

        runtime
            .record_freshness_probe(
                event_at,
                "api-freshness-probe".to_string(),
                "probe updated lag".to_string(),
            )
            .await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(
            status.realtime.current_lag_source.as_deref(),
            Some("api-freshness-probe")
        );
        assert!(status.realtime.current_lag_seconds.is_some());
        assert!(
            status
                .realtime
                .current_lag_millis
                .is_some_and(|millis| millis >= 400)
        );
        assert!(status.realtime.last_freshness_probe_at.is_some());
    }

    #[tokio::test]
    async fn mark_stream_quiet_without_gap_keeps_idle_work_visible() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);

        runtime
            .mark_stream_quiet_without_gap(
                10,
                "stream quiet for 10s; freshness probe found no newer target-wiki edits"
                    .to_string(),
            )
            .await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "healthy");
        assert_eq!(
            status
                .realtime
                .current_task
                .as_ref()
                .map(|task| task.task_kind.as_str()),
            Some("idle")
        );
        assert!(
            status
                .realtime
                .latest_notice
                .as_deref()
                .is_some_and(|notice| notice.contains("no newer target-wiki edits"))
        );
    }

    #[tokio::test]
    async fn mark_stream_quiet_without_gap_clears_reconnect_noise_state() {
        let temp = tempdir().unwrap();
        let runtime = build_test_runtime(&temp, RuntimeStatusSurfaceMode::DetachedCommand);
        runtime
            .mark_stream_reconnecting(
                "stream-closed".to_string(),
                "event stream ended".to_string(),
                "real-time stream closed; reconnecting".to_string(),
            )
            .await;

        runtime
            .mark_stream_quiet_without_gap(
                10,
                "stream quiet for 10s; freshness probe found no newer target-wiki edits"
                    .to_string(),
            )
            .await;

        let status = runtime.reconcile.runtime_status.lock().await.clone();
        assert_eq!(status.realtime.state, "healthy");
        assert_eq!(status.realtime.last_recovery_trigger, None);
        assert_eq!(status.realtime.last_reconnect_reason, None);
        assert!(status.realtime.latest_actionable_issue.is_none());
        assert!(status.realtime.last_offline_recovered_at.is_some());
    }
}
