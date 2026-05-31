use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, TimeDelta, Utc};
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use tracing::{error, info, warn};

use crate::auth::{AuthState, authenticate, refresh_csrf_token};
use crate::cache::{
    CachePersistence, CacheRefreshMode, RuntimeCache, load_or_bootstrap, refresh_cache,
};
use crate::config::{AppConfig, EnvConfig, RuntimePaths, init_logging, load_env};
use crate::mw_api::{MediaWikiClient, RecentChangeRecord, classify_api_failure, revision_url};
use crate::runtime::{daemon_should_write_pid, launch_path_snapshot_from_paths};
use crate::state::{
    ActionableIssueSnapshot, ApiFailureSnapshot, CoverageSummary, CurrentTaskSnapshot,
    ExecutionLaneSnapshot, LaunchPathSnapshot, ProcessedRevidsState, RealtimeRuntimeStatus,
    RuntimeStatus, SuppressionOutcomeSnapshot, UnresolvedExposureItem, load_json, save_json_atomic,
    save_text_atomic,
};
use crate::titles::normalize_title;

const STATE_FILE_NAME: &str = "simple_daemon_state.json";
const LIVE_POLL_INTERVAL_SECONDS: u64 = 1;
const LIVE_OVERLAP_SECONDS: i64 = 15;
const PENDING_RETRY_SECONDS: i64 = 30;
const PROCESSED_CAPACITY: usize = 10_000;
const MAX_PENDING_ITEMS: usize = 5_000;
const SMOKE_TEST_PAGE: &str = "Удзельнік:Plaga_med_Bot/suppressor/tests";

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
struct SimpleDaemonState {
    last_successful_poll_at: Option<DateTime<Utc>>,
    last_observed_change_at: Option<DateTime<Utc>>,
    last_successful_hide_at: Option<DateTime<Utc>>,
    last_successful_hide_title: Option<String>,
    last_successful_hide_revid: Option<u64>,
    last_successful_hide_source_label: Option<String>,
    latest_error: Option<ApiFailureSnapshot>,
    pending: Vec<PendingHide>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
struct PendingHide {
    title: String,
    revid: u64,
    observed_at: Option<DateTime<Utc>>,
    first_failed_at: DateTime<Utc>,
    last_failed_at: DateTime<Utc>,
    attempt_count: u32,
    last_error: Option<ApiFailureSnapshot>,
}

impl Default for PendingHide {
    fn default() -> Self {
        let now = Utc::now();
        Self {
            title: String::new(),
            revid: 0,
            observed_at: None,
            first_failed_at: now,
            last_failed_at: now,
            attempt_count: 0,
            last_error: None,
        }
    }
}

impl PendingHide {
    fn retry_due_at(&self) -> DateTime<Utc> {
        self.last_failed_at + TimeDelta::seconds(PENDING_RETRY_SECONDS)
    }

    fn retry_due(&self, now: DateTime<Utc>) -> bool {
        now >= self.retry_due_at()
    }

