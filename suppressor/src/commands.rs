use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, TimeDelta, Utc};
use tokio::sync::RwLock;
use tracing::info;

use crate::auth::{AuthState, authenticate, refresh_csrf_token};
use crate::catchup::{CatchupRequest, format_summary_lines, run_catchup_window};
use crate::config::{AppConfig, EnvConfig, RuntimePaths, init_logging, load_env};
use crate::effective_config::render_effective_config;
use crate::mw_api::MediaWikiClient;
use crate::runtime::AppRuntime;
use crate::signals;
use crate::state::{
    CommandReportCounts, CommandReportSurface, CommandReportWindow, CompatibilityNotice,
    CoverageSummary, compatibility_notice_for_unreadable_surface, load_json, save_json_atomic,
};

pub struct CommandContext {
    pub config: AppConfig,
    pub paths: RuntimePaths,
}

impl CommandContext {
    pub fn load(config_path: &Path) -> Result<Self> {
        let config_path = config_path.to_path_buf();
        let config = AppConfig::load(&config_path)?;
        let paths = RuntimePaths::resolve(&config_path, &config);
        Ok(Self { config, paths })
    }

    pub fn init_logging(&self, verbose: bool) {
        init_logging(&self.config.logging, verbose);
    }
}

struct AuthenticatedCommandContext {
    command: CommandContext,
    env: EnvConfig,
    client: MediaWikiClient,
    auth: AuthState,
    auth_lock: Arc<RwLock<AuthState>>,
}

impl AuthenticatedCommandContext {
    async fn load(config_path: &Path, command_name: &str, verbose: bool) -> Result<Self> {
        let command = CommandContext::load(config_path)?;
        command.init_logging(verbose);
        info!(
            command = command_name,
            config_path = %command.paths.config_path.display(),
            "running command"
        );
        let env = load_env(&command.paths.config_path)?;
        let client = MediaWikiClient::new(&env)?;
        let auth = authenticate(&client, &env).await?;
        let auth_lock = Arc::new(RwLock::new(auth.clone()));
        Ok(Self {
            command,
            env,
            client,
            auth,
            auth_lock,
        })
    }
}

fn format_auth_status_lines(auth: &AuthState) -> Vec<String> {
    let mut rights = auth.rights.iter().cloned().collect::<Vec<_>>();
    rights.sort();
    vec![
        format!("auth.user={}", auth.username),
        format!("auth.bot={}", auth.has_bot_right()),
        format!("auth.rights={}", rights.join(",")),
    ]
}

fn format_hide_revid_result(revid: u64) -> String {
    format!("revdel.ok revid={revid}")
}

fn render_command_report_lines(summary: &crate::state::CoverageSummary) -> Vec<String> {
    format_summary_lines(summary)
}

fn next_action_for_summary(summary: &CoverageSummary, report_only: bool) -> Option<String> {
    if summary.backoff_until.is_some() {
        return Some("wait for backoff to expire and rerun the command".to_string());
    }
    if report_only && summary.unresolved_count > 0 {
        return Some(
            "run emergency catch-up without report-only if hiding should proceed".to_string(),
        );
    }
    if summary.unresolved_count > 0 {
        return Some(
            "review unresolved items and rerun the command if exposure remains".to_string(),
        );
    }
    None
}

fn command_report_compatibility_notice(paths: &RuntimePaths) -> Option<CompatibilityNotice> {
    let path = paths.command_report_file();
    if !path.exists() {
        return None;
    }
    match load_json::<CommandReportSurface>(&path) {
        Ok(_) => None,
        Err(_) => Some(compatibility_notice_for_unreadable_surface(
            "command-report",
            &path,
            "bounded command-report surface",
            "review the previous command report file and trust the newly written bounded report",
            "treat the last command summary as trustworthy only after the current binary rewrites a bounded command report",
            "remove the incompatible command report and rerun the last trusted command workflow if the new report cannot be regenerated",
        )),
    }
}

fn persist_command_report(
    paths: &RuntimePaths,
    command: &str,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
    report_only: bool,
    summary: &CoverageSummary,
) -> Result<()> {
    let report = CommandReportSurface {
        command: command.to_string(),
        generated_at: Some(Utc::now()),
        report_only,
        scope_label: summary.scope_label.clone(),
        window: CommandReportWindow {
            start: Some(start),
            end: Some(end),
        },
        counts: CommandReportCounts {
            checked: summary.edits_checked,
            hidden: summary.hidden_count,
            already_hidden: summary.already_hidden_count,
            skipped: summary.skipped_count,
            failed: summary.failed_count,
            unresolved: summary.unresolved_count,
        },
        unresolved_items: summary.unresolved_items.clone(),
        stopped_early_reason: summary.stopped_early_reason.clone(),
        backoff_until: summary.backoff_until,
        next_action: next_action_for_summary(summary, report_only),
        compatibility_notice: command_report_compatibility_notice(paths),
    };
    save_json_atomic(&paths.command_report_file(), &report)
}

