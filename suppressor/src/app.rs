use anyhow::Result;
use clap::Parser;

use crate::cli::{Cli, Command};
use crate::commands::{
    run_check_auth, run_hide_revid, run_manual_sweep, run_print_effective_config, run_reload_cache,
};
use crate::daemon::run_daemon;

pub async fn run() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Run => run_daemon(cli.config, false, cli.verbose).await,
        Command::Tui => crate::tui::run(cli.config, cli.verbose).await,
        Command::DryRun => run_daemon(cli.config, true, cli.verbose).await,
        Command::CheckAuth => run_check_auth(cli.config, cli.verbose).await,
        Command::HideRevid { id } => run_hide_revid(cli.config, id, cli.verbose).await,
        Command::ReloadCache => run_reload_cache(cli.config),
        Command::NightlySweepNow => run_manual_sweep(cli.config),
        Command::PrintEffectiveConfig => run_print_effective_config(cli.config, cli.verbose),
    }
}
