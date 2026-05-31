use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command as ProcessCommand, Stdio};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail, ensure};
use chrono::{DateTime, TimeDelta, Utc};
use nix::errno::Errno;
use nix::sys::signal::{Signal, kill};
use nix::unistd::{Pid, setsid};
use tokio::sync::RwLock;
use tracing::{info, warn};

use crate::auth::{AuthState, authenticate, refresh_csrf_token};
use crate::catchup::{CatchupRequest, format_summary_lines, run_catchup_window};
use crate::config::{
    AppConfig, EnvConfig, RuntimePaths, default_log_filter, init_logging, load_env,
};
use crate::daemon::{
    LAUNCH_KIND_ENV, LAUNCH_LOG_PATH_ENV, LAUNCH_WRITE_PID_ENV, SERVER_START_LAUNCH_KIND,
};
use crate::effective_config::render_effective_config;
use crate::mw_api::MediaWikiClient;
use crate::runtime::AppRuntime;
use crate::signals;
use crate::state::{
    CommandReportCounts, CommandReportSurface, CommandReportWindow, CompatibilityNotice,
    CoverageSummary, RuntimeStatus, compatibility_notice_for_unreadable_surface, load_json,
    load_text, save_json_atomic, save_text_atomic,
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
        let client = MediaWikiClient::new_with_retry(&env, &command.config.retry)?;
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

#[derive(Debug, PartialEq, Eq)]
struct ServerStartReceipt {
    mode: &'static str,
    pid: i32,
    supervisor_pid: i32,
    config_path: PathBuf,
    pid_file: PathBuf,
    runtime_status_file: PathBuf,
    log_path: PathBuf,
}

enum ServerStartProbe {
    Ready(ServerStartReceipt),
    Pending(String),
    Failed(String),
}

const SUPERVISOR_PID_FILE_NAME: &str = "supervisor.pid";
const SUPERVISOR_RESTART_INITIAL_SECONDS: u64 = 1;
const SUPERVISOR_RESTART_MAX_SECONDS: u64 = 30;
const SUPERVISOR_STABLE_RUN_SECONDS: u64 = 60;

pub fn run_server_start(
    config_path: PathBuf,
    dry_run: bool,
    status_timeout_seconds: u64,
    log_file: Option<PathBuf>,
    verbose: bool,
) -> Result<()> {
    ensure!(
        status_timeout_seconds > 0,
        "server-start requires --status-timeout-seconds greater than zero"
    );
    let command = CommandContext::load(&config_path)?;
    let log_path =
        resolve_server_start_log_path(&command.paths.config_path, &command.paths, log_file);
    prepare_server_start_paths(&command.paths, &log_path)?;
    let _env = load_env(&command.paths.config_path)?;
    let current_exe =
        std::env::current_exe().context("failed to resolve current suppressor binary")?;
    reject_or_clear_existing_processes(&command.paths, &current_exe)?;
    let spawned_at = Utc::now();
    let (mut child, supervisor_pid) =
        spawn_server_start_supervisor(&current_exe, &command.paths, &log_path, dry_run, verbose)?;
    let timeout = Duration::from_secs(status_timeout_seconds);
    match wait_for_server_start(
        &mut child,
        &command.paths,
        &log_path,
        supervisor_pid,
        dry_run,
        spawned_at,
        timeout,
    ) {
        Ok(receipt) => {
            for line in format_server_start_receipt_lines(&receipt) {
                println!("{line}");
            }
            Ok(())
        }
        Err(error) => {
            terminate_child(&mut child, supervisor_pid);
            if let Err(cleanup_error) = cleanup_failed_server_start_evidence(
                &command.paths,
                supervisor_pid,
                dry_run,
                spawned_at,
            ) {
                warn!(
                    supervisor_pid,
                    error = %cleanup_error,
                    "failed to clean server-start evidence after launch failure"
                );
            }
            Err(error)
        }
    }
}

fn resolve_server_start_log_path(
    config_path: &Path,
    paths: &RuntimePaths,
    log_file: Option<PathBuf>,
) -> PathBuf {
    match log_file {
        Some(path) if path.is_absolute() => path,
        Some(path) => config_path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join(path),
        None => paths.state_dir.join("daemon.log"),
    }
}

fn prepare_server_start_paths(paths: &RuntimePaths, log_path: &Path) -> Result<()> {
    fs::create_dir_all(&paths.state_dir)
        .with_context(|| format!("failed to create {}", paths.state_dir.display()))?;
    let supervisor_pid_file = supervisor_pid_path(paths);
    for path in [
        paths.cache_file.as_path(),
        paths.last_event_id_file.as_path(),
        paths.processed_revids_file.as_path(),
        paths.nightly_sweep_progress_file.as_path(),
        paths.runtime_status_file.as_path(),
        paths.pid_file.as_path(),
        supervisor_pid_file.as_path(),
        log_path,
    ] {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }
    }
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)
        .with_context(|| format!("failed to open detached daemon log {}", log_path.display()))?;
    Ok(())
}

fn supervisor_pid_path(paths: &RuntimePaths) -> PathBuf {
    paths.state_dir.join(SUPERVISOR_PID_FILE_NAME)
}

