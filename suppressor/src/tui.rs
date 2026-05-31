use std::collections::VecDeque;
use std::io;
use std::path::PathBuf;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use crossterm::execute;
use crossterm::terminal::{
    EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode,
};
use nix::sys::signal::{Signal, kill};
use nix::unistd::Pid;
use ratatui::Terminal;
use ratatui::backend::CrosstermBackend;
use ratatui::layout::Rect;
use tokio::process::Child;
use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender, unbounded_channel};

use crate::config::{AppConfig, RuntimePaths};
use crate::signals;
use crate::tui_process::{build_child_command, build_child_command_owned, spawn_pipe_reader};
use crate::tui_status::{StatusSnapshot, collect_status};
use crate::tui_view::{draw_ui, log_view_capacity, log_view_content_width, log_viewport};

const MAX_LOG_LINES: usize = 500;
const STATUS_REFRESH_INTERVAL: Duration = Duration::from_secs(2);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum FocusPane {
    Actions,
    Output,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum UiAction {
    StartDaemon,
    StartDryRun,
    StopDaemon,
    CheckAuth,
    PrintConfig,
    ReloadCache,
    EmergencyCatchup,
    CoverageReport,
    SweepNow,
    RefreshStatus,
    Quit,
}

impl UiAction {
    pub(crate) fn all() -> &'static [UiAction] {
        &[
            UiAction::StartDaemon,
            UiAction::StartDryRun,
            UiAction::StopDaemon,
            UiAction::CheckAuth,
            UiAction::PrintConfig,
            UiAction::ReloadCache,
            UiAction::EmergencyCatchup,
            UiAction::CoverageReport,
            UiAction::SweepNow,
            UiAction::RefreshStatus,
            UiAction::Quit,
        ]
    }

    pub(crate) fn label(self) -> &'static str {
        match self {
            UiAction::StartDaemon => "Start daemon",
            UiAction::StartDryRun => "Start dry-run",
            UiAction::StopDaemon => "Stop daemon",
            UiAction::CheckAuth => "Check auth",
            UiAction::PrintConfig => "Print config",
            UiAction::ReloadCache => "Reload watched pages",
            UiAction::EmergencyCatchup => "Emergency catch-up",
            UiAction::CoverageReport => "Coverage: Last 24 hours",
            UiAction::SweepNow => "Run bounded recovery",
            UiAction::RefreshStatus => "Reread local status",
            UiAction::Quit => "Quit",
        }
    }

    pub(crate) fn detail(self) -> &'static str {
        match self {
            UiAction::StartDaemon => "Runs the real daemon under this supervisor client.",
            UiAction::StartDryRun => "Runs the daemon in dry-run mode with live logs.",
            UiAction::StopDaemon => "Stops the managed daemon or sends SIGTERM to a running PID.",
            UiAction::CheckAuth => "Checks login and rights without starting the daemon.",
            UiAction::PrintConfig => "Shows the effective config with secrets redacted.",
            UiAction::ReloadCache => {
                "Reloads the watched-page cache. The status panel will show the source refresh result once the daemon finishes."
            }
            UiAction::EmergencyCatchup => {
                "Checks from the last successful hide when available and hides unresolved watched-page edits."
            }
            UiAction::CoverageReport => {
                "Reports the rolling Last 24 hours window without hiding so unresolved exposure is visible."
            }
            UiAction::SweepNow => {
                "Asks the running daemon to rescan its bounded recovery window and retry transient pending hides."
            }
            UiAction::RefreshStatus => {
                "Rereads daemon-owned status and command-report files. It does not repair protection."
            }
            UiAction::Quit => "Closes the control center. Managed sessions are stopped on exit.",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) enum ManagedMode {
    Daemon,
    DryRun,
}

impl ManagedMode {
    pub(crate) fn command_name(self) -> &'static str {
        match self {
            ManagedMode::Daemon => "run",
            ManagedMode::DryRun => "dry-run",
        }
    }

    pub(crate) fn label(self) -> &'static str {
        match self {
            ManagedMode::Daemon => "daemon",
            ManagedMode::DryRun => "dry-run",
        }
    }
}

pub(crate) struct ManagedSession {
    child: Child,
    mode: ManagedMode,
    started_at: Instant,
}

