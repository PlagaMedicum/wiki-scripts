use anyhow::Result;
use clap::Parser;

use crate::cli::{Cli, Command};
use crate::commands::{
    run_check_auth, run_hide_revid, run_manual_sweep, run_print_effective_config, run_reload_cache,
};
use crate::coverage_command::{run_coverage_last_24h, run_coverage_report, run_emergency_catchup};
use crate::daemon::run_daemon;
use crate::server_start::{run_server_start, run_supervisor};
use crate::status_command::{run_health, run_last_edits, run_perf, run_status};

pub async fn run() -> Result<()> {
    let cli = Cli::parse();
    let config = cli.required_config()?;
    match cli.command {
        Command::Run => run_daemon(config, false, cli.verbose).await,
        Command::Status { json } => run_status(config, json),
        Command::Health { json } => {
            let exit_code = run_health(config, json)?;
            if exit_code != 0 {
                std::process::exit(exit_code);
            }
            Ok(())
        }
        Command::LastEdits { limit, json } => run_last_edits(config, limit, json).await,
        Command::Perf { json } => run_perf(config, json),
        Command::DryRun => run_daemon(config, true, cli.verbose).await,
        Command::CheckAuth => run_check_auth(config, cli.verbose).await,
        Command::HideRevid { id } => run_hide_revid(config, id, cli.verbose).await,
        Command::SmokeTest { page } => {
            crate::daemon::run_smoke_test(config, page, cli.verbose).await
        }
        Command::EmergencyCatchup {
            start,
            end,
            allow_large_window,
            dry_run,
            report_only,
        } => {
            run_emergency_catchup(
                config,
                start,
                end,
                allow_large_window,
                dry_run,
                report_only,
                cli.verbose,
            )
            .await
        }
        Command::CoverageReport {
            start,
            end,
            allow_large_window,
            dry_run,
            report_only,
        } => {
            run_coverage_report(
                config,
                start,
                end,
                allow_large_window,
                dry_run,
                report_only,
                cli.verbose,
            )
            .await
        }
        Command::CoverageLast24h {
            dry_run,
            report_only,
        } => run_coverage_last_24h(config, dry_run, report_only, cli.verbose).await,
        Command::ServerStart {
            dry_run,
            status_timeout_seconds,
            log_file,
        } => run_server_start(
            config,
            dry_run,
            status_timeout_seconds,
            log_file,
            cli.verbose,
        ),
        Command::SupervisorRun { dry_run, log_file } => {
            run_supervisor(config, dry_run, log_file, cli.verbose)
        }
        Command::ReloadCache => run_reload_cache(config),
        Command::CatchUpNow => run_manual_sweep(config, "catch-up-now"),
        Command::NightlySweepNow => run_manual_sweep(config, "nightly-sweep-now"),
        Command::PrintEffectiveConfig => run_print_effective_config(config, cli.verbose),
    }
}