    fn is_blocking(&self) -> bool {
        self.last_error
            .as_ref()
            .map(is_blocking_failure)
            .unwrap_or(false)
    }
}

#[derive(Clone, Debug)]
struct HideTarget {
    title: String,
    revid: u64,
    observed_at: Option<DateTime<Utc>>,
    source_label: String,
}

pub async fn run_daemon(config_path: PathBuf, dry_run: bool, verbose: bool) -> Result<()> {
    let mut daemon = SimpleDaemon::bootstrap(config_path, dry_run, verbose).await?;
    daemon.run().await
}

pub async fn run_smoke_test(
    config_path: PathBuf,
    page: Option<String>,
    verbose: bool,
) -> Result<()> {
    let mut daemon = SimpleDaemon::bootstrap(config_path, false, verbose).await?;
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

struct SimpleDaemon {
    config: AppConfig,
    paths: RuntimePaths,
    env: EnvConfig,
    client: MediaWikiClient,
    auth: AuthState,
    cache: Arc<RwLock<RuntimeCache>>,
    state: SimpleDaemonState,
    processed: ProcessedRevidsState,
    dry_run: bool,
    launch_path: LaunchPathSnapshot,
    state_file: PathBuf,
    next_cache_refresh_at: DateTime<Utc>,
}

impl SimpleDaemon {
    async fn bootstrap(config_path: PathBuf, dry_run: bool, verbose: bool) -> Result<Self> {
        let config = AppConfig::load(&config_path)?;
        init_logging(&config.logging, verbose);
        let paths = RuntimePaths::resolve(&config_path, &config);
        std::fs::create_dir_all(&paths.state_dir)
            .with_context(|| format!("Failed to create {}", paths.state_dir.display()))?;
        let env = load_env(&paths.config_path)?;
        let client = MediaWikiClient::new_with_retry(&env, &config.retry)?;
        let state_file = paths.state_dir.join(STATE_FILE_NAME);
        let state = load_json(&state_file)?.unwrap_or_default();
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
        };

        daemon
            .write_status(
                "starting",
                "minimal daemon starting",
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
            "minimal daemon authenticated MediaWiki session"
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
        daemon.persist_state()?;
        Ok(daemon)
    }

    async fn run(&mut self) -> Result<()> {
        info!(
            dry_run = self.dry_run,
            config_path = %self.paths.config_path.display(),
            state_dir = %self.paths.state_dir.display(),
            api_url = %self.env.api_url,
            "minimal daemon runtime started"
        );
        let write_pid = daemon_should_write_pid(self.dry_run);
        if write_pid {
            save_text_atomic(&self.paths.pid_file, &self.launch_path.pid.to_string())?;
            info!(pid_file = %self.paths.pid_file.display(), "wrote daemon pid file");
        }

        self.startup_catchup().await;
        self.write_status(
            "healthy",
            "minimal daemon running",
            None,
            Some(idle_task_snapshot()),
        )?;

        loop {
            tokio::select! {
                signal = tokio::signal::ctrl_c() => {
                    signal.context("failed to wait for Ctrl-C")?;
                    self.write_status("stopping", "minimal daemon stopping", None, None)?;
                    if write_pid {
                        remove_file_if_exists(&self.paths.pid_file)?;
                    }
                    self.write_status("stopped", "minimal daemon stopped", None, None)?;
                    info!("minimal daemon stopped");
                    return Ok(());
                }
                _ = tokio::time::sleep(Duration::from_secs(LIVE_POLL_INTERVAL_SECONDS)) => {
                    self.tick().await;
                }
            }
        }
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

    fn startup_catchup_start(&self, end: DateTime<Utc>) -> DateTime<Utc> {
        let fallback = end - TimeDelta::seconds(self.config.catchup.default_window_seconds);
        let Some(cursor) = self.state.last_successful_poll_at else {
            return fallback;
        };
        let max_start = end - TimeDelta::seconds(self.config.catchup.max_window_seconds);
        cursor.max(max_start).min(end)
    }

    fn live_poll_start(&self, end: DateTime<Utc>) -> DateTime<Utc> {
        self.state
            .last_successful_poll_at
            .map(|cursor| cursor - TimeDelta::seconds(LIVE_OVERLAP_SECONDS))
            .unwrap_or_else(|| end - TimeDelta::seconds(self.config.catchup.default_window_seconds))
            .max(end - TimeDelta::seconds(self.config.catchup.max_window_seconds))
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
                self.record_hide_failure(&target, &error)?;
                Ok(())
            }
        }
    }

    async fn retry_pending_due(&mut self) -> Result<()> {
        let now = Utc::now();
        let due = self
            .state
            .pending
            .iter()
            .filter(|item| item.retry_due(now))
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
                Err(error) => self.record_hide_failure(&target, &error)?,
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

    fn record_hide_failure(&mut self, target: &HideTarget, error: &anyhow::Error) -> Result<()> {
        let failure = classify_api_failure(
            error,
            "revisiondelete",
            Some(&target.title),
            Some(target.revid),
        );
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
        self.state.pending.sort_by_key(|item| item.revid);
        if self.state.pending.len() > MAX_PENDING_ITEMS {
            let remove_count = self.state.pending.len() - MAX_PENDING_ITEMS;
            self.state.pending.drain(0..remove_count);
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
        let realtime_state = effective_realtime_state(
            requested_state,
            &self.state,
            latest_error.as_ref(),
            now,
            self.config.realtime.stale_threshold_seconds,
        );
        let latest_issue = latest_error.as_ref().map(|failure| ActionableIssueSnapshot {
            source: failure.operation.clone(),
            severity: if is_blocking_failure(failure) {
                "error".to_string()
            } else {
                "warning".to_string()
            },
            summary: failure.message.clone(),
            next_action: if is_blocking_failure(failure) {
                "inspect exact API code/status/content-type and verify deployed credentials/session on webtop".to_string()
            } else {
                "daemon will retry automatically; inspect network/API health if this persists".to_string()
            },
            detected_at: Some(now),
        });
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
                        .unwrap_or_else(|| "minimal-daemon".to_string()),
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
                queue_depth: self.state.pending.len(),
                live_lane: ExecutionLaneSnapshot {
                    queue_depth: self.state.pending.len(),
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
                latest_error_code: latest_error
                    .as_ref()
                    .and_then(|failure| failure.api_code.clone())
                    .or_else(|| latest_error.as_ref().map(|failure| failure.class.clone())),
                latest_error: latest_error.or_else(|| self.state.latest_error.clone()),
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
        CoverageSummary {
            scope_label: Some("minimal daemon pending queue".to_string()),
            requested_by: "minimal-daemon".to_string(),
            unresolved_count: self.state.pending.len(),
            unresolved_items: self
                .state
                .pending
                .iter()
                .take(self.config.catchup.unresolved_sample_limit)
                .map(|item| UnresolvedExposureItem {
                    title: item.title.clone(),
                    revid: item.revid,
                    revision_url: Some(revision_url(&self.config.wiki.server_name, item.revid)),
                    age_seconds: item
                        .observed_at
                        .map(|observed| Utc::now().signed_duration_since(observed).num_seconds()),
                    reason: item
                        .last_error
                        .as_ref()
                        .map(|failure| failure.message.clone())
                        .unwrap_or_else(|| "pending retry".to_string()),
                    next_action: "daemon will retry automatically".to_string(),
                })
                .collect(),
            ..CoverageSummary::default()
        }
    }
}

fn load_processed_revids(path: &Path) -> Result<ProcessedRevidsState> {
    let mut processed: ProcessedRevidsState = load_json(path)?.unwrap_or_default();
    if processed.capacity == 0 {
        processed.capacity = PROCESSED_CAPACITY;
    }
    Ok(processed)
}

fn upsert_pending(state: &mut SimpleDaemonState, target: &HideTarget, failure: ApiFailureSnapshot) {
    let now = Utc::now();
    if let Some(existing) = state
        .pending
        .iter_mut()
        .find(|item| item.revid == target.revid)
    {
        existing.last_failed_at = now;
        existing.attempt_count = existing.attempt_count.saturating_add(1);
        existing.last_error = Some(failure);
        return;
    }
    state.pending.push(PendingHide {
        title: target.title.clone(),
        revid: target.revid,
        observed_at: target.observed_at,
        first_failed_at: now,
        last_failed_at: now,
        attempt_count: 1,
        last_error: Some(failure),
    });
}

fn next_pending_retry_at(pending: &[PendingHide]) -> Option<DateTime<Utc>> {
    pending.iter().map(PendingHide::retry_due_at).min()
}

fn effective_realtime_state(
    requested_state: &str,
    state: &SimpleDaemonState,
    latest_error: Option<&ApiFailureSnapshot>,
    now: DateTime<Utc>,
    stale_threshold_seconds: u64,
) -> String {
    if matches!(
        requested_state,
        "starting" | "catching-up" | "stopping" | "stopped"
    ) {
        return requested_state.to_string();
    }
    if latest_error.map(is_blocking_failure).unwrap_or(false)
        || state.pending.iter().any(PendingHide::is_blocking)
    {
        return "blocked".to_string();
    }
    if latest_error.is_some() || !state.pending.is_empty() {
        return "degraded".to_string();
    }
    let poll_is_fresh = state
        .last_successful_poll_at
        .map(|timestamp| {
            now.signed_duration_since(timestamp).num_seconds() <= stale_threshold_seconds as i64
        })
        .unwrap_or(false);
    if poll_is_fresh {
        "healthy".to_string()
    } else {
        "degraded".to_string()
    }
}

fn is_blocking_failure(failure: &ApiFailureSnapshot) -> bool {
    matches!(failure.class.as_str(), "permission" | "auth-session")
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

    #[test]
    fn startup_catchup_uses_recent_window_without_cursor() {
        let end = DateTime::parse_from_rfc3339("2026-05-31T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let state = SimpleDaemonState::default();
        let start = state
            .last_successful_poll_at
            .unwrap_or(end - TimeDelta::seconds(1800));

        assert_eq!(start, end - TimeDelta::seconds(1800));
    }

    #[test]
    fn permission_pending_blocks_health() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            pending: vec![PendingHide {
                revid: 1,
                last_error: Some(api_failure("permission")),
                ..PendingHide::default()
            }],
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "blocked"
        );
    }

    #[test]
    fn nonblocking_pending_degrades_health() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            pending: vec![PendingHide {
                revid: 1,
                last_error: Some(api_failure("non-json-response")),
                ..PendingHide::default()
            }],
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "degraded"
        );
    }

    #[test]
    fn fresh_empty_state_is_healthy() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "healthy"
        );
    }

    #[test]
    fn stale_empty_state_is_degraded() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now - TimeDelta::seconds(30)),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "degraded"
        );
    }

    #[test]
    fn upsert_pending_preserves_single_item_per_revision() {
        let mut state = SimpleDaemonState::default();
        let target = HideTarget {
            title: "Title".to_string(),
            revid: 42,
            observed_at: None,
            source_label: "test".to_string(),
        };

        upsert_pending(&mut state, &target, api_failure("timeout"));
        upsert_pending(&mut state, &target, api_failure("timeout"));

        assert_eq!(state.pending.len(), 1);
        assert_eq!(state.pending[0].attempt_count, 2);
    }
}
