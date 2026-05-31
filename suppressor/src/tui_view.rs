use chrono::Utc;
use ratatui::Frame;
use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Wrap};

use crate::config::RuntimePaths;
use crate::state::{CommandReportSurface, CompatibilityNotice, CoverageSummary, WarningSummary};
use crate::tui::{ControlApp, FocusPane, UiAction};
use crate::tui_status::StatusSnapshot;

pub(crate) fn draw_ui(frame: &mut Frame<'_>, app: &ControlApp) {
    let area = frame.area();
    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(12),
            Constraint::Length(10),
            Constraint::Length(2),
        ])
        .split(area);

    let top = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(38), Constraint::Percentage(62)])
        .split(outer[1]);

    render_header(frame, outer[0]);
    render_actions(frame, top[0], app);
    render_status(frame, top[1], app);
    render_logs(frame, outer[2], app);
    render_footer(frame, outer[3]);
}

pub(crate) fn log_view_capacity(area: Rect) -> usize {
    area.height.saturating_sub(2).max(1) as usize
}

pub(crate) fn log_view_content_width(area: Rect) -> usize {
    area.width.saturating_sub(2).max(1) as usize
}

pub(crate) fn log_viewport(area: Rect) -> Rect {
    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(12),
            Constraint::Length(10),
            Constraint::Length(2),
        ])
        .split(area);
    outer[2]
}