pub async fn run_check_auth(config_path: PathBuf, verbose: bool) -> Result<()> {
    let command = AuthenticatedCommandContext::load(&config_path, "check-auth", verbose).await?;
    for line in format_auth_status_lines(&command.auth) {
        println!("{line}");
    }
    Ok(())
}

pub async fn run_hide_revid(config_path: PathBuf, revid: u64, verbose: bool) -> Result<()> {
    let command = AuthenticatedCommandContext::load(&config_path, "hide-revid", verbose).await?;
    info!(revid, "hiding revision from command");
    revision_delete_with_auth_context(&command, &[revid]).await?;
    println!("{}", format_hide_revid_result(revid));
    Ok(())
}

pub async fn run_emergency_catchup(
    config_path: PathBuf,
    start: Option<String>,
    end: Option<String>,
    allow_large_window: bool,
    dry_run: bool,
    report_only: bool,
    verbose: bool,
) -> Result<()> {
    let runtime = AppRuntime::bootstrap_for_command(config_path, dry_run, verbose).await?;
    let end = match end {
        Some(value) => parse_rfc3339_utc(&value)?,
        None => Utc::now(),
    };
    let recovery_window = runtime.default_recovery_window(end).await;
    let start = match start {
        Some(value) => parse_rfc3339_utc(&value)?,
        None => recovery_window.start,
    };
    let effective_allow_large_window =
        allow_large_window || start == recovery_window.start && recovery_window.allow_large_window;
    validate_window_bounds(
        start,
        end,
        runtime.config.catchup.max_window_seconds,
        effective_allow_large_window,
        report_only,
        "emergency-catchup",
    )?;
    let summary = run_catchup_window(
        &runtime,
        CatchupRequest {
            start,
            end,
            trigger: "operator-manual".to_string(),
            scope_label: if start == recovery_window.start {
                recovery_window.scope_label
            } else {
                "custom emergency window".to_string()
            },
            report_only,
            allow_large_window: effective_allow_large_window,
            title_scope: None,
        },
    )
    .await?;
    persist_command_report(
        &runtime.paths,
        "emergency-catchup",
        start,
        end,
        report_only,
        &summary,
    )?;
    for line in render_command_report_lines(&summary) {
        println!("{line}");
    }
    Ok(())
}

pub async fn run_coverage_last_24h(
    config_path: PathBuf,
    dry_run: bool,
    report_only: bool,
    verbose: bool,
) -> Result<()> {
    let runtime = AppRuntime::bootstrap_for_command(config_path, dry_run, verbose).await?;
    let end = Utc::now();
    let start = end - TimeDelta::hours(24);
    let summary = run_catchup_window(
        &runtime,
        CatchupRequest {
            start,
            end,
            trigger: "coverage-last-24h".to_string(),
            scope_label: "Last 24 hours".to_string(),
            report_only: report_only || dry_run,
            allow_large_window: true,
            title_scope: None,
        },
    )
    .await?;
    persist_command_report(
        &runtime.paths,
        "coverage-last-24h",
        start,
        end,
        report_only || dry_run,
        &summary,
    )?;
    for line in render_command_report_lines(&summary) {
        println!("{line}");
    }
    Ok(())
}

pub async fn run_coverage_report(
    config_path: PathBuf,
    start: String,
    end: Option<String>,
    allow_large_window: bool,
    dry_run: bool,
    report_only: bool,
    verbose: bool,
) -> Result<()> {
    let runtime = AppRuntime::bootstrap_for_command(config_path, dry_run, verbose).await?;
    let start = parse_rfc3339_utc(&start)?;
    let end = match end {
        Some(value) => parse_rfc3339_utc(&value)?,
        None => Utc::now(),
    };
    validate_window_bounds(
        start,
        end,
        runtime.config.catchup.max_window_seconds,
        allow_large_window,
        report_only || dry_run,
        "coverage-report",
    )?;
    let summary = run_catchup_window(
        &runtime,
        CatchupRequest {
            start,
            end,
            trigger: "coverage".to_string(),
            scope_label: "custom coverage window".to_string(),
            report_only: report_only || dry_run,
            allow_large_window,
            title_scope: None,
        },
    )
    .await?;
    persist_command_report(
        &runtime.paths,
        "coverage-report",
        start,
        end,
        report_only || dry_run,
        &summary,
    )?;
    for line in render_command_report_lines(&summary) {
        println!("{line}");
    }
    Ok(())
}