pub(crate) struct ControlApp {
    pub(crate) paths: RuntimePaths,
    current_exe: PathBuf,
    verbose: bool,
    pub(crate) focus: FocusPane,
    pub(crate) selected: usize,
    log_top: usize,
    pub(crate) follow_logs: bool,
    pub(crate) logs: VecDeque<String>,
    pub(crate) status: StatusSnapshot,
    managed: Option<ManagedSession>,
    log_tx: UnboundedSender<String>,
    log_rx: UnboundedReceiver<String>,
    last_refresh: Instant,
    should_quit: bool,
}

impl ControlApp {
    fn new(paths: RuntimePaths, current_exe: PathBuf, verbose: bool) -> Self {
        let (log_tx, log_rx) = unbounded_channel();
        let mut app = Self {
            paths,
            current_exe,
            verbose,
            focus: FocusPane::Actions,
            selected: 0,
            log_top: 0,
            follow_logs: true,
            logs: VecDeque::new(),
            status: StatusSnapshot::default(),
            managed: None,
            log_tx,
            log_rx,
            last_refresh: Instant::now()
                .checked_sub(STATUS_REFRESH_INTERVAL)
                .unwrap_or_else(Instant::now),
            should_quit: false,
        };
        app.push_control_log("Control center started. Use arrows and Enter to run an action.");
        app.refresh_status();
        app
    }

    pub(crate) fn selected_action(&self) -> UiAction {
        UiAction::all()[self.selected]
    }

    fn next_action(&mut self) {
        self.selected = (self.selected + 1) % UiAction::all().len();
    }

    fn previous_action(&mut self) {
        self.selected = if self.selected == 0 {
            UiAction::all().len() - 1
        } else {
            self.selected - 1
        };
    }

    fn wrapped_log_rows(line: &str, width: usize) -> usize {
        line.chars().count().max(1).div_ceil(width.max(1))
    }

    fn total_log_rows(&self, width: usize) -> usize {
        self.logs
            .iter()
            .map(|line| Self::wrapped_log_rows(line, width))
            .sum()
    }

    fn focus_actions(&mut self) {
        self.focus = FocusPane::Actions;
    }

    fn focus_output(&mut self) {
        self.focus = FocusPane::Output;
    }

    fn toggle_focus(&mut self) {
        self.focus = match self.focus {
            FocusPane::Actions => FocusPane::Output,
            FocusPane::Output => FocusPane::Actions,
        };
    }

    fn log_max_top(&self, visible_lines: usize, line_width: usize) -> usize {
        self.total_log_rows(line_width)
            .saturating_sub(visible_lines.max(1))
    }

    pub(crate) fn current_log_top(&self, visible_lines: usize, line_width: usize) -> usize {
        if self.follow_logs {
            self.log_max_top(visible_lines, line_width)
        } else {
            self.log_top
                .min(self.log_max_top(visible_lines, line_width))
        }
    }

    fn scroll_logs_up(&mut self, visible_lines: usize, line_width: usize, amount: usize) {
        if self.logs.is_empty() {
            return;
        }
        self.follow_logs = false;
        self.log_top = self
            .current_log_top(visible_lines, line_width)
            .saturating_sub(amount.max(1));
    }

    fn scroll_logs_down(&mut self, visible_lines: usize, line_width: usize, amount: usize) {
        if self.logs.is_empty() {
            return;
        }
        let max_top = self.log_max_top(visible_lines, line_width);
        let next = self
            .current_log_top(visible_lines, line_width)
            .saturating_add(amount.max(1))
            .min(max_top);
        self.log_top = next;
        self.follow_logs = next >= max_top;
    }

    fn scroll_logs_oldest(&mut self) {
        self.follow_logs = false;
        self.log_top = 0;
    }

    fn scroll_logs_latest(&mut self, visible_lines: usize, line_width: usize) {
        self.log_top = self.log_max_top(visible_lines, line_width);
        self.follow_logs = true;
    }

    fn push_raw_log<S: Into<String>>(&mut self, line: S) {
        self.logs.push_back(line.into());
        let mut dropped = 0usize;
        while self.logs.len() > MAX_LOG_LINES {
            let _ = self.logs.pop_front();
            dropped += 1;
        }
        if !self.follow_logs && dropped > 0 {
            self.log_top = self.log_top.saturating_sub(dropped);
        }
    }

    fn push_control_log<S: Into<String>>(&mut self, line: S) {
        self.push_raw_log(format!("[control] {}", line.into()));
    }

    fn drain_logs(&mut self) {
        while let Ok(line) = self.log_rx.try_recv() {
            self.push_raw_log(line);
        }
    }