fn render_header(frame: &mut Frame<'_>, area: Rect) {
    let header = Paragraph::new(vec![
        Line::from(vec![
            Span::styled(
                "Bewiki Suppressor Control Center",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw("  "),
            Span::styled(
                "supervisory operator client",
                Style::default().fg(Color::Yellow),
            ),
        ]),
        Line::from("Tab switches focus. When Live Output is focused, arrow keys scroll logs."),
    ])
    .block(Block::default().borders(Borders::ALL).title("Overview"));
    frame.render_widget(header, area);
}

fn render_actions(frame: &mut Frame<'_>, area: Rect, app: &ControlApp) {
    let items = UiAction::all()
        .iter()
        .map(|action| {
            ListItem::new(Line::from(vec![
                Span::styled("• ", Style::default().fg(Color::Magenta)),
                Span::styled(action.label(), Style::default().fg(Color::White)),
            ]))
        })
        .collect::<Vec<_>>();

    let list = List::new(items)
        .block(focused_block("Actions", app.focus == FocusPane::Actions))
        .highlight_style(
            Style::default()
                .bg(Color::Blue)
                .fg(Color::Black)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol("▶ ");

    let detail_area = centered_bottom(area, 4);
    let mut state = ListState::default();
    state.select(Some(app.selected));
    frame.render_stateful_widget(list, area, &mut state);
    frame.render_widget(Clear, detail_area);
    let detail = Paragraph::new(app.selected_action().detail())
        .block(focused_block(
            "Selected Action",
            app.focus == FocusPane::Actions,
        ))
        .wrap(Wrap { trim: true });
    frame.render_widget(detail, detail_area);
}

fn render_status(frame: &mut Frame<'_>, area: Rect, app: &ControlApp) {
    let lines = build_status_lines(&app.paths, &app.status);
    let widget = Paragraph::new(lines)
        .block(Block::default().borders(Borders::ALL).title("Status"))
        .wrap(Wrap { trim: true });
    frame.render_widget(widget, area);
}

fn build_status_lines(paths: &RuntimePaths, status: &StatusSnapshot) -> Vec<Line<'static>> {
    let protection_line = if let Some(runtime_status) = &status.runtime_status {
        let realtime = &runtime_status.realtime;
        let pid = status
            .daemon_pid
            .map(|value| format!("pid {value}"))
            .unwrap_or_else(|| "no pid".to_string());
        let uptime = realtime
            .daemon_started_at
            .map(|at| format_duration(Utc::now() - at))
            .unwrap_or_else(|| "unknown uptime".to_string());
        let dry_run = if runtime_status.dry_run {
            "dry-run"
        } else {
            "live"
        };
        let launch = runtime_status
            .launch_path
            .as_ref()
            .map(|path| path.kind.as_str())
            .unwrap_or("unknown-launch");
        Line::from(vec![
            Span::styled("Protection: ", Style::default().fg(Color::Gray)),
            Span::styled(
                render_protection_state(status, runtime_status),
                protection_style(status, runtime_status),
            ),
            Span::raw(format!(" ({pid}, {uptime}, {dry_run}, {launch})")),
        ])
    } else if status.daemon_running {
        Line::from(vec![
            Span::styled("Protection: ", Style::default().fg(Color::Gray)),
            Span::styled("running", Style::default().fg(Color::Yellow)),
            Span::raw(format!(" (pid {})", status.daemon_pid.unwrap_or_default())),
        ])
    } else if let Some(pid) = status.daemon_pid {
        Line::from(vec![
            Span::styled("Protection: ", Style::default().fg(Color::Gray)),
            Span::styled("stale pid file", Style::default().fg(Color::Yellow)),
            Span::raw(format!(" (pid {pid})")),
        ])
    } else {
        Line::from(vec![
            Span::styled("Protection: ", Style::default().fg(Color::Gray)),
            Span::styled("not running", Style::default().fg(Color::Red)),
        ])
    };

    let mut lines = vec![protection_line];

    if let Some(runtime_status) = &status.runtime_status {
        lines.push(Line::from(format!(
            "Current work: {}",
            render_current_work(&runtime_status.realtime)
        )));
        lines.push(Line::from(format!(
            "Lag: {}",
            render_lag(&runtime_status.realtime)
        )));
        lines.push(Line::from(render_last_successful_hide(
            &runtime_status.realtime,
        )));
        lines.push(Line::from(render_last_observed_row(
            &runtime_status.realtime,
        )));
        lines.push(Line::from(render_latest_issue(
            status,
            runtime_status,
            paths,
        )));
        lines.extend(render_recheck_freshness_lines(runtime_status));
        if let Some(warning) = runtime_status.realtime.latest_recovery_warnings.first() {
            lines.push(Line::from(render_recovery_warning_line(
                warning,
                runtime_status.realtime.latest_recovery_warnings.len(),
            )));
        }
        if let Some(summary) = runtime_status.realtime.latest_recovery_summary.as_ref()
            && summary.candidate_source.is_some()
        {
            lines.push(Line::from(render_recovery_candidate_line(summary)));
        }
        if let Some(refresh) = runtime_status.realtime.last_source_refresh.as_ref() {
            lines.push(Line::from(format!(
                "Watched-page reload: {} new={} removed={} deferred_until={}",
                refresh.outcome,
                refresh.new_titles_count,
                refresh.removed_titles_count,
                refresh
                    .deferred_until
                    .as_ref()
                    .map(render_short_timestamp)
                    .unwrap_or_else(|| "none".to_string())
            )));
        }
        lines.push(Line::from(format!(
            "Watched set: {} listed / {} watched from {}",
            status.listed_titles,
            status.watched_titles,
            status.source_title.as_deref().unwrap_or("not cached yet")
        )));
        if let Some(command_report) = &status.command_report {
            lines.extend(render_command_report_lines(command_report));
        }
        if let Some(notice) = runtime_status.compatibility_notice.as_ref() {
            lines.extend(render_compatibility_notice_lines("Compatibility", notice));
        }
        if let Some(last_notice) = runtime_status.last_notice.as_deref() {
            let rendered = if let Some(at) = runtime_status.last_notice_at {
                format!(
                    "Latest notice: {} ({})",
                    last_notice,
                    at.format("%H:%M:%S UTC")
                )
            } else {
                format!("Latest notice: {last_notice}")
            };
            lines.push(Line::from(rendered));
        }
    } else if let Some(command_report) = &status.command_report {
        lines.extend(render_command_report_lines(command_report));
    }

    if let Some(notice) = status.compatibility_notice.as_ref() {
        lines.extend(render_compatibility_notice_lines("Status notice", notice));
    }

    if let Some(error) = &status.status_error {
        lines.push(Line::from(vec![
            Span::styled("Status note: ", Style::default().fg(Color::Yellow)),
            Span::raw(error.clone()),
        ]));
    }

    lines
}

fn render_protection_state(
    status: &StatusSnapshot,
    runtime_status: &crate::state::RuntimeStatus,
) -> String {
    if !status.daemon_running && status.daemon_pid.is_some() {
        return "stale pid file".to_string();
    }
    if runtime_status.realtime.state.is_empty() {
        runtime_status.daemon_state.clone()
    } else {
        runtime_status.realtime.state.clone()
    }
}

fn protection_style(
    status: &StatusSnapshot,
    runtime_status: &crate::state::RuntimeStatus,
) -> Style {
    if !status.daemon_running && status.daemon_pid.is_some() {
        return Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD);
    }
    match runtime_status.realtime.state.as_str() {
        "healthy" => Style::default()
            .fg(Color::Green)
            .add_modifier(Modifier::BOLD),
        "catching-up" | "reconnecting" | "starting" => Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
        "stale" | "unhealthy" | "blocked" => {
            Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)
        }
        _ => Style::default().fg(Color::Gray),
    }
}