fn reject_or_clear_existing_processes(paths: &RuntimePaths, current_exe: &Path) -> Result<()> {
    reject_or_clear_pid(
        &paths.pid_file,
        current_exe,
        "daemon",
        "server-start refused duplicate daemon",
    )?;
    reject_or_clear_pid(
        &supervisor_pid_path(paths),
        current_exe,
        "supervisor",
        "server-start refused duplicate supervisor",
    )
}

fn reject_or_clear_pid(
    pid_file: &Path,
    current_exe: &Path,
    process_label: &str,
    duplicate_message: &str,
) -> Result<()> {
    let Some(pid) = read_positive_pid(pid_file)? else {
        return Ok(());
    };
    if process_is_running(pid) && live_pid_matches_binary_name(pid, current_exe) {
        bail!(
            "{}: {} points to live {} PID {}; stop the existing supervisor path first",
            duplicate_message,
            pid_file.display(),
            process_label,
            pid
        );
    }
    fs::remove_file(pid_file).with_context(|| {
        format!(
            "failed to remove stale {} PID file {} for non-running PID {}",
            process_label,
            pid_file.display(),
            pid
        )
    })?;
    Ok(())
}

#[allow(dead_code)]
fn reject_or_clear_existing_pid(paths: &RuntimePaths, current_exe: &Path) -> Result<()> {
    let Some(pid) = read_positive_pid(&paths.pid_file)? else {
        return Ok(());
    };
    if process_is_running(pid) && live_pid_matches_binary_name(pid, current_exe) {
        bail!(
            "server-start refused duplicate daemon: {} points to live PID {}; stop the existing daemon first",
            paths.pid_file.display(),
            pid
        );
    }
    fs::remove_file(&paths.pid_file).with_context(|| {
        format!(
            "failed to remove stale PID file {} for non-running PID {}",
            paths.pid_file.display(),
            pid
        )
    })?;
    Ok(())
}

fn read_positive_pid(path: &Path) -> Result<Option<i32>> {
    let Some(raw) = load_text(path)? else {
        return Ok(None);
    };
    let pid: i32 = raw
        .parse()
        .with_context(|| format!("invalid PID file {}", path.display()))?;
    ensure!(
        pid > 0,
        "invalid non-positive PID {} in {}",
        pid,
        path.display()
    );
    Ok(Some(pid))
}

fn process_is_running(pid: i32) -> bool {
    match kill(Pid::from_raw(pid), None) {
        Ok(()) => true,
        Err(Errno::EPERM) => true,
        Err(Errno::ESRCH) => false,
        Err(_) => false,
    }
}

fn live_pid_matches_binary_name(pid: i32, current_exe: &Path) -> bool {
    let Some(current_name) = current_exe.file_name() else {
        return false;
    };
    let Ok(proc_exe) = std::fs::read_link(format!("/proc/{pid}/exe")) else {
        return false;
    };
    proc_exe
        .file_name()
        .is_some_and(|name| name == current_name)
}

fn spawn_server_start_supervisor(
    current_exe: &Path,
    paths: &RuntimePaths,
    log_path: &Path,
    dry_run: bool,
    verbose: bool,
) -> Result<(Child, i32)> {
    let stdout_log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)
        .with_context(|| format!("failed to open detached daemon log {}", log_path.display()))?;
    let stderr_log = stdout_log
        .try_clone()
        .with_context(|| format!("failed to clone detached daemon log {}", log_path.display()))?;
    let log_filter =
        std::env::var("RUST_LOG").unwrap_or_else(|_| default_log_filter(verbose).to_string());
    let mut supervisor_command = ProcessCommand::new(current_exe);
    supervisor_command
        .arg("--config")
        .arg(&paths.config_path)
        .env("BEWIKI_ENV_FILE", &paths.env_file)
        .env("RUST_LOG", log_filter)
        .env("BEWIKI_LOG_FORMAT", "text")
        .env("NO_COLOR", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_log))
        .stderr(Stdio::from(stderr_log));
    if verbose {
        supervisor_command.arg("--verbose");
    }
    supervisor_command.arg("supervisor-run");
    if dry_run {
        supervisor_command.arg("--dry-run");
    }
    supervisor_command.arg("--log-file").arg(log_path);
    // Safety: the closure only calls async-signal-safe setsid before exec to detach from SSH.
    unsafe {
        supervisor_command.pre_exec(|| {
            setsid()
                .map(|_| ())
                .map_err(|errno| std::io::Error::from_raw_os_error(errno as i32))
        });
    }
    let child = supervisor_command.spawn().with_context(|| {
        format!(
            "failed to spawn detached supervisor {}",
            current_exe.display()
        )
    })?;
    let child_pid =
        i32::try_from(child.id()).context("detached supervisor PID does not fit in i32")?;
    Ok((child, child_pid))
}

