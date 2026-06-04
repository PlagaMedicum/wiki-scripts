use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, TimeDelta, Utc};
use tokio::signal::unix::{SignalKind, signal as unix_signal};
use tokio::sync::RwLock;
use tracing::{error, info, warn};

use crate::auth::{AuthState, authenticate, refresh_csrf_token};
use crate::cache::{
    CachePersistence, CacheRefreshMode, RuntimeCache, load_or_bootstrap, refresh_cache,
};
use crate::config::{AppConfig, EnvConfig, RuntimePaths, init_logging, load_env};
use crate::daemon_backlog::{
    DaemonState, HideTarget, MAX_PENDING_ITEMS, MAX_QUARANTINED_ITEMS, PROCESSED_CAPACITY,
    STATE_FILE_NAME, effective_realtime_state, is_blocking_failure, is_terminal_hide_failure,
    latest_quarantined_error, load_processed_revids, migrate_terminal_pending_to_quarantine,
    next_pending_retry_at, should_retry_after_fresh_auth, unresolved_count,
    unresolved_item_from_pending, upsert_pending, upsert_quarantined,
};
use crate::mw_api::{MediaWikiClient, RecentChangeRecord, classify_api_failure, revision_url};
use crate::runtime::{daemon_should_write_pid, launch_path_snapshot_from_paths};
use crate::signals;
use crate::state::{
    ActionableIssueSnapshot, ApiFailureSnapshot, CoverageSummary, CurrentTaskSnapshot,
    ExecutionLaneSnapshot, LaunchPathSnapshot, ProcessedRevidsState, RealtimeRuntimeStatus,
    RuntimeStatus, SuppressionOutcomeSnapshot, load_json, save_json_atomic, save_text_atomic,
};
use crate::titles::normalize_title;

pub(crate) const LAUNCH_KIND_ENV: &str = "SUPPRESSOR_LAUNCH_KIND";
pub(crate) const LAUNCH_LOG_PATH_ENV: &str = "SUPPRESSOR_LAUNCH_LOG_PATH";
pub(crate) const LAUNCH_WRITE_PID_ENV: &str = "SUPPRESSOR_LAUNCH_WRITE_PID";
pub(crate) const SERVER_START_LAUNCH_KIND: &str = "server-start";

const LIVE_POLL_INTERVAL_SECONDS: u64 = 1;
const QUARANTINE_VERIFY_INTERVAL_SECONDS: i64 = 300;
const QUARANTINE_VERIFY_PER_PASS: usize = 25;
const SMOKE_TEST_PAGE: &str = "Удзельнік:Plaga_med_Bot/suppressor/tests";

pub async fn run_daemon(config_path: PathBuf, dry_run: bool, verbose: bool) -> Result<()> {
    let mut daemon = Daemon::bootstrap(config_path, dry_run, verbose).await?;
    daemon.run().await
}

pub async fn run_smoke_test(
    config_path: PathBuf,
    page: Option<String>,
    verbose: bool,
) -> Result<()> {
    let mut daemon = Daemon::bootstrap(config_path, false, verbose).await?;
    let page = page.unwrap_or_else(|| SMOKE_TEST_PAGE.to_string());
    let marker = format!(
        "\n* suppressor smoke test {} UTC\n",
        Utc::now().format("%Y-%m-%d %H:%M:%S")
    );
    let summary = "suppressor controlled smoke test";
    let revid = daemon
        .client
        .append_text(&page, &marker, summary, &daemon.auth.csrf_token)
        .await
        .with_context(|| format!("failed to create smoke edit on {page}"))?;
    daemon
        .hide_revision(HideTarget {
            title: page.clone(),
            revid,
            observed_at: Some(Utc::now()),
            source_label: "smoke-test".to_string(),
        })
        .await
        .with_context(|| format!("failed to hide smoke revision {revid}"))?;
    daemon
        .verify_revision_hidden(&page, revid)
        .await
        .with_context(|| format!("smoke revision {revid} was hidden but verification failed"))?;
    println!("smoke-test.ok page={page} revid={revid} hidden=user|comment");
    Ok(())
}

struct Daemon {
    config: AppConfig,
    paths: RuntimePaths,
    env: EnvConfig,
    client: MediaWikiClient,
    auth: AuthState,
    cache: Arc<RwLock<RuntimeCache>>,
    state: DaemonState,
    processed: ProcessedRevidsState,
    dry_run: bool,
    launch_path: LaunchPathSnapshot,
    state_file: PathBuf,
    next_cache_refresh_at: DateTime<Utc>,
    next_quarantine_verify_at: DateTime<Utc>,
}