fn render_current_work(status: &crate::state::RealtimeRuntimeStatus) -> String {
    let Some(task) = status.current_task.as_ref() else {
        return "unknown".to_string();
    };
    let mut line = task.label.clone();
    if let (Some(done), Some(total)) = (task.progress_done, task.progress_total) {
        line.push_str(&format!(" ({done}/{total})"));
    }
    if task.window_start.is_some() || task.window_end.is_some() {
        line.push_str(&format!(
            " [{} -> {}]",
            task.window_start
                .as_ref()
                .map(render_short_timestamp)
                .unwrap_or_else(|| "unknown".to_string()),
            task.window_end
                .as_ref()
                .map(render_short_timestamp)
                .unwrap_or_else(|| "unknown".to_string())
        ));
    }
    if let Some(expected_resume_at) = task.expected_resume_at.as_ref() {
        line.push_str(&format!(
            " resume {}",
            render_short_timestamp(expected_resume_at)
        ));
    }
    line
}

fn render_lag(status: &crate::state::RealtimeRuntimeStatus) -> String {
    let lag = if let Some(millis) = status.current_lag_millis {
        if millis < 1000 {
            format!("{millis}ms")
        } else {
            format!("{:.1}s", millis as f64 / 1000.0)
        }
    } else if let Some(seconds) = status.current_lag_seconds {
        format!("{seconds}s")
    } else {
        "unknown".to_string()
    };
    let source = status.current_lag_source.as_deref().unwrap_or("unknown");
    format!(
        "{lag} [{source}], live {}/{}/{} bg {}/{}/{} p95 {}ms",
        status.live_lane.queue_depth,
        status.live_lane.in_flight,
        status.live_lane.queue_capacity,
        status.background_lane.queue_depth,
        status.background_lane.in_flight,
        status.background_lane.queue_capacity,
        status.latency.observed_to_hidden.p95_ms.unwrap_or(0)
    )
}

fn render_last_successful_hide(status: &crate::state::RealtimeRuntimeStatus) -> String {
    match (
        status.last_successful_hide_title.as_deref(),
        status.last_successful_hide_revid,
        status.last_successful_hide_at,
    ) {
        (Some(title), Some(revid), Some(at)) => format!(
            "Last successful hide: {title} at {} revid {revid} {}",
            render_short_timestamp(&at),
            status.last_successful_hide_url.as_deref().unwrap_or(""),
        ),
        _ => "Last successful hide: not recorded yet".to_string(),
    }
}

fn render_last_observed_row(status: &crate::state::RealtimeRuntimeStatus) -> String {
    if let (Some(title), Some(revid), Some(at)) = (
        status.last_matching_title.as_deref(),
        status.last_matching_revid,
        status.last_matching_edit_at,
    ) {
        return format!(
            "Last watched edit: {title} at {} revid {revid} {}",
            render_short_timestamp(&at),
            status.last_matching_revid_url.as_deref().unwrap_or(""),
        );
    }
    if let Some(at) = status.last_event_observed_at {
        return format!("Last target-wiki event: {}", render_short_timestamp(&at));
    }
    "Last target-wiki event: not recorded yet".to_string()
}

