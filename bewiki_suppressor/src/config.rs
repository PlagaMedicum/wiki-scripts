use std::fs;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use tracing_subscriber::EnvFilter;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AppConfig {
    pub wiki: WikiConfig,
    pub auth: AuthConfig,
    pub suppression_list: SuppressionListConfig,
    pub matching: MatchingConfig,
    pub revdel: RevDelConfig,
    pub queue: QueueConfig,
    pub state: StateConfig,
    pub retry: RetryConfig,
    pub nightly_sweep: NightlySweepConfig,
    pub current_day_recheck: CurrentDayRecheckConfig,
    pub logging: LoggingConfig,
    pub metrics: MetricsConfig,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct WikiConfig {
    pub api_url: String,
    pub stream_url: String,
    pub wiki_code: String,
    pub server_name: String,
    pub user_agent: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AuthConfig {
    pub username_env: String,
    pub password_env: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SuppressionListConfig {
    pub title: String,
    pub cache_file: String,
    pub metadata_recheck_seconds: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct MatchingConfig {
    pub drop_canary: bool,
    pub exact_title_match: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RevDelConfig {
    pub hide: Vec<String>,
    pub suppress: bool,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct QueueConfig {
    pub capacity: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct StateConfig {
    pub dir: String,
    pub last_event_id_file: String,
    pub processed_revids_file: String,
    pub nightly_sweep_progress_file: String,
    pub runtime_status_file: String,
    pub pid_file: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RetryConfig {
    pub stream_backoff_initial_ms: u64,
    pub stream_backoff_max_ms: u64,
    pub api_max_retries: u32,
    pub since_recovery_seconds: i64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct NightlySweepConfig {
    pub enabled: bool,
    pub timezone: String,
    pub start_time: String,
    pub page_concurrency: usize,
    pub batch_sleep_ms: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CurrentDayRecheckConfig {
    pub enabled: bool,
    pub min_delay_seconds: u64,
    pub max_delay_seconds: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct LoggingConfig {
    pub level: String,
    pub format: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct MetricsConfig {
    pub enabled: bool,
    pub bind: String,
}

#[derive(Clone, Debug)]
pub struct EnvConfig {
    pub api_url: String,
    pub stream_url: String,
    pub bot_username: String,
    pub bot_password: String,
    pub user_agent: String,
    pub env_file: PathBuf,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuntimePaths {
    pub config_path: PathBuf,
    pub state_dir: PathBuf,
    pub env_file: PathBuf,
    pub cache_file: PathBuf,
    pub last_event_id_file: PathBuf,
    pub processed_revids_file: PathBuf,
    pub nightly_sweep_progress_file: PathBuf,
    pub runtime_status_file: PathBuf,
    pub pid_file: PathBuf,
}

static LOGGING_INIT: OnceLock<()> = OnceLock::new();
const DEFAULT_API_URL_ENV: &str = "BEWIKI_API_URL";
const DEFAULT_STREAM_URL_ENV: &str = "BEWIKI_STREAM_URL";
const DEFAULT_USER_AGENT_ENV: &str = "BEWIKI_USER_AGENT";

impl AppConfig {
    pub fn load(path: &Path) -> Result<Self> {
        let raw = fs::read_to_string(path)
            .with_context(|| format!("Failed to read config file {}", path.display()))?;
        let config: AppConfig = toml::from_str(&raw)
            .with_context(|| format!("Failed to parse config file {}", path.display()))?;
        if config.queue.capacity == 0 {
            bail!("queue.capacity must be greater than zero");
        }
        if config.current_day_recheck.min_delay_seconds
            > config.current_day_recheck.max_delay_seconds
        {
            bail!("current_day_recheck min_delay_seconds must be <= max_delay_seconds");
        }
        Ok(config)
    }

    pub fn resolve_path(config_path: &Path, value: &str) -> PathBuf {
        let base = config_path.parent().unwrap_or_else(|| Path::new("."));
        let path = PathBuf::from(value);
        if path.is_absolute() {
            path
        } else {
            base.join(path)
        }
    }

    pub fn state_dir(&self, config_path: &Path) -> PathBuf {
        Self::resolve_path(config_path, &self.state.dir)
    }
}

impl RuntimePaths {
    pub fn resolve(config_path: &Path, config: &AppConfig) -> Self {
        let config_path = config_path.to_path_buf();
        Self {
            state_dir: config.state_dir(&config_path),
            env_file: resolve_env_file(&config_path),
            cache_file: AppConfig::resolve_path(&config_path, &config.suppression_list.cache_file),
            last_event_id_file: AppConfig::resolve_path(
                &config_path,
                &config.state.last_event_id_file,
            ),
            processed_revids_file: AppConfig::resolve_path(
                &config_path,
                &config.state.processed_revids_file,
            ),
            nightly_sweep_progress_file: AppConfig::resolve_path(
                &config_path,
                &config.state.nightly_sweep_progress_file,
            ),
            runtime_status_file: AppConfig::resolve_path(
                &config_path,
                &config.state.runtime_status_file,
            ),
            pid_file: AppConfig::resolve_path(&config_path, &config.state.pid_file),
            config_path,
        }
    }
}

pub fn load_env(config_path: &Path) -> Result<EnvConfig> {
    let config = AppConfig::load(config_path)?;
    let env_file = resolve_env_file(config_path);
    let file_values = if env_file.exists() {
        parse_env_file(&env_file)?
    } else {
        Vec::new()
    };

    let mut missing = Vec::new();
    let api_url = resolve_env_value(DEFAULT_API_URL_ENV, &file_values)
        .unwrap_or_else(|| config.wiki.api_url.clone());
    let stream_url = resolve_env_value(DEFAULT_STREAM_URL_ENV, &file_values)
        .unwrap_or_else(|| config.wiki.stream_url.clone());
    let bot_username =
        resolve_env_value(&config.auth.username_env, &file_values).unwrap_or_else(|| {
            missing.push(config.auth.username_env.clone());
            String::new()
        });
    let bot_password =
        resolve_env_value(&config.auth.password_env, &file_values).unwrap_or_else(|| {
            missing.push(config.auth.password_env.clone());
            String::new()
        });
    let user_agent = resolve_env_value(DEFAULT_USER_AGENT_ENV, &file_values)
        .unwrap_or_else(|| config.wiki.user_agent.clone());

    if !missing.is_empty() {
        bail!(
            "Missing required auth env values (from process env or .env): {}",
            missing.join(", ")
        );
    }

    Ok(EnvConfig {
        api_url,
        stream_url,
        bot_username,
        bot_password,
        user_agent,
        env_file,
    })
}

pub fn resolve_env_file(config_path: &Path) -> PathBuf {
    let base = config_path.parent().unwrap_or_else(|| Path::new("."));
    std::env::var("BEWIKI_ENV_FILE")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join(".env"))
}

fn parse_env_file(path: &Path) -> Result<Vec<(String, String)>> {
    let raw =
        fs::read_to_string(path).with_context(|| format!("Failed to load {}", path.display()))?;
    let mut values = Vec::new();
    for (index, raw_line) in raw.lines().enumerate() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            bail!("Invalid .env line {} in {}", index + 1, path.display());
        };
        let parsed = if value.len() >= 2
            && ((value.starts_with('"') && value.ends_with('"'))
                || (value.starts_with('\'') && value.ends_with('\'')))
        {
            value[1..value.len() - 1].to_string()
        } else {
            value.trim().to_string()
        };
        values.push((key.trim().to_string(), parsed));
    }
    Ok(values)
}

fn resolve_env_value(name: &str, file_values: &[(String, String)]) -> Option<String> {
    std::env::var(name).ok().or_else(|| {
        file_values
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, value)| value.clone())
    })
}

pub fn init_logging(config: &LoggingConfig) {
    LOGGING_INIT.get_or_init(|| {
        let filter = EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| EnvFilter::new(config.level.clone()));
        let format = std::env::var("BEWIKI_LOG_FORMAT").unwrap_or_else(|_| config.format.clone());
        if format.eq_ignore_ascii_case("json") {
            let subscriber = tracing_subscriber::fmt()
                .with_env_filter(filter)
                .json()
                .with_current_span(false)
                .with_span_list(false)
                .finish();
            let _ = tracing::subscriber::set_global_default(subscriber);
        } else if format.eq_ignore_ascii_case("tui") {
            let subscriber = tracing_subscriber::fmt()
                .with_env_filter(filter)
                .compact()
                .with_target(false)
                .with_ansi(false)
                .finish();
            let _ = tracing::subscriber::set_global_default(subscriber);
        } else if format.eq_ignore_ascii_case("pretty") {
            let subscriber = tracing_subscriber::fmt()
                .with_env_filter(filter)
                .pretty()
                .finish();
            let _ = tracing::subscriber::set_global_default(subscriber);
        } else {
            let subscriber = tracing_subscriber::fmt()
                .with_env_filter(filter)
                .compact()
                .with_target(true)
                .finish();
            let _ = tracing::subscriber::set_global_default(subscriber);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsString;
    use std::sync::{Mutex, OnceLock};

    static ENV_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

    struct EnvGuard {
        saved: Vec<(String, Option<OsString>)>,
    }

    impl Drop for EnvGuard {
        fn drop(&mut self) {
            for (key, value) in self.saved.iter().rev() {
                match value {
                    Some(value) => {
                        // Tests serialize env mutation behind a mutex.
                        unsafe { std::env::set_var(key, value) }
                    }
                    None => {
                        // Tests serialize env mutation behind a mutex.
                        unsafe { std::env::remove_var(key) }
                    }
                }
            }
        }
    }

    fn set_env_vars(vars: &[(&str, Option<&str>)]) -> EnvGuard {
        let mut saved = Vec::with_capacity(vars.len());
        for (key, value) in vars {
            saved.push(((*key).to_string(), std::env::var_os(key)));
            match value {
                Some(value) => {
                    // Tests serialize env mutation behind a mutex.
                    unsafe { std::env::set_var(key, value) }
                }
                None => {
                    // Tests serialize env mutation behind a mutex.
                    unsafe { std::env::remove_var(key) }
                }
            }
        }
        EnvGuard { saved }
    }

    fn with_env_vars<T>(vars: &[(&str, Option<&str>)], f: impl FnOnce() -> T) -> T {
        let _lock = ENV_LOCK.get_or_init(|| Mutex::new(())).lock().unwrap();
        let _guard = set_env_vars(vars);
        f()
    }

    #[test]
    fn resolves_relative_paths_from_config_dir() {
        let config_path = PathBuf::from("/tmp/bewiki_suppressor/config.toml");
        let resolved = AppConfig::resolve_path(&config_path, "./state/file.json");
        assert_eq!(
            resolved,
            PathBuf::from("/tmp/bewiki_suppressor/./state/file.json")
        );
    }

    #[test]
    fn loads_env_uses_config_defaults_and_configured_auth_env_names() {
        let temp = tempfile::tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        let env_path = temp.path().join(".env");
        let config = include_str!("../config.toml")
            .replace("BEWIKI_BOT_USERNAME", "TEST_BOT_USERNAME")
            .replace("BEWIKI_BOT_PASSWORD", "TEST_BOT_PASSWORD");
        fs::write(&config_path, config).unwrap();
        fs::write(
            &env_path,
            concat!(
                "TEST_BOT_USERNAME=Bot@password\n",
                "TEST_BOT_PASSWORD=secret\n",
            ),
        )
        .unwrap();

        with_env_vars(
            &[
                (DEFAULT_API_URL_ENV, None),
                (DEFAULT_STREAM_URL_ENV, None),
                (DEFAULT_USER_AGENT_ENV, None),
                ("TEST_BOT_USERNAME", None),
                ("TEST_BOT_PASSWORD", None),
                ("BEWIKI_ENV_FILE", None),
            ],
            || {
                let loaded = load_env(&config_path).unwrap();
                assert_eq!(loaded.api_url, "https://be.wikipedia.org/w/api.php");
                assert_eq!(
                    loaded.stream_url,
                    "https://stream.wikimedia.org/v2/stream/recentchange"
                );
                assert_eq!(
                    loaded.user_agent,
                    "bewiki-revdel-daemon/1.0 (contact on-wiki)"
                );
                assert_eq!(loaded.bot_username, "Bot@password");
                assert_eq!(loaded.bot_password, "secret");
            },
        );
    }

    #[test]
    fn loads_env_prefers_process_env_then_dotenv_over_config_defaults() {
        let temp = tempfile::tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        let env_path = temp.path().join(".env");
        let config = include_str!("../config.toml")
            .replace("BEWIKI_BOT_USERNAME", "TEST_BOT_USERNAME")
            .replace("BEWIKI_BOT_PASSWORD", "TEST_BOT_PASSWORD");
        fs::write(&config_path, config).unwrap();
        fs::write(
            &env_path,
            concat!(
                "BEWIKI_API_URL=https://dotenv.example/w/api.php\n",
                "BEWIKI_STREAM_URL=https://dotenv.example/stream\n",
                "BEWIKI_USER_AGENT=bewiki-revdel-daemon/1.0 (from-dotenv)\n",
                "TEST_BOT_USERNAME=Bot@dotenv\n",
                "TEST_BOT_PASSWORD=dotenv-secret\n",
            ),
        )
        .unwrap();

        with_env_vars(
            &[
                (
                    DEFAULT_API_URL_ENV,
                    Some("https://process.example/w/api.php"),
                ),
                (DEFAULT_STREAM_URL_ENV, None),
                (
                    DEFAULT_USER_AGENT_ENV,
                    Some("bewiki-revdel-daemon/1.0 (from-process)"),
                ),
                ("TEST_BOT_USERNAME", None),
                ("TEST_BOT_PASSWORD", None),
                ("BEWIKI_ENV_FILE", None),
            ],
            || {
                let loaded = load_env(&config_path).unwrap();
                assert_eq!(loaded.api_url, "https://process.example/w/api.php");
                assert_eq!(loaded.stream_url, "https://dotenv.example/stream");
                assert_eq!(loaded.user_agent, "bewiki-revdel-daemon/1.0 (from-process)");
                assert_eq!(loaded.bot_username, "Bot@dotenv");
                assert_eq!(loaded.bot_password, "dotenv-secret");
            },
        );
    }

    #[test]
    fn loads_env_without_dotenv_when_process_env_supplies_auth() {
        let temp = tempfile::tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        let config = include_str!("../config.toml")
            .replace("BEWIKI_BOT_USERNAME", "TEST_BOT_USERNAME")
            .replace("BEWIKI_BOT_PASSWORD", "TEST_BOT_PASSWORD");
        fs::write(&config_path, config).unwrap();

        with_env_vars(
            &[
                (DEFAULT_API_URL_ENV, None),
                (DEFAULT_STREAM_URL_ENV, None),
                (DEFAULT_USER_AGENT_ENV, None),
                ("TEST_BOT_USERNAME", Some("Bot@process")),
                ("TEST_BOT_PASSWORD", Some("process-secret")),
                ("BEWIKI_ENV_FILE", None),
            ],
            || {
                let loaded = load_env(&config_path).unwrap();
                assert_eq!(loaded.api_url, "https://be.wikipedia.org/w/api.php");
                assert_eq!(
                    loaded.stream_url,
                    "https://stream.wikimedia.org/v2/stream/recentchange"
                );
                assert_eq!(
                    loaded.user_agent,
                    "bewiki-revdel-daemon/1.0 (contact on-wiki)"
                );
                assert_eq!(loaded.bot_username, "Bot@process");
                assert_eq!(loaded.bot_password, "process-secret");
            },
        );
    }

    #[test]
    fn runtime_paths_resolve_from_config_once() {
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let config_path = Path::new("/tmp/bewiki_suppressor/config.toml");
        let paths = RuntimePaths::resolve(config_path, &config);

        assert_eq!(
            paths.config_path,
            PathBuf::from("/tmp/bewiki_suppressor/config.toml")
        );
        assert_eq!(
            paths.state_dir,
            PathBuf::from("/tmp/bewiki_suppressor/./state")
        );
        assert_eq!(paths.env_file, PathBuf::from("/tmp/bewiki_suppressor/.env"));
        assert_eq!(
            paths.cache_file,
            PathBuf::from("/tmp/bewiki_suppressor/./state/suppression_list_cache.json")
        );
        assert_eq!(
            paths.pid_file,
            PathBuf::from("/tmp/bewiki_suppressor/./state/daemon.pid")
        );
    }
}
