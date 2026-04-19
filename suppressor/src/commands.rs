use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result};
use tokio::sync::RwLock;
use tracing::info;

use crate::auth::{AuthState, authenticate, refresh_csrf_token};
use crate::config::{AppConfig, EnvConfig, RuntimePaths, init_logging, load_env};
use crate::effective_config::render_effective_config;
use crate::mw_api::MediaWikiClient;
use crate::signals;

pub struct CommandContext {
    pub config: AppConfig,
    pub paths: RuntimePaths,
}

impl CommandContext {
    pub fn load(config_path: &Path) -> Result<Self> {
        let config_path = config_path.to_path_buf();
        let config = AppConfig::load(&config_path)?;
        let paths = RuntimePaths::resolve(&config_path, &config);
        Ok(Self { config, paths })
    }

    pub fn init_logging(&self, verbose: bool) {
        init_logging(&self.config.logging, verbose);
    }
}

struct AuthenticatedCommandContext {
    command: CommandContext,
    env: EnvConfig,
    client: MediaWikiClient,
    auth: AuthState,
    auth_lock: Arc<RwLock<AuthState>>,
}

impl AuthenticatedCommandContext {
    async fn load(config_path: &Path, command_name: &str, verbose: bool) -> Result<Self> {
        let command = CommandContext::load(config_path)?;
        command.init_logging(verbose);
        info!(
            command = command_name,
            config_path = %command.paths.config_path.display(),
            "running command"
        );
        let env = load_env(&command.paths.config_path)?;
        let client = MediaWikiClient::new(&env)?;
        let auth = authenticate(&client, &env).await?;
        let auth_lock = Arc::new(RwLock::new(auth.clone()));
        Ok(Self {
            command,
            env,
            client,
            auth,
            auth_lock,
        })
    }
}

fn format_auth_status_lines(auth: &AuthState) -> Vec<String> {
    let mut rights = auth.rights.iter().cloned().collect::<Vec<_>>();
    rights.sort();
    vec![
        format!("auth.user={}", auth.username),
        format!("auth.bot={}", auth.has_bot_right()),
        format!("auth.rights={}", rights.join(",")),
    ]
}

fn format_hide_revid_result(revid: u64) -> String {
    format!("revdel.ok revid={revid}")
}

pub async fn run_check_auth(config_path: PathBuf, verbose: bool) -> Result<()> {
    let command = AuthenticatedCommandContext::load(&config_path, "check-auth", verbose).await?;
    for line in format_auth_status_lines(&command.auth) {
        println!("{line}");
    }
    Ok(())
}

pub async fn run_hide_revid(config_path: PathBuf, revid: u64, verbose: bool) -> Result<()> {
    let command = AuthenticatedCommandContext::load(&config_path, "hide-revid", verbose).await?;
    info!(revid, "hiding revision from command");
    revision_delete_with_auth_context(&command, &[revid]).await?;
    println!("{}", format_hide_revid_result(revid));
    Ok(())
}

pub fn run_reload_cache(config_path: PathBuf) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    signals::send_reload(&command.paths.pid_file)
}

pub fn run_manual_sweep(config_path: PathBuf) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    signals::send_manual_sweep(&command.paths.pid_file)
}

pub fn run_print_effective_config(config_path: PathBuf, verbose: bool) -> Result<()> {
    let command = CommandContext::load(&config_path)?;
    command.init_logging(verbose);
    info!(
        config_path = %command.paths.config_path.display(),
        "rendering effective config"
    );
    let env = load_env(&command.paths.config_path)?;
    println!(
        "{}",
        render_effective_config(&command.config, &env, &command.paths.config_path)?
    );
    Ok(())
}

async fn revision_delete_with_auth_context(
    command: &AuthenticatedCommandContext,
    revids: &[u64],
) -> Result<()> {
    let mut csrf = command.auth.csrf_token.clone();
    command
        .client
        .revision_delete_with_retry(
            revids,
            &command.command.config.revdel.reason,
            &mut csrf,
            &command.command.config.retry,
            {
                let client = command.client.clone();
                let env = command.env.clone();
                let auth_lock = Arc::clone(&command.auth_lock);
                move || {
                    let client = client.clone();
                    let env = env.clone();
                    let auth_lock = Arc::clone(&auth_lock);
                    async move {
                        let auth = authenticate(&client, &env)
                            .await
                            .context("re-login failed")?;
                        let csrf = auth.csrf_token.clone();
                        *auth_lock.write().await = auth;
                        Ok(csrf)
                    }
                }
            },
            {
                let client = command.client.clone();
                let auth_lock = Arc::clone(&command.auth_lock);
                move || {
                    let client = client.clone();
                    let auth_lock = Arc::clone(&auth_lock);
                    async move {
                        let csrf = refresh_csrf_token(&client)
                            .await
                            .context("CSRF refresh failed")?;
                        auth_lock.write().await.csrf_token = csrf.clone();
                        Ok(csrf)
                    }
                }
            },
        )
        .await
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::*;
    use crate::auth::AuthState;

    #[test]
    fn command_context_resolves_pid_path() {
        let temp = tempfile::tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();

        let command = CommandContext::load(config_path.as_path()).unwrap();
        assert_eq!(
            command.paths.pid_file,
            temp.path().join("./state/daemon.pid")
        );
    }

    #[test]
    fn formats_compact_auth_status_lines() {
        let auth = AuthState {
            username: "ExampleBot".to_string(),
            csrf_token: "token".to_string(),
            rights: HashSet::from(["bot".to_string(), "edit".to_string()]),
        };

        assert_eq!(
            format_auth_status_lines(&auth),
            vec![
                "auth.user=ExampleBot".to_string(),
                "auth.bot=true".to_string(),
                "auth.rights=bot,edit".to_string(),
            ]
        );
    }

    #[test]
    fn formats_compact_hide_revid_result() {
        assert_eq!(format_hide_revid_result(42), "revdel.ok revid=42");
    }
}