fn render_latest_issue(
    status: &StatusSnapshot,
    runtime_status: &crate::state::RuntimeStatus,
    _paths: &RuntimePaths,
) -> String {
    if let Some(issue) = runtime_status.realtime.latest_actionable_issue.as_ref() {
        return format!(
            "Latest issue: {}. Next: {}",
            issue.summary, issue.next_action
        );
    }
    if let Some(notice) = runtime_status.compatibility_notice.as_ref() {
        return format!(
            "Latest issue: {}. Next: {}",
            notice.summary, notice.operator_action
        );
    }
    if let Some(notice) = status.compatibility_notice.as_ref() {
        return format!(
            "Latest issue: {}. Next: {}",
            notice.summary, notice.operator_action
        );
    }
    let _ = status;
    "Latest issue: none".to_string()
}

fn render_recheck_freshness_lines(
    runtime_status: &crate::state::RuntimeStatus,
) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    if let Some(freshness) = runtime_status.reconciliation.freshness.as_ref() {
        let oldest = freshness
            .oldest_full_check_at
            .as_ref()
            .map(render_short_timestamp)
            .or_else(|| {
                freshness
                    .oldest_full_check_age_seconds
                    .map(render_age_seconds)
            })
            .unwrap_or_else(|| "unknown".to_string());
        let oldest_title = freshness
            .oldest_full_check_title
            .as_deref()
            .unwrap_or("unknown page");
        lines.push(Line::from(format!(
            "Full recheck freshness: {}/{} pages older than {}h; oldest {} ({})",
            freshness.pages_older_than_target,
            freshness.total_pages,
            freshness.target_hours,
            oldest,
            oldest_title
        )));
    }

    let mut verification_parts = Vec::new();
    if runtime_status
        .realtime
        .last_daytime_verification_at
        .is_some()
        || runtime_status
            .realtime
            .last_daytime_verification_result
            .is_some()
    {
        verification_parts.push(format!(
            "Last 24 hours {}",
            render_verification_outcome(
                runtime_status
                    .realtime
                    .last_daytime_verification_result
                    .as_deref(),
                runtime_status.realtime.last_daytime_verification_at,
            )
        ));
    }
    if runtime_status
        .realtime
        .last_nightly_full_recheck_at
        .is_some()
        || runtime_status
            .realtime
            .last_nightly_full_recheck_result
            .is_some()
    {
        verification_parts.push(format!(
            "full watched-set {}",
            render_verification_outcome(
                runtime_status
                    .realtime
                    .last_nightly_full_recheck_result
                    .as_deref(),
                runtime_status.realtime.last_nightly_full_recheck_at,
            )
        ));
    }
    if !verification_parts.is_empty() {
        lines.push(Line::from(format!(
            "Scheduled verification: {}",
            verification_parts.join("; ")
        )));
    }
    lines
}

fn render_recovery_warning_line(warning: &WarningSummary, warning_count: usize) -> String {
    let mut details = vec![format!("{} x{}", warning.class, warning.count)];
    if let Some(status) = warning.http_status {
        details.push(format!("http={status}"));
    }
    if let Some(seconds) = warning.retry_after_seconds {
        details.push(format!("retry_after={}s", seconds));
    }
    if !warning.operation.is_empty() {
        details.push(format!("op={}", warning.operation));
    }
    if !warning.sample_titles.is_empty() {
        details.push(format!("titles={}", warning.sample_titles.join(", ")));
    }
    if warning.stopped_early {
        details.push("stopped-early".to_string());
    }
    let prefix = if warning_count > 1 {
        format!("Recovery warnings ({warning_count} kinds): ")
    } else {
        "Recovery warnings: ".to_string()
    };
    format!("{prefix}{}", details.join(" "))
}

fn render_recovery_candidate_line(summary: &CoverageSummary) -> String {
    let source = summary.candidate_source.as_deref().unwrap_or("unknown");
    let elapsed = summary
        .candidate_discovery_elapsed_ms
        .map(|value| format!("{value}ms"))
        .unwrap_or_else(|| "unknown".to_string());
    let mut line = format!(
        "Recovery candidates: source={} candidates={} watched={} chunks={} elapsed={}",
        source,
        summary.candidate_count,
        summary.watched_candidate_count,
        summary.candidate_chunk_count,
        elapsed
    );
    if let Some(reason) = summary.fallback_reason.as_deref() {
        line.push_str(&format!(" fallback={reason}"));
    }
    line
}

