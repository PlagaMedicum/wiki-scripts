use std::path::{Path, PathBuf};

use anyhow::Result;

use crate::config::{AppConfig, RuntimePaths, init_logging};

pub struct CommandContext {
    pub config: AppConfig,
    pub paths: RuntimePaths,
}

impl CommandContext {
    pub fn load(config_path: &Path) -> Result<Self> {
        let config_path: PathBuf = config_path.to_path_buf();
        let config = AppConfig::load(&config_path)?;
        let paths = RuntimePaths::resolve(&config_path, &config);
        Ok(Self { config, paths })
    }

    pub fn init_logging(&self, verbose: bool) {
        init_logging(&self.config.logging, verbose);
    }
}