impl Daemon {
    async fn bootstrap(config_path: PathBuf, dry_run: bool, verbose: bool) -> Result<Self> {
        let config = AppConfig::load(&config_path)?;
        init_logging(&config.logging, verbose);
        let paths = RuntimePaths::resolve(&config_path, &config);
        std::fs::create_dir_all(&paths.state_dir)
            .with_context(|| format!("Failed to create {}", paths.state_dir.display()))?;
        let env = load_env(&paths.config_path)?;
        let client = MediaWikiClient::new_with_retry(&env, &config.retry)?;
        let state_file = paths.state_dir.join(STATE_FILE_NAME);
        let mut state: DaemonState = load_json(&state_file)?.unwrap_or_default();
        migrate_terminal_pending_to_quarantine(&mut state);
        let processed = load_processed_revids(&paths.processed_revids_file)?;
        let launch_path = launch_path_snapshot_from_paths(&paths, Utc::now());

        let mut daemon = Self {
            config,
            paths,
            env,
            client,
            auth: AuthState {
                username: String::new(),
                csrf_token: String::new(),
                rights: Default::default(),
            },
            cache: Arc::new(RwLock::new(RuntimeCache::from_snapshot(
                crate::cache::SuppressionListCache::initial(""),
            ))),
            state,
            processed,
            dry_run,
            launch_path,
            state_file,
            next_cache_refresh_at: Utc::now(),
            next_quarantine_verify_at: Utc::now(),
        };

        daemon
            .write_status(
                "starting",
                "daemon starting",
                None,
                Some(CurrentTaskSnapshot {
                    task_kind: "startup".to_string(),
                    label: "authenticating and loading watched titles".to_string(),
                    started_at: Some(Utc::now()),
                    ..CurrentTaskSnapshot::default()
                }),
            )
            .context("failed to publish startup status")?;

        daemon.auth = authenticate(&daemon.client, &daemon.env).await?;
        info!(
            authenticated_as = %daemon.auth.username,
            rights_count = daemon.auth.rights.len(),
            has_bot = daemon.auth.has_bot_right(),
            has_high_limits = daemon.auth.has_high_limits(),
            "daemon authenticated MediaWiki session"
        );

        daemon.cache = Arc::new(RwLock::new(
            load_or_bootstrap(
                &daemon.client,
                &daemon.config,
                &daemon.paths,
                persistence_for(daemon.dry_run),
            )
            .await?,
        ));
        daemon.next_cache_refresh_at = Utc::now()
            + TimeDelta::seconds(daemon.config.suppression_list.metadata_recheck_seconds as i64);
        daemon.resolve_quarantined_already_hidden().await;
        daemon.persist_state()?;
        Ok(daemon)
    }

    async fn run(&mut self) -> Result<()> {
        info!(
            dry_run = self.dry_run,
            config_path = %self.paths.config_path.display(),
            state_dir = %self.paths.state_dir.display(),
            api_url = %self.env.api_url,
            "daemon runtime started"
        );
        let write_pid = daemon_should_write_pid(self.dry_run);
        if write_pid {
            save_text_atomic(&self.paths.pid_file, &self.launch_path.pid.to_string())?;
            info!(pid_file = %self.paths.pid_file.display(), "wrote daemon pid file");
        }

        self.startup_catchup().await;
        self.write_status(
            "healthy",
            "daemon running",
            None,
            Some(idle_task_snapshot()),
        )?;

        // Legacy operator commands use Unix signals. The daemon must install
        // handlers before entering the steady loop so SIGHUP/SIGUSR1 are
        // commands, not fatal default actions.
        let mut reload_signal = signals::install_reload_listener().await?;
        let mut manual_sweep_signal = signals::install_manual_sweep_listener().await?;
        let mut terminate_signal =
            unix_signal(SignalKind::terminate()).context("failed to install SIGTERM listener")?;

        loop {
            tokio::select! {
                signal = tokio::signal::ctrl_c() => {
                    signal.context("failed to wait for Ctrl-C")?;
                    self.stop_gracefully(write_pid, "daemon stopping after Ctrl-C")?;
                    return Ok(());
                }
                Some(()) = terminate_signal.recv() => {
                    self.stop_gracefully(write_pid, "daemon stopping after SIGTERM")?;
                    return Ok(());
                }
                Some(()) = reload_signal.recv() => {
                    self.handle_reload_signal().await;
                }
                Some(()) = manual_sweep_signal.recv() => {
                    self.handle_manual_sweep_signal().await;
                }
                _ = tokio::time::sleep(Duration::from_secs(LIVE_POLL_INTERVAL_SECONDS)) => {
                    self.tick().await;
                }
            }
        }
    }