fn render_short_timestamp(value: &chrono::DateTime<Utc>) -> String {
    value.format("%Y-%m-%d %H:%M:%S UTC").to_string()
}

fn render_age_seconds(age_seconds: i64) -> String {
    format!(
        "{} ago",
        format_duration(chrono::TimeDelta::seconds(age_seconds.max(0)))
    )
}

fn render_verification_outcome(
    result: Option<&str>,
    completed_at: Option<chrono::DateTime<Utc>>,
) -> String {
    match (result, completed_at) {
        (Some("completed"), Some(at)) => format!("completed at {}", render_short_timestamp(&at)),
        (Some(result), Some(at)) => format!("{result} at {}", render_short_timestamp(&at)),
        (Some(result), None) => result.to_string(),
        (None, Some(at)) => format!("completed at {}", render_short_timestamp(&at)),
        (None, None) => "not recorded yet".to_string(),
    }
}

fn format_duration(duration: chrono::TimeDelta) -> String {
    let seconds = duration.num_seconds().max(0);
    let hours = seconds / 3600;
    let minutes = (seconds % 3600) / 60;
    let rem_seconds = seconds % 60;
    if hours > 0 {
        format!("{hours}h {minutes}m {rem_seconds}s")
    } else if minutes > 0 {
        format!("{minutes}m {rem_seconds}s")
    } else {
        format!("{rem_seconds}s")
    }
}

fn render_logs(frame: &mut Frame<'_>, area: Rect, app: &ControlApp) {
    let visible_logs = log_view_capacity(area);
    let top = app.current_log_top(visible_logs, log_view_content_width(area));
    let mut display = app.logs.iter().cloned().map(Line::from).collect::<Vec<_>>();
    if display.is_empty() {
        display.push(Line::from("No logs yet. Run an action to see output here."));
    }
    let title = if app.follow_logs {
        "Live Output [latest]"
    } else {
        "Live Output [scrolling]"
    };
    let logs = Paragraph::new(display)
        .block(focused_block(title, app.focus == FocusPane::Output))
        .scroll((top as u16, 0));
    frame.render_widget(logs, area);
}

fn render_footer(frame: &mut Frame<'_>, area: Rect) {
    let footer = Paragraph::new(Line::from(vec![
        Span::styled("Keys: ", Style::default().fg(Color::Gray)),
        Span::raw("Tab or ←/→ focus  "),
        Span::raw("↑/↓ move or scroll  "),
        Span::raw("PgUp/PgDn page  "),
        Span::raw("Home oldest  "),
        Span::raw("End latest  "),
        Span::raw("Enter run  "),
        Span::raw("r refresh  "),
        Span::raw("q quit"),
    ]));
    frame.render_widget(footer, area);
}

fn focused_block<'a>(title: &'a str, focused: bool) -> Block<'a> {
    let border_style = if focused {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default()
    };
    Block::default()
        .borders(Borders::ALL)
        .border_style(border_style)
        .title(title)
}

fn centered_bottom(area: Rect, height: u16) -> Rect {
    Rect {
        x: area.x,
        y: area.y + area.height.saturating_sub(height),
        width: area.width,
        height,
    }
}

fn render_compatibility_notice_lines(
    label: &str,
    notice: &CompatibilityNotice,
) -> Vec<Line<'static>> {
    let severity = if notice.blocking {
        format!("{} blocking", notice.severity)
    } else {
        notice.severity.clone()
    };
    let mut lines = vec![Line::from(vec![
        Span::styled(
            format!("{label}: "),
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(format!(
            "{} [{}] {}",
            severity, notice.scope, notice.summary
        )),
    ])];
    if notice.previous_value.is_some() || notice.expected_value.is_some() {
        lines.push(Line::from(format!(
            "{label} path: {} -> {}",
            notice.previous_value.as_deref().unwrap_or("unknown"),
            notice.expected_value.as_deref().unwrap_or("unknown")
        )));
    }
    lines.push(Line::from(format!(
        "{label} action: {}",
        notice.operator_action
    )));
    if let Some(approval_text) = notice.approval_text.as_deref() {
        lines.push(Line::from(format!("{label} approval: {approval_text}")));
    }
    if let Some(rollback_path) = notice.rollback_path.as_deref() {
        lines.push(Line::from(format!("{label} rollback: {rollback_path}")));
    }
    lines
}