fn spawn_daemon_child(
    current_exe: &Path,
    paths: &RuntimePaths,
    log_path: &Path,
    dry_run: bool,
    verbose: bool,
) -> Result<(Child, i32)> {
    let stdout_log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)
        .with_context(|| format!("failed to open detached daemon log {}", log_path.display()))?;
    let stderr_log = stdout_log
        .try_clone()
        .with_context(|| format!("failed to clone detached daemon log {}", log_path.display()))?;
    let log_filter =
        std::env::var("RUST_LOG").unwrap_or_else(|_| default_log_filter(verbose).to_string());
    let mut child_command = ProcessCommand::new(current_exe);
    child_command
        .arg("--config")
        .arg(&paths.config_path)
        .env("BEWIKI_ENV_FILE", &paths.env_file)
        .env("RUST_LOG", log_filter)
        .env("BEWIKI_LOG_FORMAT", "text")
        .env("NO_COLOR", "1")
        .env(LAUNCH_KIND_ENV, SERVER_START_LAUNCH_KIND)
        .env(LAUNCH_LOG_PATH_ENV, log_path)
        .env(LAUNCH_WRITE_PID_ENV, "1")
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_log))
        .stderr(Stdio::from(stderr_log));
    if verbose {
        child_command.arg("--verbose");
    }
    child_command.arg(if dry_run { "dry-run" } else { "run" });
    let child = child_command.spawn().with_context(|| {
        format!(
            "failed to spawn supervised daemon {}",
            current_exe.display()
        )
    })?;
    let child_pid =
        i32::try_from(child.id()).context("supervised daemon PID does not fit in i32")?;
    Ok((child, child_pid))
}

pub fn run_supervisor(
    config_path: PathBuf,
    dry_run: bool,
    log_path: PathBuf,
    verbose: bool,
) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    prepare_server_start_paths(&command.paths, &log_path)?;
    let current_exe =
        std::env::current_exe().context("failed to resolve current suppressor binary")?;
    let supervisor_pid = std::process::id() as i32;
    save_text_atomic(
        &supervisor_pid_path(&command.paths),
        &supervisor_pid.to_string(),
    )?;
    eprintln!(
        "supervisor started mode={} supervisor_pid={} log={}",
        if dry_run { "dry-run" } else { "live" },
        supervisor_pid,
        log_path.display()
    );

    let mut restart_delay = Duration::from_secs(SUPERVISOR_RESTART_INITIAL_SECONDS);
    loop {
        let child_started = Instant::now();
        match spawn_daemon_child(&current_exe, &command.paths, &log_path, dry_run, verbose) {
            Ok((mut child, daemon_pid)) => {
                eprintln!("supervisor launched daemon pid={daemon_pid}");
                let status = child
                    .wait()
                    .context("failed to wait for supervised daemon")?;
                let ran_for = child_started.elapsed();
                let next_delay = if ran_for.as_secs() >= SUPERVISOR_STABLE_RUN_SECONDS {
                    Duration::from_secs(SUPERVISOR_RESTART_INITIAL_SECONDS)
                } else {
                    restart_delay
                };
                if let Err(error) = mark_daemon_child_restarting(
                    &command.paths,
                    daemon_pid,
                    dry_run,
                    format!("daemon pid {daemon_pid} exited with {status}"),
                    next_delay,
                ) {
                    eprintln!("supervisor failed to persist restart status: {error:#}");
                }
                remove_pid_file_if_matches(&command.paths.pid_file, daemon_pid);
                eprintln!(
                    "supervisor restarting daemon after exit status={status} delay={}s",
                    next_delay.as_secs()
                );
                thread::sleep(next_delay);
                restart_delay = if ran_for.as_secs() >= SUPERVISOR_STABLE_RUN_SECONDS {
                    Duration::from_secs(SUPERVISOR_RESTART_INITIAL_SECONDS)
                } else {
                    doubled_restart_delay(restart_delay)
                };
            }
            Err(error) => {
                let next_delay = restart_delay;
                if let Err(status_error) = mark_daemon_child_restarting(
                    &command.paths,
                    0,
                    dry_run,
                    format!("supervisor failed to spawn daemon: {error:#}"),
                    next_delay,
                ) {
                    eprintln!(
                        "supervisor failed to persist spawn-failure status: {status_error:#}"
                    );
                }
                eprintln!(
                    "supervisor failed to spawn daemon: {error:#}; retrying in {}s",
                    next_delay.as_secs()
                );
                thread::sleep(next_delay);
                restart_delay = doubled_restart_delay(restart_delay);
            }
        }
    }
}

fn doubled_restart_delay(current: Duration) -> Duration {
    Duration::from_secs(current.as_secs().saturating_mul(2).clamp(
        SUPERVISOR_RESTART_INITIAL_SECONDS,
        SUPERVISOR_RESTART_MAX_SECONDS,
    ))
}

