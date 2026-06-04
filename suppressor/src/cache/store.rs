use std::collections::BTreeMap;
use std::sync::Arc;

use anyhow::Result;
use tokio::sync::RwLock;

use crate::cache::{RuntimeCache, SuppressionListCache};
use crate::config::{AppConfig, RuntimePaths};
use crate::mw_api::MediaWikiClient;
use crate::state::{load_json, save_json_atomic};
use suppressor_core::page::PageMetadata;

use super::source::{fetch_bootstrap_snapshot, fetch_refreshed_snapshot, fetch_source_metadata};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CacheRefreshMode {
    Automatic,
    Forced,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CachePersistence {
    Persist,
    Ephemeral,
}

pub fn load_cached_snapshot(paths: &RuntimePaths) -> Result<Option<SuppressionListCache>> {
    load_json(&paths.cache_file)
}

pub async fn load_or_bootstrap(
    client: &MediaWikiClient,
    config: &AppConfig,
    paths: &RuntimePaths,
    persistence: CachePersistence,
) -> Result<RuntimeCache> {
    if let Some(cache) = load_cached_snapshot(paths)? {
        return Ok(RuntimeCache::from_snapshot(cache));
    }
    let snapshot = fetch_bootstrap_snapshot(client, config).await?;
    maybe_persist_snapshot(paths, &snapshot, persistence)?;
    Ok(RuntimeCache::from_snapshot(snapshot))
}

pub async fn refresh_cache(
    runtime_cache: &Arc<RwLock<RuntimeCache>>,
    client: &MediaWikiClient,
    config: &AppConfig,
    paths: &RuntimePaths,
    refresh_mode: CacheRefreshMode,
    persistence: CachePersistence,
) -> Result<bool> {
    let current = runtime_cache.read().await.snapshot.clone();
    let metadata = fetch_source_metadata(client, config).await?;
    let needs_refresh = should_refresh(&current, &metadata, refresh_mode);
    if !needs_refresh {
        return Ok(false);
    }

    let refreshed = fetch_refreshed_snapshot(client, config, &current).await?;
    maybe_persist_snapshot(paths, &refreshed, persistence)?;
    metrics::counter!("cache_reload_total").increment(1);
    let mut guard = runtime_cache.write().await;
    guard.replace_snapshot(refreshed);
    Ok(true)
}

pub async fn enrich_redirects(
    runtime_cache: &Arc<RwLock<RuntimeCache>>,
    paths: &RuntimePaths,
    discovered: BTreeMap<String, String>,
    persistence: CachePersistence,
) -> Result<()> {
    let mut guard = runtime_cache.write().await;
    let updated = guard.snapshot.with_redirects(discovered);
    maybe_persist_snapshot(paths, &updated, persistence)?;
    guard.replace_snapshot(updated);
    Ok(())
}

fn should_refresh(
    current: &SuppressionListCache,
    metadata: &PageMetadata,
    refresh_mode: CacheRefreshMode,
) -> bool {
    match refresh_mode {
        CacheRefreshMode::Forced => true,
        CacheRefreshMode::Automatic => {
            current.source_lastrevid.is_none()
                || current.source_lastrevid != metadata.lastrevid
                || current.source_last_timestamp != metadata.timestamp
        }
    }
}

fn persist_snapshot(paths: &RuntimePaths, snapshot: &SuppressionListCache) -> Result<()> {
    save_json_atomic(&paths.cache_file, snapshot)
}

fn maybe_persist_snapshot(
    paths: &RuntimePaths,
    snapshot: &SuppressionListCache,
    persistence: CachePersistence,
) -> Result<()> {
    if persistence.should_persist() {
        persist_snapshot(paths, snapshot)?;
    }
    Ok(())
}

impl CachePersistence {
    fn should_persist(self) -> bool {
        matches!(self, Self::Persist)
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use tempfile::tempdir;

    use super::*;
    use crate::cache::RuntimeCache;
    use crate::state::load_json;

    #[test]
    fn automatic_refresh_skips_when_metadata_matches() {
        let current = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: Some(chrono::Utc::now()),
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["A".to_string()],
            watched_titles_normalized: vec!["A".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };
        let metadata = PageMetadata {
            pageid: Some(1),
            lastrevid: Some(2),
            timestamp: current.source_last_timestamp,
        };

        assert!(!should_refresh(
            &current,
            &metadata,
            CacheRefreshMode::Automatic
        ));
        assert!(should_refresh(
            &current,
            &metadata,
            CacheRefreshMode::Forced
        ));
    }

    #[test]
    fn automatic_refresh_runs_when_revid_changes() {
        let current = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: Some(chrono::Utc::now()),
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["A".to_string()],
            watched_titles_normalized: vec!["A".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };
        let metadata = PageMetadata {
            pageid: Some(1),
            lastrevid: Some(3),
            timestamp: current.source_last_timestamp,
        };

        assert!(should_refresh(
            &current,
            &metadata,
            CacheRefreshMode::Automatic
        ));
    }

    #[test]
    fn automatic_refresh_runs_when_timestamp_changes() {
        let current_timestamp = chrono::Utc::now();
        let current = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: Some(current_timestamp),
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["A".to_string()],
            watched_titles_normalized: vec!["A".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };
        let metadata = PageMetadata {
            pageid: Some(1),
            lastrevid: Some(2),
            timestamp: Some(current_timestamp + chrono::Duration::seconds(1)),
        };

        assert!(should_refresh(
            &current,
            &metadata,
            CacheRefreshMode::Automatic
        ));
    }

    #[test]
    fn maybe_persist_snapshot_writes_cache_file_when_enabled() {
        let dir = tempdir().unwrap();
        let paths = RuntimePaths {
            config_path: dir.path().join("config.toml"),
            state_dir: dir.path().join("state"),
            env_file: dir.path().join(".env"),
            cache_file: dir.path().join("cache.json"),
            last_event_id_file: dir.path().join("last_event_id.txt"),
            processed_revids_file: dir.path().join("processed.json"),
            nightly_sweep_progress_file: dir.path().join("progress.json"),
            runtime_status_file: dir.path().join("status.json"),
            pid_file: dir.path().join("daemon.pid"),
        };
        let snapshot = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["A".to_string()],
            watched_titles_normalized: vec!["A".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };

        maybe_persist_snapshot(&paths, &snapshot, CachePersistence::Persist).unwrap();
        let saved: SuppressionListCache = load_json(&paths.cache_file).unwrap().unwrap();
        assert_eq!(saved.listed_titles_normalized, vec!["A"]);
    }

    #[test]
    fn maybe_persist_snapshot_skips_cache_file_when_ephemeral() {
        let dir = tempdir().unwrap();
        let paths = RuntimePaths {
            config_path: dir.path().join("config.toml"),
            state_dir: dir.path().join("state"),
            env_file: dir.path().join(".env"),
            cache_file: dir.path().join("cache.json"),
            last_event_id_file: dir.path().join("last_event_id.txt"),
            processed_revids_file: dir.path().join("processed.json"),
            nightly_sweep_progress_file: dir.path().join("progress.json"),
            runtime_status_file: dir.path().join("status.json"),
            pid_file: dir.path().join("daemon.pid"),
        };
        let snapshot = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["A".to_string()],
            watched_titles_normalized: vec!["A".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };

        maybe_persist_snapshot(&paths, &snapshot, CachePersistence::Ephemeral).unwrap();
        assert!(!paths.cache_file.exists());
    }

    #[tokio::test]
    async fn enrich_redirects_updates_memory_without_persisting_when_ephemeral() {
        let dir = tempdir().unwrap();
        let paths = RuntimePaths {
            config_path: dir.path().join("config.toml"),
            state_dir: dir.path().join("state"),
            env_file: dir.path().join(".env"),
            cache_file: dir.path().join("cache.json"),
            last_event_id_file: dir.path().join("last_event_id.txt"),
            processed_revids_file: dir.path().join("processed.json"),
            nightly_sweep_progress_file: dir.path().join("progress.json"),
            runtime_status_file: dir.path().join("status.json"),
            pid_file: dir.path().join("daemon.pid"),
        };
        let snapshot = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string()],
            watched_titles_normalized: vec!["Foo".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };
        let runtime_cache = Arc::new(RwLock::new(RuntimeCache::from_snapshot(snapshot)));

        enrich_redirects(
            &runtime_cache,
            &paths,
            BTreeMap::from([("Foo".to_string(), "Foo Redirect".to_string())]),
            CachePersistence::Ephemeral,
        )
        .await
        .unwrap();

        let cache = runtime_cache.read().await;
        assert!(cache.watched_set.contains("Foo"));
        assert!(cache.watched_set.contains("Foo Redirect"));
        assert!(!paths.cache_file.exists());
    }

    #[tokio::test]
    async fn load_or_bootstrap_uses_cached_snapshot_without_fetching() {
        let dir = tempdir().unwrap();
        let config_path = dir.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../../config.toml")).unwrap();
        let config = AppConfig::load(&config_path).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);
        let client = MediaWikiClient::new(&crate::config::EnvConfig {
            api_url: "https://example.invalid/api.php".to_string(),
            stream_url: "https://example.invalid/stream".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "secret".to_string(),
            user_agent: "bewiki-test/1.0".to_string(),
            env_file: dir.path().join(".env"),
        })
        .unwrap();
        let snapshot = SuppressionListCache {
            source_title: "List".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: chrono::Utc::now(),
            listed_titles_normalized: vec!["A".to_string()],
            watched_titles_normalized: vec!["A".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };

        maybe_persist_snapshot(&paths, &snapshot, CachePersistence::Persist).unwrap();

        let loaded = load_or_bootstrap(&client, &config, &paths, CachePersistence::Ephemeral)
            .await
            .unwrap();

        assert_eq!(loaded.snapshot.source_title, snapshot.source_title);
        assert_eq!(
            loaded.snapshot.listed_titles_normalized,
            snapshot.listed_titles_normalized
        );
    }
}