pub fn run_reload_cache(config_path: PathBuf) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    signals::send_reload(&command.paths.pid_file)
}

pub fn run_manual_sweep(config_path: PathBuf) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    signals::send_manual_sweep(&command.paths.pid_file)
}

pub fn run_print_effective_config(config_path: PathBuf, verbose: bool) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    command.init_logging(verbose);
    info!(
        config_path = %command.paths.config_path.display(),
        "rendering effective config"
    );
    let env = load_env(&command.paths.config_path)?;
    println!(
        "{}",
        render_effective_config(&command.config, &env, &command.paths.config_path)?
    );
    Ok(())
}

async fn revision_delete_with_auth_context(
    command: &AuthenticatedCommandContext,
    revids: &[u64],
) -> Result<()> {
    let mut csrf = command.auth.csrf_token.clone();
    command
        .client
        .revision_delete_with_retry(
            revids,
            &command.command.config.revdel.reason,
            &mut csrf,
            &command.command.config.retry,
            {
                let client = command.client.clone();
                let env = command.env.clone();
                let auth_lock = Arc::clone(&command.auth_lock);
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
                let client = command.client.clone();
                let auth_lock = Arc::clone(&command.auth_lock);
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
}

fn parse_rfc3339_utc(value: &str) -> Result<DateTime<Utc>> {
    Ok(DateTime::parse_from_rfc3339(value)
        .with_context(|| format!("invalid RFC3339 timestamp {value}"))?
        .with_timezone(&Utc))
}

fn validate_window_bounds(
    start: DateTime<Utc>,
    end: DateTime<Utc>,
    max_window_seconds: i64,
    allow_large_window: bool,
    report_only: bool,
    command_name: &str,
) -> Result<()> {
    if end < start {
        bail!(
            "{command_name} requires start <= end; got start={} end={}",
            start.to_rfc3339(),
            end.to_rfc3339()
        );
    }

    let window_seconds = end.signed_duration_since(start).num_seconds();
    if window_seconds > max_window_seconds && !allow_large_window && !report_only {
        bail!(
            "{command_name} window {}s exceeds configured max {}s; rerun with --allow-large-window or use --report-only",
            window_seconds,
            max_window_seconds
        );
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::*;
    use crate::auth::AuthState;
    use crate::state::{CommandReportSurface, CoverageSummary, UnresolvedExposureItem, load_json};

    fn test_runtime_paths(temp: &tempfile::TempDir) -> RuntimePaths {
        RuntimePaths {
            config_path: temp.path().join("config.toml"),
            state_dir: temp.path().join("state"),
            env_file: temp.path().join(".env"),
            cache_file: temp.path().join("cache.json"),
            last_event_id_file: temp.path().join("last_event_id.txt"),
            processed_revids_file: temp.path().join("processed.json"),
            nightly_sweep_progress_file: temp.path().join("progress.json"),
            runtime_status_file: temp.path().join("runtime_status.json"),
            pid_file: temp.path().join("daemon.pid"),
        }
    }

    #[test]
    fn command_context_resolves_pid_path() {
        let temp = tempfile::tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();

        let command = CommandContext::load(config_path.as_path()).unwrap();
        assert_eq!(
            command.paths.pid_file,
            temp.path().join("./state/daemon.pid")
        );
    }

    #[test]
    fn formats_compact_auth_status_lines() {
        let auth = AuthState {
            username: "ExampleBot".to_string(),
            csrf_token: "token".to_string(),
            rights: HashSet::from(["bot".to_string(), "edit".to_string()]),
        };

        assert_eq!(
            format_auth_status_lines(&auth),
            vec![
                "auth.user=ExampleBot".to_string(),
                "auth.bot=true".to_string(),
                "auth.rights=bot,edit".to_string(),
            ]
        );
    }

    #[test]
    fn formats_compact_hide_revid_result() {
        assert_eq!(format_hide_revid_result(42), "revdel.ok revid=42");
    }

    #[test]
    fn parses_rfc3339_utc_timestamp() {
        let parsed = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        assert_eq!(parsed.to_rfc3339(), "2026-04-24T16:00:00+00:00");
    }

    #[test]
    fn rejects_timestamp_without_timezone() {
        let error = parse_rfc3339_utc("2026-04-24T16:00:00").unwrap_err();
        assert!(error.to_string().contains("invalid RFC3339 timestamp"));
    }

    #[test]
    fn rejects_inverted_windows_before_api_work() {
        let start = parse_rfc3339_utc("2026-04-24T16:30:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();

        let error =
            validate_window_bounds(start, end, 1800, false, false, "coverage-report").unwrap_err();

        assert!(error.to_string().contains("requires start <= end"));
    }

    #[test]
    fn rejects_oversized_windows_without_override_or_report_only() {
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T17:00:01Z").unwrap();

        let error = validate_window_bounds(start, end, 3600, false, false, "emergency-catchup")
            .unwrap_err();

        assert!(error.to_string().contains("--allow-large-window"));
        assert!(error.to_string().contains("--report-only"));
    }

    #[test]
    fn accepts_oversized_windows_with_explicit_override() {
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T18:00:01Z").unwrap();

        validate_window_bounds(start, end, 3600, true, false, "coverage-report").unwrap();
    }

    #[test]
    fn accepts_oversized_windows_in_report_only_mode() {
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T18:00:01Z").unwrap();

        validate_window_bounds(start, end, 3600, false, true, "coverage-report").unwrap();
    }

    #[test]
    fn command_reports_redact_sensitive_reason_and_action_text() {
        let summary = CoverageSummary {
            requested_by: "coverage".to_string(),
            unresolved_count: 1,
            unresolved_items: vec![UnresolvedExposureItem {
                title: "Sensitive Page".to_string(),
                revid: 77,
                revision_url: Some("https://be.wikipedia.org/wiki/Special:Diff/77".to_string()),
                age_seconds: Some(45),
                reason: "revisiondelete failed token=abc123 cookie=sessionid".to_string(),
                next_action: "inspect response body: <html>bad</html> password=secret".to_string(),
            }],
            ..CoverageSummary::default()
        };

        let rendered = render_command_report_lines(&summary).join("\n");

        assert!(rendered.contains("coverage.unresolved_item"));
        assert!(rendered.contains("title=Sensitive Page"));
        assert!(rendered.contains("revid=77"));
        assert!(rendered.contains("age_seconds=45"));
        assert!(!rendered.contains("abc123"));
        assert!(!rendered.contains("sessionid"));
        assert!(!rendered.contains("<html>bad</html>"));
        assert!(!rendered.contains("password=secret"));
    }

    #[test]
    fn command_report_persists_to_separate_surface() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T16:05:00Z").unwrap();
        let summary = CoverageSummary {
            requested_by: "coverage".to_string(),
            edits_checked: 3,
            hidden_count: 1,
            already_hidden_count: 1,
            unresolved_count: 1,
            unresolved_items: vec![UnresolvedExposureItem {
                title: "Page".to_string(),
                revid: 42,
                revision_url: Some("https://be.wikipedia.org/wiki/Special:Diff/42".to_string()),
                age_seconds: Some(5),
                reason: "report-only-not-hidden".to_string(),
                next_action: "run emergency catch-up without report-only".to_string(),
            }],
            ..CoverageSummary::default()
        };

        persist_command_report(&paths, "coverage-report", start, end, true, &summary).unwrap();

        let report: CommandReportSurface =
            load_json(&paths.command_report_file()).unwrap().unwrap();
        assert_eq!(report.command, "coverage-report");
        assert!(report.report_only);
        assert_eq!(report.counts.checked, 3);
        assert_eq!(report.counts.hidden, 1);
        assert_eq!(report.counts.already_hidden, 1);
        assert_eq!(report.counts.unresolved, 1);
        assert_eq!(report.unresolved_items.len(), 1);
        assert_eq!(
            report.window.start.map(|value| value.to_rfc3339()),
            Some("2026-04-24T16:00:00+00:00".to_string())
        );
        assert!(!paths.runtime_status_file.exists());
    }

    #[test]
    fn invalid_previous_command_report_emits_compatibility_notice() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        std::fs::create_dir_all(&paths.state_dir).unwrap();
        std::fs::write(
            paths.command_report_file(),
            r#"{"command":"coverage-report","counts":"not-an-object"}"#,
        )
        .unwrap();
        let start = parse_rfc3339_utc("2026-04-24T16:00:00Z").unwrap();
        let end = parse_rfc3339_utc("2026-04-24T16:05:00Z").unwrap();

        persist_command_report(
            &paths,
            "coverage-report",
            start,
            end,
            false,
            &CoverageSummary::default(),
        )
        .unwrap();

        let report: CommandReportSurface =
            load_json(&paths.command_report_file()).unwrap().unwrap();
        assert_eq!(
            report
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.scope.as_str()),
            Some("command-report")
        );
        assert_eq!(
            report
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.severity.as_str()),
            Some("migration-required")
        );
        assert_eq!(
            report
                .compatibility_notice
                .as_ref()
                .map(|notice| notice.blocking),
            Some(true)
        );
    }
}