    fn stop_gracefully(&mut self, write_pid: bool, notice: &str) -> Result<()> {
        self.write_status("stopping", notice, None, None)?;
        if write_pid {
            remove_file_if_exists(&self.paths.pid_file)?;
        }
        self.write_status("stopped", "daemon stopped", None, None)?;
        info!(notice, "daemon stopped");
        Ok(())
    }

    async fn startup_catchup(&mut self) {
        let end = Utc::now();
        let start = self.startup_catchup_start(end);
        if let Err(error) = self
            .process_window(start, end, "startup-catchup", true)
            .await
        {
            self.record_poll_error(error, "startup-catchup", start, end);
        }
    }

    async fn tick(&mut self) {
        if let Err(error) = self.refresh_cache_if_due().await {
            self.record_error(error, "source-refresh", None, None);
        }
        self.resolve_quarantined_if_due().await;

        let end = Utc::now();
        let start = self.live_poll_start(end);
        match self.process_window(start, end, "live-poll", false).await {
            Ok(()) => {
                if let Err(error) = self.retry_pending_due().await {
                    self.record_error(error, "pending-retry", None, None);
                }
                if let Err(error) = self.write_status(
                    "healthy",
                    "recentchanges poll completed",
                    None,
                    Some(idle_task_snapshot()),
                ) {
                    error!(error = %error, "failed to write runtime status");
                }
            }
            Err(error) => {
                self.record_poll_error(error, "live-poll", start, end);
            }
        }
    }

    async fn resolve_quarantined_if_due(&mut self) {
        let now = Utc::now();
        if now < self.next_quarantine_verify_at {
            return;
        }
        self.next_quarantine_verify_at =
            now + TimeDelta::seconds(QUARANTINE_VERIFY_INTERVAL_SECONDS);
        self.resolve_quarantined_already_hidden().await;
    }

    async fn resolve_quarantined_already_hidden(&mut self) {
        if self.state.quarantined.is_empty() {
            return;
        }
        let items = self
            .state
            .quarantined
            .iter()
            .take(QUARANTINE_VERIFY_PER_PASS)
            .cloned()
            .collect::<Vec<_>>();
        let mut resolved = Vec::new();
        for item in items {
            let target = HideTarget {
                title: item.title.clone(),
                revid: item.revid,
                observed_at: item.observed_at,
                source_label: "quarantine-verification".to_string(),
            };
            if self.verify_terminal_failure_already_hidden(&target).await {
                resolved.push(item.revid);
            }
        }
        if resolved.is_empty() {
            return;
        }
        for revid in &resolved {
            self.processed.insert(*revid);
        }
        self.state
            .quarantined
            .retain(|item| !resolved.contains(&item.revid));
        self.state.latest_error = latest_quarantined_error(&self.state);
        if let Err(error) = self.persist_state() {
            error!(error = %error, "failed to persist resolved quarantine state");
            return;
        }
        info!(
            resolved_count = resolved.len(),
            "cleared quarantined revisiondelete failure(s) that are now hidden"
        );
    }

    async fn handle_reload_signal(&mut self) {
        info!("received watched-page reload signal");
        let started_at = Utc::now();
        if let Err(error) = self.write_status(
            "healthy",
            "operator requested watched-page cache reload",
            None,
            Some(CurrentTaskSnapshot {
                task_kind: "source-refresh".to_string(),
                label: "reloading watched-page cache".to_string(),
                started_at: Some(started_at),
                ..CurrentTaskSnapshot::default()
            }),
        ) {
            error!(error = %error, "failed to publish reload signal status");
        }
        self.next_cache_refresh_at = Utc::now()
            + TimeDelta::seconds(self.config.suppression_list.metadata_recheck_seconds as i64);
        match refresh_cache(
            &self.cache,
            &self.client,
            &self.config,
            &self.paths,
            CacheRefreshMode::Forced,
            persistence_for(self.dry_run),
        )
        .await
        {
            Ok(changed) => {
                let watched_count = self.cache.read().await.watched_titles().len();
                info!(
                    changed,
                    watched_count, "operator watched-page cache reload completed"
                );
                if let Err(error) = self.write_status(
                    "healthy",
                    "watched-page cache reload completed",
                    None,
                    Some(idle_task_snapshot()),
                ) {
                    error!(error = %error, "failed to publish reload completion status");
                }
            }
            Err(error) => self.record_error(error, "source-refresh", None, None),
        }
    }