    fn refresh_status(&mut self) {
        self.status = collect_status(
            &self.paths,
            self.managed.as_ref().map(|session| session.mode.label()),
        );
        self.last_refresh = Instant::now();
    }

    fn needs_refresh(&self) -> bool {
        self.last_refresh.elapsed() >= STATUS_REFRESH_INTERVAL
    }

    fn spawn_managed_session(&mut self, mode: ManagedMode) {
        if self.managed.is_some() {
            self.push_control_log(
                "A managed session is already running. Stop it before starting another.",
            );
            return;
        }
        match build_child_command(
            &self.current_exe,
            &self.paths,
            self.verbose,
            &[mode.command_name()],
        ) {
            Ok(mut command) => {
                command.kill_on_drop(true);
                match command.spawn() {
                    Ok(mut child) => {
                        let pid = child.id();
                        if let Some(stdout) = child.stdout.take() {
                            spawn_pipe_reader(
                                stdout,
                                format!("{}:out", mode.label()),
                                self.log_tx.clone(),
                            );
                        }
                        if let Some(stderr) = child.stderr.take() {
                            spawn_pipe_reader(
                                stderr,
                                format!("{}:err", mode.label()),
                                self.log_tx.clone(),
                            );
                        }
                        self.push_control_log(format!(
                            "Started managed {} session{}.",
                            mode.label(),
                            pid.map(|value| format!(" with child PID {}", value))
                                .unwrap_or_default()
                        ));
                        self.managed = Some(ManagedSession {
                            child,
                            mode,
                            started_at: Instant::now(),
                        });
                        self.refresh_status();
                    }
                    Err(error) => {
                        self.push_control_log(format!(
                            "Failed to start {} session: {error:#}",
                            mode.label()
                        ));
                    }
                }
            }
            Err(error) => {
                self.push_control_log(format!(
                    "Failed to prepare {} session: {error:#}",
                    mode.label()
                ));
            }
        }
    }

    fn spawn_background_command(&mut self, label: &'static str, args: Vec<String>) {
        let current_exe = self.current_exe.clone();
        let paths = self.paths.clone();
        let verbose = self.verbose;
        let tx = self.log_tx.clone();
        tokio::spawn(async move {
            let mut command = match build_child_command_owned(&current_exe, &paths, verbose, args) {
                Ok(command) => command,
                Err(error) => {
                    let _ = tx.send(format!("[{label}] failed to prepare command: {error:#}"));
                    return;
                }
            };
            let _ = tx.send(format!("[{label}] starting command..."));
            let mut child = match command.spawn() {
                Ok(child) => child,
                Err(error) => {
                    let _ = tx.send(format!("[{label}] failed to start command: {error:#}"));
                    return;
                }
            };
            if let Some(stdout) = child.stdout.take() {
                spawn_pipe_reader(stdout, format!("{label}:out"), tx.clone());
            }
            if let Some(stderr) = child.stderr.take() {
                spawn_pipe_reader(stderr, format!("{label}:err"), tx.clone());
            }
            match child.wait().await {
                Ok(status) if status.success() => {
                    let _ = tx.send(format!("[{label}] command finished successfully."));
                }
                Ok(status) => {
                    let _ = tx.send(format!("[{label}] command failed with status {status}."));
                }
                Err(error) => {
                    let _ = tx.send(format!(
                        "[{label}] failed while waiting for command: {error:#}"
                    ));
                }
            }
        });
    }

    fn stop_daemon(&mut self) {
        if let Some(mut managed) = self.managed.take() {
            if let Err(error) = managed.child.start_kill() {
                self.push_control_log(format!(
                    "Failed to stop managed {}: {error:#}",
                    managed.mode.label()
                ));
                self.managed = Some(managed);
                return;
            }
            self.push_control_log(format!(
                "Sent stop request to managed {} session.",
                managed.mode.label()
            ));
            self.refresh_status();
            return;
        }

        if let Some(pid) = self.status.daemon_pid {
            if !self.status.daemon_running {
                self.push_control_log(format!(
                    "PID file exists at {} but process {} is not running. Start the daemon again to refresh the state.",
                    self.status.pid_file.display(),
                    pid
                ));
                return;
            }
            match kill(Pid::from_raw(pid), Signal::SIGTERM) {
                Ok(()) => {
                    self.push_control_log(format!("Sent SIGTERM to daemon PID {}.", pid));
                    self.refresh_status();
                }
                Err(error) => {
                    self.push_control_log(format!("Failed to stop daemon PID {}: {error:#}", pid));
                }
            }
        } else {
            self.push_control_log(
                "No running daemon was found. Start one with the Start daemon action.",
            );
        }
    }