fn mark_daemon_child_restarting(
    paths: &RuntimePaths,
    daemon_pid: i32,
    dry_run: bool,
    summary: String,
    next_delay: Duration,
) -> Result<()> {
    let now = Utc::now();
    let resume_at = now + TimeDelta::seconds(next_delay.as_secs() as i64);
    let mut status = match load_json::<RuntimeStatus>(&paths.runtime_status_file) {
        Ok(Some(status)) => status,
        Ok(None) => RuntimeStatus::default(),
        Err(error) => {
            eprintln!(
                "supervisor replacing unreadable runtime status {}: {error:#}",
                paths.runtime_status_file.display()
            );
            RuntimeStatus::default()
        }
    };
    status.daemon_state = if dry_run {
        "dry-run-restarting".to_string()
    } else {
        "restarting".to_string()
    };
    status.dry_run = dry_run;
    status.last_notice = Some(format!(
        "{summary}; supervisor restarting in {}s",
        next_delay.as_secs()
    ));
    status.last_notice_at = Some(now);
    status.realtime.state = "unhealthy".to_string();
    status.realtime.last_state_changed_at = Some(now);
    status.realtime.latest_error_code = Some("supervisor-restart".to_string());
    status.realtime.latest_notice = status.last_notice.clone();
    status.realtime.latest_actionable_issue = Some(crate::state::ActionableIssueSnapshot {
        source: "supervisor".to_string(),
        severity: "error".to_string(),
        summary: summary.clone(),
        next_action:
            "wait for the supervisor restart and verify the next runtime_status.json heartbeat"
                .to_string(),
        detected_at: Some(now),
    });
    status.realtime.current_task = Some(crate::state::CurrentTaskSnapshot {
        task_kind: "supervisor-restart".to_string(),
        label: status.last_notice.clone().unwrap_or(summary),
        started_at: Some(now),
        expected_resume_at: Some(resume_at),
        ..crate::state::CurrentTaskSnapshot::default()
    });
    if daemon_pid > 0 {
        status.realtime.last_offline_started_at = Some(now);
    }
    save_json_atomic(&paths.runtime_status_file, &status)
}

fn remove_pid_file_if_matches(pid_file: &Path, pid: i32) {
    if read_positive_pid(pid_file).ok().flatten() == Some(pid) {
        let _ = fs::remove_file(pid_file);
    }
}

fn wait_for_server_start(
    child: &mut Child,
    paths: &RuntimePaths,
    log_path: &Path,
    supervisor_pid: i32,
    dry_run: bool,
    spawned_at: DateTime<Utc>,
    timeout: Duration,
) -> Result<ServerStartReceipt> {
    let deadline = Instant::now() + timeout;
    let mut last_reason = "waiting for daemon-owned startup evidence".to_string();
    loop {
        if let Some(status) = child
            .try_wait()
            .context("failed to inspect detached daemon")?
        {
            let recent_log = recent_log_failure(log_path)
                .map(|line| format!("; recent_log={line}"))
                .unwrap_or_default();
            bail!(
                "server-start supervisor exited before startup was verified: status={status}; last_evidence={last_reason}; log={}{}",
                log_path.display(),
                recent_log
            );
        }
        match probe_server_start(paths, log_path, supervisor_pid, dry_run, spawned_at) {
            ServerStartProbe::Ready(receipt) => return Ok(receipt),
            ServerStartProbe::Pending(reason) => last_reason = reason,
            ServerStartProbe::Failed(reason) => bail!(
                "server-start verification failed: {reason}; log={}",
                log_path.display()
            ),
        }
        if Instant::now() >= deadline {
            bail!(
                "server-start timed out after {}s before startup was verified: last_evidence={}; log={}",
                timeout.as_secs(),
                last_reason,
                log_path.display()
            );
        }
        thread::sleep(Duration::from_millis(250));
    }
}

