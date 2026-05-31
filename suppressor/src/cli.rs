use std::path::PathBuf;

use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(
    name = "suppressor",
    version,
    about = "public revision-delete daemon first developed for be.wiki"
)]
pub struct Cli {
    #[arg(long, global = true, default_value = "config.toml")]
    pub config: PathBuf,
    #[arg(long, global = true)]
    pub verbose: bool,
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    Run,
    Tui,
    CheckAuth,
    ReloadCache,
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

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    #[test]
    fn parses_hide_revid_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "config.toml",
            "--verbose",
            "hide-revid",
            "42",
        ])
        .unwrap();
        assert_eq!(cli.config, PathBuf::from("config.toml"));
        assert!(cli.verbose);
        match cli.command {
            Command::HideRevid { id } => assert_eq!(id, 42),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_smoke_test_command() {
        let cli =
            Cli::try_parse_from(["suppressor", "smoke-test", "--page", "User:Bot/Test"]).unwrap();
        match cli.command {
            Command::SmokeTest { page } => assert_eq!(page.as_deref(), Some("User:Bot/Test")),
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_config_after_subcommand() {
        let cli =
            Cli::try_parse_from(["suppressor", "dry-run", "--config", "config.toml"]).unwrap();
        assert_eq!(cli.config, PathBuf::from("config.toml"));
        match cli.command {
            Command::DryRun => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_tui_command() {
        let cli = Cli::try_parse_from(["suppressor", "tui"]).unwrap();
        match cli.command {
            Command::Tui => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parses_emergency_catchup_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
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
        let cli =
            Cli::try_parse_from(["suppressor", "coverage-last-24h", "--report-only"]).unwrap();
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
    fn parses_server_start_command() {
        let cli = Cli::try_parse_from([
            "suppressor",
            "--config",
            "./config.toml",
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