    fn post_reload_signal(&mut self) {
        match signals::send_reload(&self.paths.pid_file) {
            Ok(()) => {
                self.push_control_log("Requested watched-page reload from the running daemon.")
            }
            Err(error) => {
                self.push_control_log(format!("Failed to request watched-page reload: {error:#}"))
            }
        }
        self.refresh_status();
    }

    fn post_sweep_signal(&mut self) {
        match signals::send_manual_sweep(&self.paths.pid_file) {
            Ok(()) => {
                self.push_control_log("Requested bounded manual recovery from the running daemon.")
            }
            Err(error) => self.push_control_log(format!(
                "Failed to request bounded manual recovery: {error:#}"
            )),
        }
        self.refresh_status();
    }

    fn poll_managed_session(&mut self) {
        if let Some(managed) = self.managed.as_mut() {
            match managed.child.try_wait() {
                Ok(Some(status)) => {
                    let label = managed.mode.label();
                    let elapsed = managed.started_at.elapsed().as_secs();
                    self.push_control_log(format!(
                        "Managed {} session exited with status {} after {}s.",
                        label, status, elapsed
                    ));
                    self.managed = None;
                    self.refresh_status();
                }
                Ok(None) => {}
                Err(error) => {
                    let label = managed.mode.label();
                    self.push_control_log(format!(
                        "Failed to poll managed {} session: {error:#}",
                        label
                    ));
                    self.managed = None;
                    self.refresh_status();
                }
            }
        }
    }
}

fn background_command_for_action(action: UiAction) -> Option<(&'static str, Vec<String>)> {
    match action {
        UiAction::CheckAuth => Some(("check-auth", vec!["check-auth".to_string()])),
        UiAction::PrintConfig => Some((
            "print-effective-config",
            vec!["print-effective-config".to_string()],
        )),
        UiAction::EmergencyCatchup => {
            Some(("emergency-catchup", vec!["emergency-catchup".to_string()]))
        }
        UiAction::CoverageReport => Some((
            "coverage-last-24h",
            vec!["coverage-last-24h".to_string(), "--report-only".to_string()],
        )),
        _ => None,
    }
}

impl ControlApp {
    fn execute_selected_action(&mut self) {
        match self.selected_action() {
            UiAction::StartDaemon => self.spawn_managed_session(ManagedMode::Daemon),
            UiAction::StartDryRun => self.spawn_managed_session(ManagedMode::DryRun),
            UiAction::StopDaemon => self.stop_daemon(),
            UiAction::CheckAuth | UiAction::PrintConfig => {
                if let Some((label, args)) = background_command_for_action(self.selected_action()) {
                    self.spawn_background_command(label, args);
                }
            }
            UiAction::ReloadCache => self.post_reload_signal(),
            UiAction::EmergencyCatchup | UiAction::CoverageReport => {
                if let Some((label, args)) = background_command_for_action(self.selected_action()) {
                    self.spawn_background_command(label, args);
                }
            }
            UiAction::SweepNow => self.post_sweep_signal(),
            UiAction::RefreshStatus => {
                self.refresh_status();
                self.push_control_log("Reread local status files.");
            }
            UiAction::Quit => self.should_quit = true,
        }
    }
}