fn probe_server_start(
    paths: &RuntimePaths,
    log_path: &Path,
    supervisor_pid: i32,
    dry_run: bool,
    spawned_at: DateTime<Utc>,
) -> ServerStartProbe {
    if !process_is_running(supervisor_pid) {
        return ServerStartProbe::Pending(format!(
            "supervisor PID {supervisor_pid} is not running yet"
        ));
    }
    let supervisor_pid_file = supervisor_pid_path(paths);
    match read_positive_pid(&supervisor_pid_file) {
        Ok(Some(pid)) if pid != supervisor_pid => {
            return ServerStartProbe::Failed(format!(
                "supervisor pid file {} contains {}, expected {}",
                supervisor_pid_file.display(),
                pid,
                supervisor_pid
            ));
        }
        Ok(_) => {}
        Err(error) => return ServerStartProbe::Pending(format!("{error:#}")),
    }

    let pid = match read_positive_pid(&paths.pid_file) {
        Ok(Some(pid)) => Some(pid),
        Ok(None) => None,
        Err(error) => return ServerStartProbe::Failed(format!("{error:#}")),
    };
    if let Some(pid) = pid
        && !process_is_running(pid)
    {
        return ServerStartProbe::Pending(format!("PID {pid} is not running yet"));
    }

    let status = match load_json::<RuntimeStatus>(&paths.runtime_status_file) {
        Ok(Some(status)) => status,
        Ok(None) => {
            return ServerStartProbe::Pending("runtime_status.json not written yet".to_string());
        }
        Err(error) => {
            return ServerStartProbe::Pending(format!(
                "runtime_status.json is not readable yet: {error:#}"
            ));
        }
    };
    if let Some(notice) = status.compatibility_notice.as_ref()
        && notice.blocking
    {
        return ServerStartProbe::Failed(format!(
            "blocking compatibility notice: {}",
            notice.summary
        ));
    }
    let Some(launch_path) = status.launch_path.as_ref() else {
        return ServerStartProbe::Pending("runtime status has no launch_path yet".to_string());
    };
    if launch_path
        .started_at
        .is_none_or(|started_at| started_at < spawned_at)
    {
        return ServerStartProbe::Pending("runtime launch_path is stale".to_string());
    }
    if launch_path.kind != SERVER_START_LAUNCH_KIND {
        return ServerStartProbe::Pending(format!(
            "runtime launch_path={} is not {} yet",
            launch_path.kind, SERVER_START_LAUNCH_KIND
        ));
    }
    let daemon_pid = launch_path.pid;
    if let Some(pid) = pid
        && pid != daemon_pid
    {
        return ServerStartProbe::Failed(format!(
            "pid file {} contains {}, expected runtime daemon {}",
            paths.pid_file.display(),
            pid,
            daemon_pid
        ));
    }
    if launch_path.pid_file != paths.pid_file.display().to_string() {
        return ServerStartProbe::Failed(format!(
            "runtime launch_path pid_file {} does not match {}",
            launch_path.pid_file,
            paths.pid_file.display()
        ));
    }
    if launch_path.runtime_status_file != paths.runtime_status_file.display().to_string() {
        return ServerStartProbe::Failed(format!(
            "runtime launch_path runtime_status_file {} does not match {}",
            launch_path.runtime_status_file,
            paths.runtime_status_file.display()
        ));
    }
    let expected_log_path = log_path.display().to_string();
    if launch_path.log_path.as_deref() != Some(expected_log_path.as_str()) {
        return ServerStartProbe::Failed(format!(
            "runtime launch_path log_path {:?} does not match {}",
            launch_path.log_path,
            log_path.display()
        ));
    }
    if status.dry_run != dry_run {
        return ServerStartProbe::Failed(format!(
            "runtime dry_run={} does not match requested dry_run={}",
            status.dry_run, dry_run
        ));
    }
    if !process_is_running(daemon_pid) {
        return ServerStartProbe::Pending(format!("daemon PID {daemon_pid} is not running yet"));
    }
    let expected_state = if dry_run {
        "dry-run-running"
    } else {
        "running"
    };
    if status.daemon_state != expected_state {
        return ServerStartProbe::Pending(format!(
            "daemon_state={} waiting for {}",
            status.daemon_state, expected_state
        ));
    }
    let Some(daemon_started_at) = status.realtime.daemon_started_at else {
        return ServerStartProbe::Pending(
            "runtime status has no daemon_started_at yet".to_string(),
        );
    };
    if daemon_started_at < spawned_at {
        return ServerStartProbe::Pending("runtime daemon_started_at is stale".to_string());
    }
    if status.realtime.live_lane.queue_capacity == 0
        || status.realtime.background_lane.queue_capacity == 0
    {
        return ServerStartProbe::Pending("runtime lanes are not initialized yet".to_string());
    }
    if status.realtime.current_task.is_none() {
        return ServerStartProbe::Pending(
            "runtime current task is not initialized yet".to_string(),
        );
    }
    if status
        .last_notice_at
        .is_none_or(|notice_at| notice_at < spawned_at)
    {
        return ServerStartProbe::Pending("runtime notice is stale".to_string());
    }
    if pid.is_none()
        && let Err(error) = save_text_atomic(&paths.pid_file, &daemon_pid.to_string())
    {
        return ServerStartProbe::Failed(format!(
            "runtime status is ready but pid file {} could not be repaired: {error:#}",
            paths.pid_file.display()
        ));
    }

    ServerStartProbe::Ready(ServerStartReceipt {
        mode: if dry_run { "dry-run" } else { "live" },
        pid: daemon_pid,
        supervisor_pid,
        config_path: paths.config_path.clone(),
        pid_file: paths.pid_file.clone(),
        runtime_status_file: paths.runtime_status_file.clone(),
        log_path: log_path.to_path_buf(),
    })
}

fn cleanup_failed_server_start_evidence(
    paths: &RuntimePaths,
    supervisor_pid: i32,
    dry_run: bool,
    spawned_at: DateTime<Utc>,
) -> Result<()> {
    remove_pid_file_if_matches(&supervisor_pid_path(paths), supervisor_pid);

    let Some(status) = load_json::<RuntimeStatus>(&paths.runtime_status_file)? else {
        return Ok(());
    };
    let Some(launch_path) = status.launch_path.clone() else {
        return Ok(());
    };
    if launch_path.kind != SERVER_START_LAUNCH_KIND
        || launch_path
            .started_at
            .is_none_or(|started_at| started_at < spawned_at)
    {
        return Ok(());
    }
    let daemon_pid = launch_path.pid;
    if daemon_pid > 0 {
        let _ = kill(Pid::from_raw(daemon_pid), Signal::SIGTERM);
        remove_pid_file_if_matches(&paths.pid_file, daemon_pid);
    }

    let failed_at = Utc::now();
    let mut failed_status = RuntimeStatus {
        daemon_state: "stopped".to_string(),
        dry_run,
        launch_path: Some(launch_path),
        last_notice: Some("server-start failed before daemon runtime was verified".to_string()),
        last_notice_at: Some(failed_at),
        ..RuntimeStatus::default()
    };
    failed_status.realtime.state = "stopped".to_string();
    failed_status.realtime.last_state_changed_at = Some(failed_at);
    save_json_atomic(&paths.runtime_status_file, &failed_status)
}