    async fn handle_manual_sweep_signal(&mut self) {
        info!("received bounded manual recovery signal");
        let end = Utc::now();
        let start = self.startup_catchup_start(end);
        if let Err(error) = self
            .process_window(start, end, "manual-recovery", true)
            .await
        {
            self.record_poll_error(error, "manual-recovery", start, end);
            return;
        }
        if let Err(error) = self.retry_pending(true).await {
            self.record_error(error, "pending-retry", None, None);
            return;
        }
        if let Err(error) = self.write_status(
            "healthy",
            "bounded manual recovery completed",
            None,
            Some(idle_task_snapshot()),
        ) {
            error!(error = %error, "failed to publish manual recovery completion status");
        }
    }

    fn startup_catchup_start(&self, end: DateTime<Utc>) -> DateTime<Utc> {
        crate::daemon_windows::startup_catchup_start(&self.state, &self.config.catchup, end)
    }

    fn live_poll_start(&self, end: DateTime<Utc>) -> DateTime<Utc> {
        crate::daemon_windows::live_poll_start(&self.state, &self.config.catchup, end)
    }

    async fn refresh_cache_if_due(&mut self) -> Result<()> {
        if Utc::now() < self.next_cache_refresh_at {
            return Ok(());
        }
        self.next_cache_refresh_at = Utc::now()
            + TimeDelta::seconds(self.config.suppression_list.metadata_recheck_seconds as i64);
        let changed = refresh_cache(
            &self.cache,
            &self.client,
            &self.config,
            &self.paths,
            CacheRefreshMode::Automatic,
            persistence_for(self.dry_run),
        )
        .await?;
        if changed {
            let watched_count = self.cache.read().await.watched_titles().len();
            info!(watched_count, "watched title cache refreshed");
        }
        Ok(())
    }

    async fn process_window(
        &mut self,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
        source_label: &str,
        catchup: bool,
    ) -> Result<()> {
        self.write_status(
            if catchup { "catching-up" } else { "healthy" },
            &format!("{source_label} scanning recentchanges"),
            None,
            Some(CurrentTaskSnapshot {
                task_kind: source_label.to_string(),
                label: "scanning MediaWiki recentchanges".to_string(),
                window_start: Some(start),
                window_end: Some(end),
                started_at: Some(Utc::now()),
                ..CurrentTaskSnapshot::default()
            }),
        )?;
        let window = self
            .client
            .fetch_recent_changes_in_window(start, end, self.config.catchup.max_revisions_per_run)
            .await?;
        let mut changes = window.changes;
        changes.sort_by_key(|change| (change.timestamp, change.revid));

        if let Some(latest) = changes.last() {
            self.state.last_observed_change_at = Some(latest.timestamp);
        }

        let watched = self.cache.read().await.watched_set.clone();
        let mut watched_count = 0usize;
        for change in changes {
            if self.processed.contains(change.revid) {
                continue;
            }
            if !watched.contains(&normalize_title(&change.title)) {
                continue;
            }
            watched_count += 1;
            self.handle_watched_change(change, source_label).await?;
        }

        if window.truncated {
            let error = anyhow::anyhow!(
                "{source_label} hit recentchanges limit {}; preserving cursor for retry",
                self.config.catchup.max_revisions_per_run
            );
            return Err(error);
        }

        self.state.last_successful_poll_at = Some(end);
        self.state.latest_error = None;
        self.persist_state()?;
        if watched_count > 0 {
            info!(
                source_label,
                watched_count, "processed watched recentchanges"
            );
        }
        Ok(())
    }

    async fn handle_watched_change(
        &mut self,
        change: RecentChangeRecord,
        source_label: &str,
    ) -> Result<()> {
        info!(
            title = %change.title,
            revid = change.revid,
            source_label,
            "matched watched revision"
        );
        self.write_status(
            "healthy",
            "hiding watched revision",
            None,
            Some(CurrentTaskSnapshot {
                task_kind: "hide".to_string(),
                label: format!("hiding watched edit {}", change.revid),
                started_at: Some(Utc::now()),
                ..CurrentTaskSnapshot::default()
            }),
        )?;
        let target = HideTarget {
            title: change.title,
            revid: change.revid,
            observed_at: Some(change.timestamp),
            source_label: source_label.to_string(),
        };
        match self.hide_revision(target.clone()).await {
            Ok(()) => {
                self.record_hide_success(&target, "hidden")?;
                Ok(())
            }
            Err(error) => {
                self.record_hide_failure(&target, &error).await?;
                Ok(())
            }
        }
    }

    async fn retry_pending_due(&mut self) -> Result<()> {
        self.retry_pending(false).await
    }

