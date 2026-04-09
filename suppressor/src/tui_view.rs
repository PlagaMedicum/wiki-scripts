use ratatui::Frame;
use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Wrap};

use crate::tui::{ControlApp, FocusPane, UiAction};

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
    let daemon_line = if app.status.daemon_running {
        Line::from(vec![
            Span::styled("Daemon: ", Style::default().fg(Color::Gray)),
            Span::styled("running", Style::default().fg(Color::Green)),
            Span::raw(format!(
                " (pid {})",
                app.status.daemon_pid.unwrap_or_default()
            )),
        ])
    } else if let Some(pid) = app.status.daemon_pid {
        Line::from(vec![
            Span::styled("Daemon: ", Style::default().fg(Color::Gray)),
            Span::styled("stale pid file", Style::default().fg(Color::Yellow)),
            Span::raw(format!(" (pid {})", pid)),
        ])
    } else {
        Line::from(vec![
            Span::styled("Daemon: ", Style::default().fg(Color::Gray)),
            Span::styled("not running", Style::default().fg(Color::Red)),
        ])
    };

    let managed = app
        .status
        .managed_session
        .clone()
        .unwrap_or_else(|| "none".to_string());
    let daemon_state = app
        .status
        .runtime_status
        .as_ref()
        .map(|status| {
            if status.daemon_state.is_empty() {
                "unknown".to_string()
            } else {
                status.daemon_state.clone()
            }
        })
        .unwrap_or_else(|| {
            if app.status.daemon_running {
                "running".to_string()
            } else {
                "not running".to_string()
            }
        });

    let mut lines = vec![
        daemon_line,
        Line::from(format!("Daemon state: {}", daemon_state)),
        Line::from(format!("Managed session: {}", managed)),
        Line::from(format!("Config: {}", app.paths.config_path.display())),
        Line::from(format!("Env file: {}", app.status.env_file.display())),
        Line::from(format!("PID file: {}", app.status.pid_file.display())),
        Line::from(format!(
            "Source page: {}",
            app.status
                .source_title
                .as_deref()
                .unwrap_or("not cached yet")
        )),
        Line::from(format!(
            "Listed titles: {}   Watched titles: {}",
            app.status.listed_titles, app.status.watched_titles
        )),
        Line::from(format!(
            "Processed revisions: {}   Checkpoint pages: {}",
            app.status.processed_revids, app.status.checkpoint_pages
        )),
        Line::from(format!(
            "Last Event-ID: {}",
            app.status
                .last_event_id
                .as_deref()
                .unwrap_or("not recorded yet")
        )),
    ];

    if let Some(runtime_status) = &app.status.runtime_status {
        lines.push(Line::from(render_reconcile_line(
            &runtime_status.reconciliation,
        )));
        if let Some(phase) = runtime_status.reconciliation.phase.as_deref() {
            let rendered = format!(
                "Phase: {} {}/{}",
                phase,
                runtime_status.reconciliation.phase_completed,
                runtime_status.reconciliation.phase_total
            );
            lines.push(Line::from(rendered));
        }
        if let Some(current_title) = runtime_status.reconciliation.current_title.as_deref() {
            lines.push(Line::from(format!("Current title: {}", current_title)));
        }
        if let Some(queued_mode) = runtime_status.reconciliation.queued_mode.as_deref() {
            lines.push(Line::from(format!("Queued rerun: {}", queued_mode)));
        }
        if let Some(last_notice) = runtime_status.last_notice.as_deref() {
            let rendered = if let Some(at) = runtime_status.last_notice_at {
                format!(
                    "Last notice: {} ({})",
                    last_notice,
                    at.format("%H:%M:%S UTC")
                )
            } else {
                format!("Last notice: {}", last_notice)
            };
            lines.push(Line::from(rendered));
        }
    }

    if let Some(error) = &app.status.status_error {
        lines.push(Line::from(vec![
            Span::styled("Status note: ", Style::default().fg(Color::Yellow)),
            Span::raw(error.clone()),
        ]));
    }

    let widget = Paragraph::new(lines)
        .block(Block::default().borders(Borders::ALL).title("Status"))
        .wrap(Wrap { trim: true });
    frame.render_widget(widget, area);
}

fn render_logs(frame: &mut Frame<'_>, area: Rect, app: &ControlApp) {
    let visible_logs = log_view_capacity(area);
    let top = app.current_log_top(visible_logs);
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
        .scroll((top as u16, 0))
        .wrap(Wrap { trim: false });
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

fn render_reconcile_line(status: &crate::state::ReconciliationRuntimeStatus) -> String {
    if status.active {
        let mode = status.mode.as_deref().unwrap_or("unknown");
        let progress = render_progress_bar(
            status.phase_completed,
            status.phase_total.max(status.total_titles),
            16,
        );
        format!(
            "Reconciliation: active [{}] {}/{} {}",
            mode,
            status.phase_completed,
            status.phase_total.max(status.total_titles),
            progress
        )
    } else if let Some(result) = status.last_result.as_deref() {
        let mode = status.mode.as_deref().unwrap_or("last");
        format!("Reconciliation: idle [{}] {}", mode, result)
    } else {
        "Reconciliation: idle".to_string()
    }
}

fn render_progress_bar(done: usize, total: usize, width: usize) -> String {
    if total == 0 || width == 0 {
        return "[no work]".to_string();
    }
    let filled = ((done.saturating_mul(width)) / total).min(width);
    format!(
        "[{}{}]",
        "#".repeat(filled),
        ".".repeat(width.saturating_sub(filled))
    )
}
