use std::path::Path;

use anyhow::{Context, Result};
use serde::Serialize;

use crate::config::{AppConfig, EnvConfig};

#[derive(Debug, Serialize)]
struct EffectiveConfigView<'a> {
    config_path: String,
    env_file: String,
    config: &'a AppConfig,
    env: RedactedEnv<'a>,
}

#[derive(Debug, Serialize)]
struct RedactedEnv<'a> {
    api_url: &'a str,
    stream_url: &'a str,
    bot_username: &'a str,
    bot_password: &'static str,
    user_agent: &'a str,
}

pub(crate) fn render_effective_config(
    config: &AppConfig,
    env: &EnvConfig,
    config_path: &Path,
) -> Result<String> {
    let view = EffectiveConfigView {
        config_path: config_path.display().to_string(),
        env_file: env.env_file.display().to_string(),
        config,
        env: RedactedEnv {
            api_url: &env.api_url,
            stream_url: &env.stream_url,
            bot_username: &env.bot_username,
            bot_password: "REDACTED",
            user_agent: &env.user_agent,
        },
    };
    serde_json::to_string_pretty(&view).context("Failed to render effective config")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn effective_config_redacts_password() {
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let env = EnvConfig {
            api_url: "https://example.invalid/w/api.php".to_string(),
            stream_url: "https://stream.example.invalid/recentchange".to_string(),
            bot_username: "Bot@tool".to_string(),
            bot_password: "secret".to_string(),
            user_agent: "test-agent".to_string(),
            env_file: PathBuf::from("/tmp/.env"),
        };
        let rendered =
            render_effective_config(&config, &env, Path::new("/tmp/config.toml")).unwrap();
        assert!(rendered.contains("\"bot_password\": \"REDACTED\""));
        assert!(!rendered.contains("secret"));
    }
}