    async fn retry_pending(&mut self, force: bool) -> Result<()> {
        migrate_terminal_pending_to_quarantine(&mut self.state);
        let now = Utc::now();
        let due = self
            .state
            .pending
            .iter()
            .filter(|item| force || item.retry_due(now))
            .cloned()
            .collect::<Vec<_>>();
        for item in due {
            let target = HideTarget {
                title: item.title,
                revid: item.revid,
                observed_at: item.observed_at,
                source_label: "pending-retry".to_string(),
            };
            match self.hide_revision(target.clone()).await {
                Ok(()) => self.record_hide_success(&target, "hidden-after-retry")?,
                Err(error) => self.record_hide_failure(&target, &error).await?,
            }
        }
        Ok(())
    }

    async fn hide_revision(&mut self, target: HideTarget) -> Result<()> {
        if self.dry_run {
            return Ok(());
        }
        let mut csrf = self.auth.csrf_token.clone();
        self.client
            .revision_delete_with_retry(
                &[target.revid],
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
                                .context("re-login failed")?;
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
                                .context("CSRF refresh failed")
                        }
                    }
                },
            )
            .await
            .with_context(|| format!("revisiondelete failed for revid {}", target.revid))?;
        self.auth.csrf_token = csrf;
        Ok(())
    }

    async fn verify_revision_hidden(&self, title: &str, revid: u64) -> Result<()> {
        let start = Utc::now() - TimeDelta::minutes(10);
        let revisions = self.client.fetch_revisions(title, Some(start)).await?;
        let Some(revision) = revisions
            .into_iter()
            .find(|revision| revision.revid == revid)
        else {
            bail!("revision {revid} not found during hidden-state verification");
        };
        if revision.user_hidden && revision.comment_hidden {
            return Ok(());
        }
        bail!(
            "revision {revid} is not fully hidden: user_hidden={} comment_hidden={}",
            revision.user_hidden,
            revision.comment_hidden
        );
    }

    fn record_hide_success(&mut self, target: &HideTarget, outcome: &str) -> Result<()> {
        let now = Utc::now();
        self.processed.insert(target.revid);
        self.state.pending.retain(|item| item.revid != target.revid);
        self.state
            .quarantined
            .retain(|item| item.revid != target.revid);
        self.state.last_successful_hide_at = Some(now);
        self.state.last_successful_hide_title = Some(target.title.clone());
        self.state.last_successful_hide_revid = Some(target.revid);
        self.state.last_successful_hide_source_label = Some(target.source_label.clone());
        self.state.latest_error = None;
        self.persist_state()?;
        self.write_status(
            "healthy",
            &format!("revision {} {outcome}", target.revid),
            None,
            Some(idle_task_snapshot()),
        )?;
        Ok(())
    }

    async fn record_hide_failure(
        &mut self,
        target: &HideTarget,
        error: &anyhow::Error,
    ) -> Result<()> {
        let failure = classify_api_failure(
            error,
            "revisiondelete",
            Some(&target.title),
            Some(target.revid),
        );
        if is_terminal_hide_failure(&failure)
            && self.verify_terminal_failure_already_hidden(target).await
        {
            self.record_hide_success(target, "already-hidden-after-terminal-failure")?;
            return Ok(());
        }
        if should_retry_after_fresh_auth(&failure) {
            match self.hide_revision_after_fresh_auth(target).await {
                Ok(()) => {
                    self.record_hide_success(target, "hidden-after-fresh-auth")?;
                    return Ok(());
                }
                Err(retry_error) => {
                    let retry_failure = classify_api_failure(
                        &retry_error,
                        "revisiondelete",
                        Some(&target.title),
                        Some(target.revid),
                    );
                    warn!(
                        title = %target.title,
                        revid = target.revid,
                        class = %retry_failure.class,
                        api_code = ?retry_failure.api_code,
                        http_status = ?retry_failure.http_status,
                        retryable = retry_failure.retryable,
                        message = %retry_failure.message,
                        "revisiondelete still failed after fresh authentication"
                    );
                    if is_terminal_hide_failure(&retry_failure)
                        && self.verify_terminal_failure_already_hidden(target).await
                    {
                        self.record_hide_success(target, "already-hidden-after-terminal-failure")?;
                        return Ok(());
                    }
                    return self.record_classified_hide_failure(target, retry_failure);
                }
            }
        }
        self.record_classified_hide_failure(target, failure)
    }

    async fn hide_revision_after_fresh_auth(&mut self, target: &HideTarget) -> Result<()> {
        warn!(
            title = %target.title,
            revid = target.revid,
            "revisiondelete returned permission failure; refreshing MediaWiki session before quarantine"
        );
        self.auth = authenticate(&self.client, &self.env)
            .await
            .context("re-login after permission failure failed")?;
        self.hide_revision(target.clone()).await
    }

    fn record_classified_hide_failure(
        &mut self,
        target: &HideTarget,
        failure: ApiFailureSnapshot,
    ) -> Result<()> {
        if is_terminal_hide_failure(&failure) {
            warn!(
                title = %target.title,
                revid = target.revid,
                class = %failure.class,
                api_code = ?failure.api_code,
                http_status = ?failure.http_status,
                retryable = failure.retryable,
                message = %failure.message,
                "revisiondelete returned terminal failure; quarantining item instead of retrying forever"
            );
            upsert_quarantined(&mut self.state, target, failure.clone());
            self.processed.insert(target.revid);
            self.state.latest_error = Some(failure.clone());
            self.persist_state()?;
            self.write_status(
                "degraded",
                &format!(
                    "revisiondelete terminal failure quarantined for revision {}",
                    target.revid
                ),
                Some(failure),
                Some(CurrentTaskSnapshot {
                    task_kind: "quarantined".to_string(),
                    label: format!(
                        "{} non-retryable revisiondelete failure(s) need review",
                        self.state.quarantined.len()
                    ),
                    started_at: Some(Utc::now()),
                    ..CurrentTaskSnapshot::default()
                }),
            )?;
            return Ok(());
        }
        warn!(
            title = %target.title,
            revid = target.revid,
            class = %failure.class,
            api_code = ?failure.api_code,
            http_status = ?failure.http_status,
            retryable = failure.retryable,
            message = %failure.message,
            "revisiondelete failed; keeping daemon alive and retaining pending item"
        );
        upsert_pending(&mut self.state, target, failure.clone());
        self.state.latest_error = Some(failure.clone());
        self.persist_state()?;
        self.write_status(
            if is_blocking_failure(&failure) {
                "blocked"
            } else {
                "degraded"
            },
            &format!("revisiondelete failed for revision {}", target.revid),
            Some(failure),
            Some(CurrentTaskSnapshot {
                task_kind: "pending-retry".to_string(),
                label: format!(
                    "retrying {} pending revisiondelete failure(s)",
                    self.state.pending.len()
                ),
                started_at: Some(Utc::now()),
                expected_resume_at: next_pending_retry_at(&self.state.pending),
                ..CurrentTaskSnapshot::default()
            }),
        )?;
        Ok(())
    }

    async fn verify_terminal_failure_already_hidden(&self, target: &HideTarget) -> bool {
        let since = target
            .observed_at
            .map(|observed| observed - TimeDelta::seconds(60))
            .unwrap_or_else(|| Utc::now() - TimeDelta::hours(24));
        match self
            .client
            .fetch_revisions(&target.title, Some(since))
            .await
        {
            Ok(revisions) => revisions.into_iter().any(|revision| {
                revision.revid == target.revid && revision.user_hidden && revision.comment_hidden
            }),
            Err(error) => {
                warn!(
                    title = %target.title,
                    revid = target.revid,
                    error = %error,
                    "could not verify hidden state after terminal revisiondelete failure"
                );
                false
            }
        }
    }

    fn record_poll_error(
        &mut self,
        error: anyhow::Error,
        operation: &str,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
    ) {
        let failure = classify_api_failure(&error, operation, None, None);
        self.state.latest_error = Some(failure.clone());
        if let Err(save_error) = self.persist_state() {
            error!(error = %save_error, "failed to persist poll failure state");
        }
        if let Err(status_error) = self.write_status(
            "degraded",
            &format!("{operation} failed: {}", failure.message),
            Some(failure),
            Some(CurrentTaskSnapshot {
                task_kind: operation.to_string(),
                label: "retrying recentchanges polling".to_string(),
                window_start: Some(start),
                window_end: Some(end),
                started_at: Some(Utc::now()),
                expected_resume_at: Some(
                    Utc::now() + TimeDelta::seconds(LIVE_POLL_INTERVAL_SECONDS as i64),
                ),
                ..CurrentTaskSnapshot::default()
            }),
        ) {
            error!(error = %status_error, "failed to write poll failure status");
        }
    }

    fn record_error(
        &mut self,
        error: anyhow::Error,
        operation: &str,
        sample_title: Option<&str>,
        sample_revid: Option<u64>,
    ) {
        let failure = classify_api_failure(&error, operation, sample_title, sample_revid);
        self.state.latest_error = Some(failure.clone());
        if let Err(save_error) = self.persist_state() {
            error!(error = %save_error, "failed to persist failure state");
        }
        if let Err(status_error) = self.write_status(
            if is_blocking_failure(&failure) {
                "blocked"
            } else {
                "degraded"
            },
            &format!("{operation} failed: {}", failure.message),
            Some(failure),
            Some(idle_task_snapshot()),
        ) {
            error!(error = %status_error, "failed to write error status");
        }
    }

    fn persist_state(&mut self) -> Result<()> {
        migrate_terminal_pending_to_quarantine(&mut self.state);
        self.state.pending.sort_by_key(|item| item.revid);
        self.state.quarantined.sort_by_key(|item| item.revid);
        if self.state.pending.len() > MAX_PENDING_ITEMS {
            let remove_count = self.state.pending.len() - MAX_PENDING_ITEMS;
            self.state.pending.drain(0..remove_count);
        }
        if self.state.quarantined.len() > MAX_QUARANTINED_ITEMS {
            let remove_count = self.state.quarantined.len() - MAX_QUARANTINED_ITEMS;
            self.state.quarantined.drain(0..remove_count);
        }
        self.processed.capacity = PROCESSED_CAPACITY;
        save_json_atomic(&self.state_file, &self.state)?;
        save_json_atomic(&self.paths.processed_revids_file, &self.processed)?;
        Ok(())
    }

    fn write_status(
        &self,
        requested_state: &str,
        notice: &str,
        latest_error: Option<ApiFailureSnapshot>,
        current_task: Option<CurrentTaskSnapshot>,
    ) -> Result<()> {
        let now = Utc::now();
        let effective_error = latest_error
            .clone()
            .or_else(|| self.state.latest_error.clone())
            .or_else(|| latest_quarantined_error(&self.state));
        let realtime_state = effective_realtime_state(
            requested_state,
            &self.state,
            effective_error.as_ref(),
            now,
            self.config.realtime.stale_threshold_seconds,
        );
        let latest_issue = effective_error
            .as_ref()
            .map(|failure| actionable_issue_for_failure(failure, now));
        let latest_outcome =
            self.state
                .last_successful_hide_revid
                .map(|revid| SuppressionOutcomeSnapshot {
                    title: self
                        .state
                        .last_successful_hide_title
                        .clone()
                        .unwrap_or_default(),
                    revid,
                    revision_url: Some(revision_url(&self.config.wiki.server_name, revid)),
                    outcome: "hidden".to_string(),
                    mode: if self.dry_run {
                        "dry-run".to_string()
                    } else {
                        "live".to_string()
                    },
                    source_label: self
                        .state
                        .last_successful_hide_source_label
                        .clone()
                        .unwrap_or_else(|| "daemon".to_string()),
                    completed_at: self.state.last_successful_hide_at,
                    ..SuppressionOutcomeSnapshot::default()
                });
        let status = RuntimeStatus {
            daemon_state: daemon_state_for(requested_state, self.dry_run),
            dry_run: self.dry_run,
            launch_path: Some(self.launch_path.clone()),
            last_notice: Some(notice.to_string()),
            last_notice_at: Some(now),
            realtime: RealtimeRuntimeStatus {
                state: realtime_state,
                last_state_changed_at: Some(now),
                stale_threshold_seconds: self.config.realtime.stale_threshold_seconds,
                stream_read_timeout_seconds: self.config.realtime.stream_read_timeout_seconds,
                last_event_observed_at: self.state.last_observed_change_at,
                last_successful_hide_at: self.state.last_successful_hide_at,
                last_successful_hide_title: self.state.last_successful_hide_title.clone(),
                last_successful_hide_revid: self.state.last_successful_hide_revid,
                last_successful_hide_url: self
                    .state
                    .last_successful_hide_revid
                    .map(|revid| revision_url(&self.config.wiki.server_name, revid)),
                current_lag_seconds: self
                    .state
                    .last_successful_poll_at
                    .map(|timestamp| now.signed_duration_since(timestamp).num_seconds().max(0)),
                current_lag_millis: self.state.last_successful_poll_at.map(|timestamp| {
                    now.signed_duration_since(timestamp)
                        .num_milliseconds()
                        .max(0)
                }),
                current_lag_source: Some("recentchanges-polling".to_string()),
                queue_depth: unresolved_count(&self.state),
                live_lane: ExecutionLaneSnapshot {
                    queue_depth: unresolved_count(&self.state),
                    queue_capacity: self.config.queue.capacity,
                    concurrency_limit: 1,
                    ..ExecutionLaneSnapshot::default()
                },
                background_lane: ExecutionLaneSnapshot {
                    queue_capacity: self.config.queue.capacity,
                    concurrency_limit: 1,
                    ..ExecutionLaneSnapshot::default()
                },
                daemon_started_at: self.launch_path.started_at,
                latest_error_code: effective_error
                    .as_ref()
                    .and_then(|failure| failure.api_code.clone())
                    .or_else(|| {
                        effective_error
                            .as_ref()
                            .map(|failure| failure.class.clone())
                    }),
                latest_error: effective_error,
                latest_actionable_issue: latest_issue,
                latest_notice: Some(notice.to_string()),
                latest_outcome,
                latest_recovery_summary: Some(self.coverage_summary()),
                current_task,
                catchup_active: requested_state == "catching-up",
                ..RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
        };
        save_json_atomic(&self.paths.runtime_status_file, &status)
    }

    fn coverage_summary(&self) -> CoverageSummary {
        let mut unresolved_items = self
            .state
            .pending
            .iter()
            .map(|item| {
                unresolved_item_from_pending(
                    item,
                    &self.config.wiki.server_name,
                    "daemon will retry automatically",
                )
            })
            .collect::<Vec<_>>();
        unresolved_items.extend(self.state.quarantined.iter().map(|item| {
            unresolved_item_from_pending(
                item,
                &self.config.wiki.server_name,
                "manual review required; daemon will not retry this non-retryable API failure automatically",
            )
        }));
        unresolved_items.truncate(self.config.catchup.unresolved_sample_limit);
        CoverageSummary {
            scope_label: Some("daemon pending queue".to_string()),
            requested_by: "daemon".to_string(),
            unresolved_count: unresolved_count(&self.state),
            unresolved_items,
            ..CoverageSummary::default()
        }
    }
}