fn render_command_report_lines(report: &CommandReportSurface) -> Vec<Line<'static>> {
    let mode = if report.report_only {
        "report-only"
    } else {
        "hide-run"
    };
    let generated_at = report
        .generated_at
        .map(|at| at.format("%H:%M:%S UTC").to_string())
        .unwrap_or_else(|| "unknown time".to_string());
    let mut lines = vec![
        Line::from(vec![
            Span::styled("Command output: ", Style::default().fg(Color::Gray)),
            Span::styled(
                report
                    .scope_label
                    .clone()
                    .unwrap_or_else(|| report.command.clone()),
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(format!(" [{}] {} ({})", mode, generated_at, report.command)),
        ]),
        Line::from(format!(
            "Counts: checked={} hidden={} already_hidden={} skipped={} failed={} unresolved={}",
            report.counts.checked,
            report.counts.hidden,
            report.counts.already_hidden,
            report.counts.skipped,
            report.counts.failed,
            report.counts.unresolved
        )),
    ];
    if report.window.start.is_some() || report.window.end.is_some() {
        lines.push(Line::from(format!(
            "Window: {} -> {}",
            report
                .window
                .start
                .map(|at| at.format("%H:%M:%S UTC").to_string())
                .unwrap_or_else(|| "unknown".to_string()),
            report
                .window
                .end
                .map(|at| at.format("%H:%M:%S UTC").to_string())
                .unwrap_or_else(|| "unknown".to_string())
        )));
    }
    if let Some(reason) = report.stopped_early_reason.as_deref() {
        lines.push(Line::from(format!(
            "Stopped early: {} until={}",
            reason,
            report
                .backoff_until
                .map(|at| at.format("%H:%M:%S UTC").to_string())
                .unwrap_or_else(|| "none".to_string())
        )));
    }
    if let Some(next_action) = report.next_action.as_deref() {
        lines.push(Line::from(format!("Next action: {}", next_action)));
    }
    if let Some(unresolved) = report.unresolved_items.first() {
        lines.push(Line::from(format!(
            "First unresolved: {} revid {} {}",
            unresolved.title,
            unresolved.revid,
            unresolved.revision_url.as_deref().unwrap_or(""),
        )));
    }
    if let Some(notice) = report.compatibility_notice.as_ref() {
        lines.extend(render_compatibility_notice_lines("Command notice", notice));
    }
    lines
}

#[cfg(test)]
mod tests {
    use chrono::Utc;

    use super::*;
    use crate::config::RuntimePaths;
    use crate::state::{
        CommandReportCounts, CommandReportSurface, CommandReportWindow, CompatibilityNotice,
        RealtimeRuntimeStatus, RuntimeStatus, WarningSummary,
    };
    use crate::tui_status::StatusSnapshot;

