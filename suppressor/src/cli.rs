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
    HideRevid { id: u64 },
    NightlySweepNow,
    PrintEffectiveConfig,
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    #[test]
    fn parses_hide_revid_command() {
        let cli =
            Cli::try_parse_from(["suppressor", "--config", "config.toml", "hide-revid", "42"])
                .unwrap();
        assert_eq!(cli.config, PathBuf::from("config.toml"));
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
}