fn actionable_issue_for_failure(
    failure: &ApiFailureSnapshot,
    detected_at: DateTime<Utc>,
) -> ActionableIssueSnapshot {
    ActionableIssueSnapshot {
        source: failure.operation.clone(),
        severity: if is_blocking_failure(failure) {
            "error".to_string()
        } else {
            "warning".to_string()
        },
        summary: failure.message.clone(),
        next_action: if is_blocking_failure(failure) {
            "inspect exact API code/status/content-type and verify deployed credentials/session on webtop".to_string()
        } else if is_terminal_hide_failure(failure) {
            "manual review required for this revision; daemon will not retry this non-retryable API failure automatically".to_string()
        } else {
            "daemon will retry automatically; inspect network/API health if this persists"
                .to_string()
        },
        detected_at: Some(detected_at),
    }
}

fn daemon_state_for(requested_state: &str, dry_run: bool) -> String {
    if requested_state == "stopped" {
        return "stopped".to_string();
    }
    if requested_state == "stopping" {
        return "stopping".to_string();
    }
    if dry_run {
        "dry-run-running".to_string()
    } else {
        "running".to_string()
    }
}

fn idle_task_snapshot() -> CurrentTaskSnapshot {
    CurrentTaskSnapshot {
        task_kind: "idle".to_string(),
        label: "waiting for watched-page edits".to_string(),
        started_at: Some(Utc::now()),
        ..CurrentTaskSnapshot::default()
    }
}

