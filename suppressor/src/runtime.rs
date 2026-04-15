use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use anyhow::{Context, Result};
use chrono::Utc;
use metrics::gauge;
use tokio::sync::{RwLock, mpsc};
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
    NightlySweepProgress, ProcessedRevidsState, RuntimeStatus, load_json, save_json_atomic,
};

#[derive(Clone, Copy, Debug)]
pub enum RevDelMode {
    Live,
    Reconciliation,
    Manual,
}

pub struct RevDelAction {
    pub title: String,
    pub revids: Vec<u64>,
    pub event_id: Option<String>,
    pub user: Option<String>,
    pub comment: Option<String>,
    pub mode: RevDelMode,
    pub enqueued_at: Instant,
    pub _revision_guards: Vec<KeyLockGuard<u64>>,
}

pub struct ActionDispatcher {
    revision_locks: Arc<KeyLockSet<u64>>,
    processed: Arc<RwLock<ProcessedRevidsState>>,
    queue_depth: Arc<AtomicUsize>,
    work_tx: mpsc::Sender<RevDelAction>,
}

impl ActionDispatcher {
    pub fn new(
        revision_locks: Arc<KeyLockSet<u64>>,
        processed: Arc<RwLock<ProcessedRevidsState>>,
        queue_depth: Arc<AtomicUsize>,
        work_tx: mpsc::Sender<RevDelAction>,
    ) -> Self {
        Self {
            revision_locks,
            processed,
            queue_depth,
            work_tx,
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
        let mut guards = Vec::new();
        for revid in &revids {
            let Some(guard) = self.revision_locks.try_lock(*revid) else {
                tracing::debug!(
                    revid,
                    title = %title,
                    "skipping action because revision lock is already held"
                );
                return Ok(());
            };
            if self.processed.read().await.contains(*revid) {
                tracing::debug!(
                    revid,
                    title = %title,
                    "skipping action because revision is already processed"
                );
                return Ok(());
            }
            guards.push(guard);
        }
        self.queue_depth.fetch_add(1, Ordering::SeqCst);
        gauge!("queue_depth").set(self.queue_depth.load(Ordering::SeqCst) as f64);
        tracing::debug!(
            title = %title,
            revids = ?revids,
            event_id = ?event_id,
            mode = ?mode,
            queue_depth = self.queue_depth.load(Ordering::SeqCst),
            "queueing revisiondelete action"
        );
        self.work_tx
            .send(RevDelAction {
                title,
                revids,
                event_id,
                user,
                comment,
                mode,
                enqueued_at: Instant::now(),
                _revision_guards: guards,
            })
            .await
            .context("Failed to queue revisiondelete action")
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
    pub async fn run_reconciliation_pass(self: &Arc<Self>, mode: ReconcileMode) -> Result<()> {
        self.reconcile.run_reconciliation_pass(mode).await
    }
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
        AppConfig, AuthConfig, CurrentDayRecheckConfig, LoggingConfig, MatchingConfig,
        MetricsConfig, NightlySweepConfig, QueueConfig, RetryConfig, RevDelConfig, StateConfig,
        SuppressionListConfig, WikiConfig,
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
        let dispatcher =
            ActionDispatcher::new(revision_locks, processed, queue_depth.clone(), work_tx);

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
        let actions = Arc::new(ActionDispatcher::new(
            revision_locks,
            Arc::new(RwLock::new(ProcessedRevidsState::default())),
            queue_depth,
            work_tx,
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
}
