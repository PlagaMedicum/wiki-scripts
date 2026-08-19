use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(
    name = "suppressor",
    version,
    about = "public revision-delete daemon first developed for be.wiki"
)]
pub struct Cli {
    #[arg(long, global = true)]
    pub config: Option<PathBuf>,
    #[arg(long, global = true)]
    pub verbose: bool,
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    Run,
    Status {
        #[arg(long)]
        json: bool,
    },
    Health {
        #[arg(long)]
        json: bool,
    },
    LastEdits {
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long)]
        json: bool,
    },
    Perf {
        #[arg(long)]
        json: bool,
    },
    CheckAuth,
    ReloadCache,
    #[command(name = "catch-up-now")]
    CatchUpNow,
    DryRun,
    HideRevid {
        id: u64,
    },
    #[command(name = "smoke-test")]
    SmokeTest {
        #[arg(long)]
        page: Option<String>,
    },
    EmergencyCatchup {
        #[arg(long)]
        start: Option<String>,
        #[arg(long)]
        end: Option<String>,
        #[arg(long)]
        allow_large_window: bool,
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        report_only: bool,
    },
    CoverageReport {
        #[arg(long)]
        start: String,
        #[arg(long)]
        end: Option<String>,
        #[arg(long)]
        allow_large_window: bool,
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        report_only: bool,
    },
    #[command(name = "coverage-last-24h")]
    CoverageLast24h {
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        report_only: bool,
    },
    #[command(name = "server-start")]
    ServerStart {
        #[arg(long)]
        dry_run: bool,
        #[arg(long, default_value_t = 120)]
        status_timeout_seconds: u64,
        #[arg(long)]
        log_file: Option<PathBuf>,
    },
    #[command(name = "supervisor-run", hide = true)]
    SupervisorRun {
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        log_file: PathBuf,
    },
    NightlySweepNow,
    PrintEffectiveConfig,
}

impl Cli {
    pub fn required_config(&self) -> Result<PathBuf> {
        self.config
            .clone()
            .context("Missing required --config /path/to/wiki.toml")
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    #[test]
    fn parses_hide_revid_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "--verbose",
            "hide-revid",
            "42",
        ])
        .unwrap();
        assert_eq!(cli.config, Some(PathBuf::from("config.example.toml")));
        assert!(cli.verbose);
        match cli.command {
            Command::HideRevid { id } => assert_eq!(id, 42),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_smoke_test_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "smoke-test",
            "--page",
            "User:Bot/Test",
        ])
        .unwrap();
        match cli.command {
            Command::SmokeTest { page } => assert_eq!(page.as_deref(), Some("User:Bot/Test")),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_config_after_subcommand() {
        let cli = Cli::try_parse_from(["suppressor", "dry-run", "--config", "config.example.toml"])
            .unwrap();
        assert_eq!(cli.config, Some(PathBuf::from("config.example.toml")));
        match cli.command {
            Command::DryRun => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_status_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "status",
            "--json",
        ])
        .unwrap();
        match cli.command {
            Command::Status { json } => assert!(json),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn requires_an_explicit_config_file() {
        let cli = Cli::try_parse_from(["suppressor", "status"]).unwrap();
        assert!(cli.required_config().is_err());
    }

    #[test]
    fn parses_health_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "health",
            "--json",
        ])
        .unwrap();
        match cli.command {
            Command::Health { json } => assert!(json),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_last_edits_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "last-edits",
            "--limit",
            "7",
        ])
        .unwrap();
        match cli.command {
            Command::LastEdits { limit, json } => {
                assert_eq!(limit, 7);
                assert!(!json);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_perf_command() {
        let cli =
            Cli::try_parse_from(["suppressor", "--config", "config.example.toml", "perf"]).unwrap();
        match cli.command {
            Command::Perf { json } => assert!(!json),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_emergency_catchup_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "emergency-catchup",
            "--start",
            "2026-04-24T16:00:00Z",
            "--end",
            "2026-04-24T16:30:00Z",
            "--dry-run",
        ])
        .unwrap();
        match cli.command {
            Command::EmergencyCatchup {
                start,
                end,
                allow_large_window,
                dry_run,
                report_only,
            } => {
                assert_eq!(start.as_deref(), Some("2026-04-24T16:00:00Z"));
                assert_eq!(end.as_deref(), Some("2026-04-24T16:30:00Z"));
                assert!(!allow_large_window);
                assert!(dry_run);
                assert!(!report_only);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_coverage_report_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "coverage-report",
            "--start",
            "2026-04-24T16:00:00Z",
            "--report-only",
        ])
        .unwrap();
        match cli.command {
            Command::CoverageReport {
                start,
                end,
                allow_large_window,
                dry_run,
                report_only,
            } => {
                assert_eq!(start, "2026-04-24T16:00:00Z");
                assert!(end.is_none());
                assert!(!allow_large_window);
                assert!(!dry_run);
                assert!(report_only);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_last_24h_coverage_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "coverage-last-24h",
            "--report-only",
        ])
        .unwrap();
        match cli.command {
            Command::CoverageLast24h {
                dry_run,
                report_only,
            } => {
                assert!(!dry_run);
                assert!(report_only);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_catch_up_now_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "catch-up-now",
        ])
        .unwrap();
        match cli.command {
            Command::CatchUpNow => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_server_start_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "./config.example.toml",
            "server-start",
            "--dry-run",
            "--status-timeout-seconds",
            "15",
            "--log-file",
            "./state/start.log",
        ])
        .unwrap();
        match cli.command {
            Command::ServerStart {
                dry_run,
                status_timeout_seconds,
                log_file,
            } => {
                assert!(dry_run);
                assert_eq!(status_timeout_seconds, 15);
                assert_eq!(log_file, Some(PathBuf::from("./state/start.log")));
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_large_window_override_for_coverage_report() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.example.toml",
            "coverage-report",
            "--start",
            "2026-04-24T16:00:00Z",
            "--end",
            "2026-04-24T18:30:00Z",
            "--allow-large-window",
        ])
        .unwrap();
        match cli.command {
            Command::CoverageReport {
                allow_large_window, ..
            } => assert!(allow_large_window),
            other => panic!("unexpected command: {other:?}"),
        }
    }
}