pub async fn run(config_path: PathBuf, verbose: bool) -> Result<()> {
    let config = AppConfig::load(&config_path)?;
    let paths = RuntimePaths::resolve(&config_path, &config);
    let current_exe = std::env::current_exe().context("Failed to locate current executable")?;

    enable_raw_mode().context("Failed to enable terminal raw mode")?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen).context("Failed to enter alternate screen")?;
    let _guard = TerminalCleanup;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend).context("Failed to initialize terminal backend")?;

    let mut app = ControlApp::new(paths, current_exe, verbose);

    while !app.should_quit {
        app.drain_logs();
        app.poll_managed_session();
        if app.needs_refresh() {
            app.refresh_status();
        }

        terminal
            .draw(|frame| draw_ui(frame, &app))
            .context("Failed to draw control screen")?;

        if event::poll(Duration::from_millis(100)).context("Failed to poll terminal events")?
            && let Event::Key(key) = event::read().context("Failed to read terminal event")?
        {
            if key.kind != KeyEventKind::Press {
                continue;
            }
            let size = terminal.size()?;
            let log_area = log_viewport(Rect::new(0, 0, size.width, size.height));
            let visible_logs = log_view_capacity(log_area);
            let log_width = log_view_content_width(log_area);
            match key.code {
                KeyCode::Tab => app.toggle_focus(),
                KeyCode::Left => app.focus_actions(),
                KeyCode::Right => app.focus_output(),
                KeyCode::Up => match app.focus {
                    FocusPane::Actions => app.previous_action(),
                    FocusPane::Output => app.scroll_logs_up(visible_logs, log_width, 1),
                },
                KeyCode::Down => match app.focus {
                    FocusPane::Actions => app.next_action(),
                    FocusPane::Output => app.scroll_logs_down(visible_logs, log_width, 1),
                },
                KeyCode::PageUp => app.scroll_logs_up(visible_logs, log_width, visible_logs.max(5)),
                KeyCode::PageDown => {
                    app.scroll_logs_down(visible_logs, log_width, visible_logs.max(5))
                }
                KeyCode::Home => app.scroll_logs_oldest(),
                KeyCode::End => app.scroll_logs_latest(visible_logs, log_width),
                KeyCode::Enter => app.execute_selected_action(),
                KeyCode::Char('q') => app.should_quit = true,
                KeyCode::Char('r') => {
                    app.refresh_status();
                    app.push_control_log("Reread local status files.");
                }
                _ => {}
            }
        }
    }

    if let Some(mut managed) = app.managed.take() {
        let _ = managed.child.start_kill();
    }
    Ok(())
}

struct TerminalCleanup;

impl Drop for TerminalCleanup {
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let mut stdout = io::stdout();
        let _ = execute!(stdout, LeaveAlternateScreen);
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;
    use crate::config::RuntimePaths;

    fn test_paths() -> RuntimePaths {
        RuntimePaths {
            config_path: PathBuf::from("/tmp/config.toml"),
            state_dir: PathBuf::from("/tmp/state"),
            env_file: PathBuf::from("/tmp/.env"),
            cache_file: PathBuf::from("/tmp/state/cache.json"),
            last_event_id_file: PathBuf::from("/tmp/state/last_event_id"),
            processed_revids_file: PathBuf::from("/tmp/state/processed.json"),
            nightly_sweep_progress_file: PathBuf::from("/tmp/state/progress.json"),
            runtime_status_file: PathBuf::from("/tmp/state/runtime.json"),
            pid_file: PathBuf::from("/tmp/state/pid"),
        }
    }

    #[test]
    fn coverage_report_uses_its_own_command() {
        let (label, args) = background_command_for_action(UiAction::CoverageReport).unwrap();

        assert_eq!(label, "coverage-last-24h");
        assert_eq!(
            args,
            vec!["coverage-last-24h".to_string(), "--report-only".to_string()]
        );
    }

    #[test]
    fn emergency_catchup_uses_its_own_command() {
        let (label, args) = background_command_for_action(UiAction::EmergencyCatchup).unwrap();

        assert_eq!(label, "emergency-catchup");
        assert_eq!(args, vec!["emergency-catchup".to_string()]);
    }

    #[test]
    fn control_logs_are_source_labeled() {
        let mut app = ControlApp::new(test_paths(), PathBuf::from("/tmp/suppressor"), false);

        app.push_control_log("Status refreshed.");

        assert_eq!(
            app.logs.back().map(String::as_str),
            Some("[control] Status refreshed.")
        );
    }

    #[test]
    fn latest_mode_tracks_newest_raw_lines() {
        let mut app = ControlApp::new(test_paths(), PathBuf::from("/tmp/suppressor"), false);
        app.logs.clear();

        for index in 0..6 {
            app.push_raw_log(format!("line-{index} {}", "x".repeat(120)));
        }

        assert!(app.follow_logs);
        assert_eq!(app.current_log_top(3, 200), 3);
    }

    #[test]
    fn latest_mode_tracks_newest_wrapped_rows() {
        let mut app = ControlApp::new(test_paths(), PathBuf::from("/tmp/suppressor"), false);
        app.logs.clear();

        for index in 0..3 {
            app.push_raw_log(format!("line-{index} {}", "x".repeat(40)));
        }

        assert!(app.follow_logs);
        assert_eq!(app.current_log_top(3, 10), 12);
    }
}