    fn lines_to_text(lines: &[Line<'_>]) -> String {
        lines
            .iter()
            .flat_map(|line| line.spans.iter().map(|span| span.content.as_ref()))
            .collect::<Vec<_>>()
            .join("\n")
    }

    fn test_paths() -> RuntimePaths {
        RuntimePaths {
            config_path: "/tmp/config.toml".into(),
            state_dir: "/tmp/state".into(),
            env_file: "/tmp/.env".into(),
            cache_file: "/tmp/state/cache.json".into(),
            last_event_id_file: "/tmp/state/last_event_id".into(),
            processed_revids_file: "/tmp/state/processed.json".into(),
            nightly_sweep_progress_file: "/tmp/state/progress.json".into(),
            runtime_status_file: "/tmp/state/runtime.json".into(),
            pid_file: "/tmp/state/pid".into(),
        }
    }

    #[test]
    fn command_report_lines_render_counts_next_action_and_notice() {
        let lines = render_command_report_lines(&CommandReportSurface {
            command: "coverage-report".to_string(),
            generated_at: Some(Utc::now()),
            report_only: true,
            window: CommandReportWindow {
                start: Some(Utc::now()),
                end: Some(Utc::now()),
            },
            counts: CommandReportCounts {
                checked: 12,
                hidden: 3,
                already_hidden: 2,
                skipped: 1,
                failed: 0,
                unresolved: 4,
            },
            stopped_early_reason: Some("rate-limited".to_string()),
            next_action: Some("rerun after backoff".to_string()),
            compatibility_notice: Some(CompatibilityNotice {
                scope: "command-report".to_string(),
                severity: "migration-required".to_string(),
                detected_at: Some(Utc::now()),
                previous_value: Some("legacy command report".to_string()),
                expected_value: Some("bounded command report".to_string()),
                summary: "previous report shape is no longer safe".to_string(),
                operator_action: "trust the bounded command report".to_string(),
                approval_text: Some("confirm the current binary rewrote the report".to_string()),
                rollback_path: Some("rerun the last trusted report workflow".to_string()),
                blocking: true,
            }),
            ..CommandReportSurface::default()
        });
        let rendered = lines_to_text(&lines);

        assert!(rendered.contains("coverage-report"));
        assert!(rendered.contains("report-only"));
        assert!(rendered.contains("checked=12"));
        assert!(rendered.contains("unresolved=4"));
        assert!(rendered.contains("Next action: rerun after backoff"));
        assert!(rendered.contains("migration-required"));
        assert!(rendered.contains("command-report"));
        assert!(rendered.contains("trust the bounded command report"));
        assert!(rendered.contains("confirm the current binary rewrote the report"));
        assert!(rendered.contains("rerun the last trusted report workflow"));
    }

    #[test]
    fn status_lines_render_operator_first_rows_and_command_output() {
        let lines = build_status_lines(
            &test_paths(),
            &StatusSnapshot {
                daemon_pid: Some(55),
                daemon_running: true,
                compatibility_notice: Some(CompatibilityNotice {
                    scope: "pid-file".to_string(),
                    severity: "warning".to_string(),
                    detected_at: Some(Utc::now()),
                    previous_value: Some("/tmp/state/pid".to_string()),
                    expected_value: Some("running daemon pid plus runtime_status.json".to_string()),
                    summary: "pid file points to a non-running process (stale marker)".to_string(),
                    operator_action: "clear the stale pid marker".to_string(),
                    approval_text: Some("confirm the replacement pid is running".to_string()),
                    rollback_path: Some("restart the last trusted supervisor workflow".to_string()),
                    blocking: true,
                }),
                runtime_status: Some(RuntimeStatus {
                    daemon_state: "running".to_string(),
                    compatibility_notice: Some(CompatibilityNotice {
                        scope: "launch-path".to_string(),
                        severity: "migration-required".to_string(),
                        detected_at: Some(Utc::now()),
                        previous_value: Some("journalctl -u suppressor.service".to_string()),
                        expected_value: Some(
                            "TUI-managed daemon child plus runtime_status.json".to_string(),
                        ),
                        summary: "current deployment is not systemd-managed".to_string(),
                        operator_action: "verify the TUI-managed child process".to_string(),
                        approval_text: Some(
                            "trust this setup only after confirming the active supervisor path"
                                .to_string(),
                        ),
                        rollback_path: Some(
                            "restart the last trusted workflow and verify it using the previous path"
                                .to_string(),
                        ),
                        blocking: true,
                    }),
                    realtime: RealtimeRuntimeStatus {
                        state: "unhealthy".to_string(),
                        stale_threshold_seconds: 10,
                        current_task: Some(crate::state::CurrentTaskSnapshot {
                            task_kind: "catch-up".to_string(),
                            label: "since last successful hide".to_string(),
                            progress_done: Some(1),
                            progress_total: Some(3),
                            window_start: Some(Utc::now()),
                            window_end: Some(Utc::now()),
                            started_at: Some(Utc::now()),
                            expected_resume_at: None,
                        }),
                        latest_actionable_issue: Some(crate::state::ActionableIssueSnapshot {
                            source: "live-hide".to_string(),
                            severity: "error".to_string(),
                            summary: "live hide failed".to_string(),
                            next_action: "watch the recovery window".to_string(),
                            detected_at: Some(Utc::now()),
                        }),
                        latest_recovery_warnings: vec![WarningSummary {
                            class: "rate-limit".to_string(),
                            http_status: Some(429),
                            retry_after_seconds: Some(30),
                            operation: "fetch-revisions".to_string(),
                            count: 3,
                            sample_titles: vec!["Sensitive".to_string()],
                            stopped_early: true,
                            ..WarningSummary::default()
                        }],
                        backoff_until: Some(Utc::now()),
                        last_successful_hide_title: Some("Sensitive".to_string()),
                        last_successful_hide_revid: Some(77),
                        last_successful_hide_at: Some(Utc::now()),
                        last_successful_hide_url: Some(
                            "https://example.invalid/wiki/Special:Diff/77".to_string(),
                        ),
                        latest_notice: Some("observed target-wiki event".to_string()),
                        last_daytime_verification_at: Some(Utc::now()),
                        last_daytime_verification_result: Some(
                            "failed: non-json-response".to_string(),
                        ),
                        last_nightly_full_recheck_at: Some(Utc::now()),
                        last_nightly_full_recheck_result: Some("completed".to_string()),
                        ..RealtimeRuntimeStatus::default()
                    },
                    reconciliation: crate::state::ReconciliationRuntimeStatus {
                        freshness: Some(crate::state::RecheckFreshnessSnapshot {
                            target_hours: 24,
                            total_pages: 20,
                            pages_older_than_target: 4,
                            oldest_full_check_at: Some(Utc::now() - chrono::TimeDelta::days(2)),
                            oldest_full_check_title: Some("Old page".to_string()),
                            oldest_full_check_age_seconds: Some(172800),
                            last_daytime_verification_result: Some(
                                "failed: non-json-response".to_string(),
                            ),
                            last_nightly_full_recheck_result: Some("completed".to_string()),
                            computed_at: Some(Utc::now()),
                        }),
                        ..crate::state::ReconciliationRuntimeStatus::default()
                    },
                    ..RuntimeStatus::default()
                }),
                command_report: Some(CommandReportSurface {
                    command: "coverage-report".to_string(),
                    report_only: true,
                    generated_at: Some(Utc::now()),
                    counts: CommandReportCounts {
                        checked: 3,
                        unresolved: 1,
                        ..CommandReportCounts::default()
                    },
                    next_action: Some("rerun after backoff".to_string()),
                    ..CommandReportSurface::default()
                }),
                ..StatusSnapshot::default()
            },
        );
        let line_texts = lines
            .iter()
            .map(|line| {
                line.spans
                    .iter()
                    .map(|span| span.content.as_ref())
                    .collect::<String>()
            })
            .collect::<Vec<_>>();
        assert!(line_texts.iter().any(|line| line.contains("Protection: ")));
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Current work: since last successful hide"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Last successful hide: Sensitive"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Latest issue: live hide failed"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Full recheck freshness: 4/20 pages older than 24h"))
        );
        assert!(line_texts.iter().any(|line| {
            line.contains("Scheduled verification: Last 24 hours failed: non-json-response")
        }));
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Recovery warnings: rate-limit x3"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Command output: "))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Compatibility:"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Status notice:"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Compatibility approval:"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Compatibility rollback:"))
        );
    }

    #[test]
    fn status_lines_keep_command_output_distinct_without_fake_daemon_rows() {
        let lines = build_status_lines(
            &test_paths(),
            &StatusSnapshot {
                daemon_pid: Some(77),
                daemon_running: false,
                command_report: Some(CommandReportSurface {
                    command: "coverage-last-24h".to_string(),
                    scope_label: Some("Last 24 hours".to_string()),
                    report_only: true,
                    generated_at: Some(Utc::now()),
                    counts: CommandReportCounts {
                        checked: 5,
                        unresolved: 2,
                        ..CommandReportCounts::default()
                    },
                    ..CommandReportSurface::default()
                }),
                ..StatusSnapshot::default()
            },
        );
        let line_texts = lines
            .iter()
            .map(|line| {
                line.spans
                    .iter()
                    .map(|span| span.content.as_ref())
                    .collect::<String>()
            })
            .collect::<Vec<_>>();

        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Protection: stale pid file"))
        );
        assert!(
            line_texts
                .iter()
                .any(|line| line.contains("Command output: Last 24 hours"))
        );
        assert!(
            !line_texts
                .iter()
                .any(|line| line.starts_with("Current work:"))
        );
    }
}