fn persistence_for(dry_run: bool) -> CachePersistence {
    if dry_run {
        CachePersistence::Ephemeral
    } else {
        CachePersistence::Persist
    }
}

fn remove_file_if_exists(path: &Path) -> Result<()> {
    match std::fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error).with_context(|| format!("Failed to remove {}", path.display())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn api_failure(class: &str) -> ApiFailureSnapshot {
        ApiFailureSnapshot {
            class: class.to_string(),
            operation: "revisiondelete".to_string(),
            message: "failed".to_string(),
            ..ApiFailureSnapshot::default()
        }
    }

    fn api_failure_with_code(class: &str, code: &str) -> ApiFailureSnapshot {
        ApiFailureSnapshot {
            api_code: Some(code.to_string()),
            retryable: false,
            ..api_failure(class)
        }
    }

    #[test]
    fn permission_failure_gets_fresh_auth_retry_before_quarantine() {
        let permission = api_failure_with_code("permission", "permissiondenied");
        let cantdelete = api_failure_with_code("permission", "cantdelete");
        let timeout = api_failure("timeout");

        assert!(should_retry_after_fresh_auth(&permission));
        assert!(is_terminal_hide_failure(&permission));
        assert!(should_retry_after_fresh_auth(&cantdelete));
        assert!(is_terminal_hide_failure(&cantdelete));
        assert!(!should_retry_after_fresh_auth(&timeout));
    }
}
