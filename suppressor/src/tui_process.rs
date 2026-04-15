use std::path::Path;
use std::process::Stdio;

use anyhow::Result;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::mpsc::UnboundedSender;

use crate::config::RuntimePaths;
use crate::config::default_log_filter;

pub(crate) fn build_child_command(
    current_exe: &Path,
    paths: &RuntimePaths,
    verbose: bool,
    args: &[&str],
) -> Result<Command> {
    build_child_command_owned(
        current_exe,
        paths,
        verbose,
        args.iter().map(|arg| (*arg).to_string()).collect(),
    )
}

pub(crate) fn build_child_command_owned(
    current_exe: &Path,
    paths: &RuntimePaths,
    verbose: bool,
    args: Vec<String>,
) -> Result<Command> {
    let log_filter =
        std::env::var("RUST_LOG").unwrap_or_else(|_| default_log_filter(verbose).to_string());
    let mut command = Command::new(current_exe);
    command
        .arg("--config")
        .arg(&paths.config_path)
        .args(verbose.then_some("--verbose"))
        .env("BEWIKI_ENV_FILE", &paths.env_file)
        .env("RUST_LOG", log_filter)
        .env("BEWIKI_LOG_FORMAT", "tui")
        .env("NO_COLOR", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for arg in args {
        command.arg(arg);
    }
    Ok(command)
}

pub(crate) fn spawn_pipe_reader<R>(reader: R, label: String, tx: UnboundedSender<String>)
where
    R: tokio::io::AsyncRead + Unpin + Send + 'static,
{
    tokio::spawn(async move {
        let mut lines = BufReader::new(reader).lines();
        loop {
            match lines.next_line().await {
                Ok(Some(line)) => {
                    let cleaned = sanitize_log_line(&line);
                    if !cleaned.trim().is_empty() {
                        let _ = tx.send(format!("[{}] {}", label, cleaned));
                    }
                }
                Ok(None) => break,
                Err(error) => {
                    let _ = tx.send(format!("[{}] output reader failed: {error:#}", label));
                    break;
                }
            }
        }
    });
}

pub(crate) fn sanitize_log_line(line: &str) -> String {
    let mut cleaned = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '\u{1b}' {
            if matches!(chars.peek(), Some('[')) {
                let _ = chars.next();
                for next in chars.by_ref() {
                    if ('@'..='~').contains(&next) {
                        break;
                    }
                }
            }
            continue;
        }
        match ch {
            '\r' => {}
            '\t' => cleaned.push_str("    "),
            c if c.is_control() => {}
            c => cleaned.push(c),
        }
    }
    cleaned
}

#[cfg(test)]
mod tests {
    use std::path::{Path, PathBuf};

    use super::*;
    use crate::config::RuntimePaths;

    #[test]
    fn build_child_command_injects_supervisor_env() {
        let paths = RuntimePaths {
            config_path: PathBuf::from("/tmp/config.toml"),
            state_dir: PathBuf::from("/tmp/state"),
            env_file: PathBuf::from("/tmp/.env"),
            cache_file: PathBuf::from("/tmp/state/cache.json"),
            last_event_id_file: PathBuf::from("/tmp/state/last_event_id"),
            processed_revids_file: PathBuf::from("/tmp/state/processed.json"),
            nightly_sweep_progress_file: PathBuf::from("/tmp/state/progress.json"),
            runtime_status_file: PathBuf::from("/tmp/state/runtime.json"),
            pid_file: PathBuf::from("/tmp/state/pid"),
        };

        let command =
            build_child_command(Path::new("/tmp/suppressor"), &paths, true, &["run"]).unwrap();
        let std = command.as_std();
        let args = std
            .get_args()
            .map(|arg| arg.to_string_lossy().to_string())
            .collect::<Vec<_>>();
        let envs = std
            .get_envs()
            .map(|(key, value)| {
                (
                    key.to_string_lossy().to_string(),
                    value.map(|item| item.to_string_lossy().to_string()),
                )
            })
            .collect::<Vec<_>>();

        assert_eq!(
            args,
            vec![
                "--config".to_string(),
                "/tmp/config.toml".to_string(),
                "--verbose".to_string(),
                "run".to_string()
            ]
        );
        assert!(envs.contains(&("BEWIKI_ENV_FILE".to_string(), Some("/tmp/.env".to_string()))));
        assert!(envs.contains(&("BEWIKI_LOG_FORMAT".to_string(), Some("tui".to_string()))));
        assert!(envs.contains(&("NO_COLOR".to_string(), Some("1".to_string()))));
    }

    #[test]
    fn sanitize_log_line_strips_ansi_sequences() {
        let rendered = sanitize_log_line("\u{1b}[31mhello\tworld\u{1b}[0m");
        assert_eq!(rendered, "hello    world");
    }
}
