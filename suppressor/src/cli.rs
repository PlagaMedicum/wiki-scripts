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
    EmergencyCatchup {
        #[arg(long)]
        start: Option<String>,
        #[arg(long)]
        end: Option<String>,
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
        dry_run: bool,
        #[arg(long)]
        report_only: bool,
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
                dry_run,
                report_only,
            } => {
                assert_eq!(start.as_deref(), Some("2026-04-24T16:00:00Z"));
                assert_eq!(end.as_deref(), Some("2026-04-24T16:30:00Z"));
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
                dry_run,
                report_only,
            } => {
                assert_eq!(start, "2026-04-24T16:00:00Z");
                assert!(end.is_none());
                assert!(!dry_run);
                assert!(report_only);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }
}