fn terminate_child(child: &mut Child, pid: i32) {
    let _ = kill(Pid::from_raw(pid), Signal::SIGTERM);
    let deadline = Instant::now() + Duration::from_secs(3);
    while Instant::now() < deadline {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn recent_log_failure(path: &Path) -> Option<String> {
    const TAIL_BYTES: u64 = 16 * 1024;
    const MAX_LINE_CHARS: usize = 500;

    let mut file = File::open(path).ok()?;
    let len = file.metadata().ok()?.len();
    file.seek(SeekFrom::Start(len.saturating_sub(TAIL_BYTES)))
        .ok()?;
    let mut raw = String::new();
    file.read_to_string(&mut raw).ok()?;
    raw.lines()
        .rev()
        .find(|line| {
            let lower = line.to_ascii_lowercase();
            line.contains("Error:") || line.contains("ERROR") || lower.contains("failed")
        })
        .map(|line| line.trim().chars().take(MAX_LINE_CHARS).collect())
}

fn format_server_start_receipt_lines(receipt: &ServerStartReceipt) -> Vec<String> {
    vec![
        format!("server-start.ok mode={} pid={}", receipt.mode, receipt.pid),
        format!("supervisor_pid={}", receipt.supervisor_pid),
        format!("config={}", receipt.config_path.display()),
        format!("pid_file={}", receipt.pid_file.display()),
        format!("runtime_status={}", receipt.runtime_status_file.display()),
        format!("log={}", receipt.log_path.display()),
        format!("launch_path={SERVER_START_LAUNCH_KIND}"),
    ]
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
    use crate::state::{
        CommandReportSurface, CoverageSummary, LaunchPathSnapshot, UnresolvedExposureItem,
        load_json, save_text_atomic,
    };

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

    fn server_start_runtime_status(
        paths: &RuntimePaths,
        pid: i32,
        dry_run: bool,
        started_at: DateTime<Utc>,
    ) -> RuntimeStatus {
        RuntimeStatus {
            daemon_state: if dry_run {
                "dry-run-running".to_string()
            } else {
                "running".to_string()
            },
            dry_run,
            launch_path: Some(LaunchPathSnapshot {
                kind: SERVER_START_LAUNCH_KIND.to_string(),
                pid,
                config_path: paths.config_path.display().to_string(),
                pid_file: paths.pid_file.display().to_string(),
                runtime_status_file: paths.runtime_status_file.display().to_string(),
                log_path: Some(paths.state_dir.join("daemon.log").display().to_string()),
                started_at: Some(started_at),
                ..LaunchPathSnapshot::default()
            }),
            last_notice: Some("daemon runtime started".to_string()),
            last_notice_at: Some(started_at),
            realtime: crate::state::RealtimeRuntimeStatus {
                daemon_started_at: Some(started_at),
                live_lane: crate::state::ExecutionLaneSnapshot {
                    queue_capacity: 100,
                    concurrency_limit: 1,
                    ..crate::state::ExecutionLaneSnapshot::default()
                },
                background_lane: crate::state::ExecutionLaneSnapshot {
                    queue_capacity: 100,
                    concurrency_limit: 1,
                    ..crate::state::ExecutionLaneSnapshot::default()
                },
                current_task: Some(crate::state::CurrentTaskSnapshot {
                    task_kind: "idle".to_string(),
                    label: "waiting for watched-page edits".to_string(),
                    started_at: Some(started_at),
                    ..crate::state::CurrentTaskSnapshot::default()
                }),
                ..crate::state::RealtimeRuntimeStatus::default()
            },
            ..RuntimeStatus::default()
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
    fn server_start_resolves_relative_log_path_from_config_dir() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);

        let log_path = resolve_server_start_log_path(
            &paths.config_path,
            &paths,
            Some(PathBuf::from("./state/server.log")),
        );

        assert_eq!(log_path, temp.path().join("./state/server.log"));
    }

    #[test]
    fn server_start_receipt_lines_are_non_sensitive_and_complete() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let receipt = ServerStartReceipt {
            mode: "live",
            pid: 42,
            supervisor_pid: 41,
            config_path: paths.config_path.clone(),
            pid_file: paths.pid_file.clone(),
            runtime_status_file: paths.runtime_status_file.clone(),
            log_path: paths.state_dir.join("daemon.log"),
        };

        let lines = format_server_start_receipt_lines(&receipt);

        assert_eq!(lines[0], "server-start.ok mode=live pid=42");
        assert!(lines.contains(&"supervisor_pid=41".to_string()));
        assert!(lines.iter().any(|line| line.starts_with("config=")));
        assert!(lines.iter().any(|line| line.starts_with("pid_file=")));
        assert!(lines.iter().any(|line| line.starts_with("runtime_status=")));
        assert!(lines.iter().any(|line| line.starts_with("log=")));
        assert_eq!(
            lines.last().map(String::as_str),
            Some("launch_path=server-start")
        );
        assert!(!lines.join("\n").contains("password"));
        assert!(!lines.join("\n").contains("token"));
    }

    #[test]
    fn server_start_recent_log_failure_picks_latest_actionable_error() {
        let temp = tempfile::tempdir().unwrap();
        let log_path = temp.path().join("daemon.log");
        std::fs::write(
            &log_path,
            "INFO old startup\nError: stale failure\nINFO retrying\nError: non-json-response: Failed to decode JSON response\n",
        )
        .unwrap();

        let recent = recent_log_failure(&log_path).unwrap();

        assert_eq!(
            recent,
            "Error: non-json-response: Failed to decode JSON response"
        );
    }

    #[test]
    fn server_start_rejects_duplicate_live_pid() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let current_exe = std::env::current_exe().unwrap();
        save_text_atomic(&paths.pid_file, &std::process::id().to_string()).unwrap();

        let error = reject_or_clear_existing_pid(&paths, &current_exe).unwrap_err();

        assert!(error.to_string().contains("refused duplicate daemon"));
        assert!(paths.pid_file.exists());
    }

    #[test]
    fn server_start_clears_stale_pid_marker() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let current_exe = std::env::current_exe().unwrap();
        save_text_atomic(&paths.pid_file, "9999999").unwrap();

        reject_or_clear_existing_pid(&paths, &current_exe).unwrap();

        assert!(!paths.pid_file.exists());
    }

    #[test]
    fn server_start_clears_pid_for_unrelated_live_process() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let current_exe = std::env::current_exe().unwrap();
        let mut child = std::process::Command::new("sleep")
            .arg("60")
            .spawn()
            .unwrap();
        save_text_atomic(&paths.pid_file, &child.id().to_string()).unwrap();

        reject_or_clear_existing_pid(&paths, &current_exe).unwrap();

        assert!(!paths.pid_file.exists());
        let _ = child.kill();
        let _ = child.wait();
    }

    #[test]
    fn server_start_probe_accepts_fresh_matching_runtime_status() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let pid = std::process::id() as i32;
        let spawned_at = Utc::now() - TimeDelta::seconds(1);
        let started_at = Utc::now();
        save_text_atomic(&paths.pid_file, &pid.to_string()).unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &server_start_runtime_status(&paths, pid, false, started_at),
        )
        .unwrap();

        match probe_server_start(
            &paths,
            &paths.state_dir.join("daemon.log"),
            pid,
            false,
            spawned_at,
        ) {
            ServerStartProbe::Ready(receipt) => {
                assert_eq!(receipt.pid, pid);
                assert_eq!(receipt.mode, "live");
            }
            ServerStartProbe::Pending(reason) | ServerStartProbe::Failed(reason) => {
                panic!("expected ready probe, got {reason}")
            }
        }
    }

    #[test]
    fn server_start_probe_keeps_startup_only_runtime_status_pending() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let pid = std::process::id() as i32;
        let spawned_at = Utc::now() - TimeDelta::seconds(1);
        save_text_atomic(&paths.pid_file, &pid.to_string()).unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &RuntimeStatus {
                daemon_state: "starting".to_string(),
                dry_run: false,
                launch_path: Some(LaunchPathSnapshot {
                    kind: SERVER_START_LAUNCH_KIND.to_string(),
                    pid,
                    config_path: paths.config_path.display().to_string(),
                    pid_file: paths.pid_file.display().to_string(),
                    runtime_status_file: paths.runtime_status_file.display().to_string(),
                    log_path: Some(paths.state_dir.join("daemon.log").display().to_string()),
                    started_at: Some(Utc::now()),
                    ..LaunchPathSnapshot::default()
                }),
                ..RuntimeStatus::default()
            },
        )
        .unwrap();

        match probe_server_start(
            &paths,
            &paths.state_dir.join("daemon.log"),
            pid,
            false,
            spawned_at,
        ) {
            ServerStartProbe::Pending(reason) => {
                assert!(reason.contains("waiting for running"));
            }
            ServerStartProbe::Ready(_) | ServerStartProbe::Failed(_) => {
                panic!("expected startup-only status to remain pending")
            }
        }
    }

    #[test]
    fn server_start_probe_repairs_missing_pid_from_fresh_runtime_status() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let pid = std::process::id() as i32;
        let spawned_at = Utc::now() - TimeDelta::seconds(1);
        let started_at = Utc::now();
        save_json_atomic(
            &paths.runtime_status_file,
            &server_start_runtime_status(&paths, pid, false, started_at),
        )
        .unwrap();

        match probe_server_start(
            &paths,
            &paths.state_dir.join("daemon.log"),
            pid,
            false,
            spawned_at,
        ) {
            ServerStartProbe::Ready(receipt) => {
                let expected_pid = pid.to_string();
                assert_eq!(receipt.pid, pid);
                assert_eq!(receipt.mode, "live");
                assert_eq!(
                    load_text(&paths.pid_file).unwrap().as_deref(),
                    Some(expected_pid.as_str())
                );
            }
            ServerStartProbe::Pending(reason) | ServerStartProbe::Failed(reason) => {
                panic!("expected ready probe, got {reason}")
            }
        }
    }

    #[test]
    fn server_start_rejects_zero_status_timeout_before_preflight() {
        let temp = tempfile::tempdir().unwrap();
        let config_path = temp.path().join("config.toml");

        let error = run_server_start(config_path, false, 0, None, false).unwrap_err();

        assert!(
            error
                .to_string()
                .contains("status-timeout-seconds greater than zero")
        );
    }

    #[test]
    fn server_start_cleanup_removes_matching_startup_pid_and_marks_status_stopped() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let child_pid = 42;
        let started_at = Utc::now();
        save_text_atomic(&paths.pid_file, &child_pid.to_string()).unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &RuntimeStatus {
                daemon_state: "starting".to_string(),
                dry_run: false,
                launch_path: Some(LaunchPathSnapshot {
                    kind: SERVER_START_LAUNCH_KIND.to_string(),
                    pid: child_pid,
                    config_path: paths.config_path.display().to_string(),
                    pid_file: paths.pid_file.display().to_string(),
                    runtime_status_file: paths.runtime_status_file.display().to_string(),
                    log_path: Some(paths.state_dir.join("daemon.log").display().to_string()),
                    started_at: Some(started_at),
                    ..LaunchPathSnapshot::default()
                }),
                ..RuntimeStatus::default()
            },
        )
        .unwrap();

        cleanup_failed_server_start_evidence(
            &paths,
            child_pid - 1,
            false,
            started_at - TimeDelta::seconds(1),
        )
        .unwrap();

        assert!(!paths.pid_file.exists());
        let status = load_json::<RuntimeStatus>(&paths.runtime_status_file)
            .unwrap()
            .unwrap();
        assert_eq!(status.daemon_state, "stopped");
        assert_eq!(status.realtime.state, "stopped");
        assert_eq!(
            status.last_notice.as_deref(),
            Some("server-start failed before daemon runtime was verified")
        );
    }

    #[test]
    fn server_start_cleanup_leaves_mismatched_pid_and_status_alone() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let child_pid = 42;
        let other_pid = 43;
        let started_at = Utc::now();
        save_text_atomic(&paths.pid_file, &other_pid.to_string()).unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &server_start_runtime_status(&paths, other_pid, false, started_at),
        )
        .unwrap();

        cleanup_failed_server_start_evidence(
            &paths,
            child_pid,
            false,
            started_at + TimeDelta::seconds(1),
        )
        .unwrap();

        assert_eq!(load_text(&paths.pid_file).unwrap().as_deref(), Some("43"));
        let status = load_json::<RuntimeStatus>(&paths.runtime_status_file)
            .unwrap()
            .unwrap();
        assert_eq!(status.daemon_state, "running");
        assert_eq!(
            status.launch_path.as_ref().map(|launch| launch.pid),
            Some(other_pid)
        );
    }

    #[test]
    fn server_start_probe_rejects_stale_runtime_launch_path() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let pid = std::process::id() as i32;
        let spawned_at = Utc::now();
        save_text_atomic(&paths.pid_file, &pid.to_string()).unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &RuntimeStatus {
                daemon_state: "running".to_string(),
                dry_run: false,
                launch_path: Some(LaunchPathSnapshot {
                    kind: SERVER_START_LAUNCH_KIND.to_string(),
                    pid,
                    config_path: paths.config_path.display().to_string(),
                    pid_file: paths.pid_file.display().to_string(),
                    runtime_status_file: paths.runtime_status_file.display().to_string(),
                    log_path: Some(paths.state_dir.join("daemon.log").display().to_string()),
                    started_at: Some(spawned_at - TimeDelta::seconds(1)),
                    ..LaunchPathSnapshot::default()
                }),
                ..RuntimeStatus::default()
            },
        )
        .unwrap();

        match probe_server_start(
            &paths,
            &paths.state_dir.join("daemon.log"),
            pid,
            false,
            spawned_at,
        ) {
            ServerStartProbe::Pending(reason) => {
                assert!(reason.contains("runtime launch_path is stale"));
            }
            ServerStartProbe::Ready(_) | ServerStartProbe::Failed(_) => {
                panic!("expected stale launch path to remain pending")
            }
        }
    }

    #[test]
    fn server_start_probe_keeps_stale_previous_launch_mismatch_pending() {
        let temp = tempfile::tempdir().unwrap();
        let paths = test_runtime_paths(&temp);
        let pid = std::process::id() as i32;
        let spawned_at = Utc::now();
        save_text_atomic(&paths.pid_file, &pid.to_string()).unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &RuntimeStatus {
                daemon_state: "running".to_string(),
                dry_run: false,
                launch_path: Some(LaunchPathSnapshot {
                    kind: SERVER_START_LAUNCH_KIND.to_string(),
                    pid: pid + 1,
                    config_path: paths.config_path.display().to_string(),
                    pid_file: paths.pid_file.display().to_string(),
                    runtime_status_file: paths.runtime_status_file.display().to_string(),
                    log_path: Some(paths.state_dir.join("daemon.log").display().to_string()),
                    started_at: Some(spawned_at - TimeDelta::seconds(1)),
                    ..LaunchPathSnapshot::default()
                }),
                ..RuntimeStatus::default()
            },
        )
        .unwrap();

        match probe_server_start(
            &paths,
            &paths.state_dir.join("daemon.log"),
            pid,
            false,
            spawned_at,
        ) {
            ServerStartProbe::Pending(reason) => {
                assert!(reason.contains("runtime launch_path is stale"));
            }
            ServerStartProbe::Ready(_) | ServerStartProbe::Failed(_) => {
                panic!("expected stale previous launch mismatch to remain pending")
            }
        }
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
                revision_url: Some("https://example.invalid/wiki/Special:Diff/77".to_string()),
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
                revision_url: Some("https://example.invalid/wiki/Special:Diff/42".to_string()),
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
