use std::path::PathBuf;

use crate::cache::SuppressionListCache;
use crate::config::RuntimePaths;
use crate::state::{
    NightlySweepProgress, ProcessedRevidsState, RuntimeStatus, load_json, load_text,
};

#[derive(Clone, Debug, Default)]
pub(crate) struct StatusSnapshot {
    pub daemon_pid: Option<i32>,
    pub daemon_running: bool,
    pub managed_session: Option<String>,
    pub env_file: PathBuf,
    pub pid_file: PathBuf,
    pub last_event_id: Option<String>,
    pub source_title: Option<String>,
    pub listed_titles: usize,
    pub watched_titles: usize,
    pub processed_revids: usize,
    pub checkpoint_pages: usize,
    pub runtime_status: Option<RuntimeStatus>,
    pub status_error: Option<String>,
}

pub(crate) fn collect_status(
    paths: &RuntimePaths,
    managed_session: Option<&str>,
) -> StatusSnapshot {
    let mut snapshot = StatusSnapshot {
        env_file: paths.env_file.clone(),
        pid_file: paths.pid_file.clone(),
        managed_session: managed_session.map(str::to_string),
        ..StatusSnapshot::default()
    };

    match load_text(&paths.pid_file) {
        Ok(Some(raw)) => match raw.parse::<i32>() {
            Ok(pid) if pid > 0 => {
                snapshot.daemon_pid = Some(pid);
                snapshot.daemon_running = PathBuf::from(format!("/proc/{pid}")).exists();
            }
            Ok(_) => {
                snapshot.status_error = Some("PID file contains a non-positive pid.".to_string())
            }
            Err(error) => {
                snapshot.status_error = Some(format!("Invalid pid file contents: {error}"));
            }
        },
        Ok(None) => {}
        Err(error) => snapshot.status_error = Some(format!("Unable to read pid file: {error:#}")),
    }

    if let Ok(last_event_id) = load_text(&paths.last_event_id_file) {
        snapshot.last_event_id = last_event_id;
    }

    match load_json::<ProcessedRevidsState>(&paths.processed_revids_file) {
        Ok(Some(state)) => snapshot.processed_revids = state.revids.len(),
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(format!("Unable to read processed revisions: {error:#}"))
        }
    }

    match load_json::<SuppressionListCache>(&paths.cache_file) {
        Ok(Some(cache)) => {
            snapshot.source_title = Some(cache.source_title);
            snapshot.listed_titles = cache.listed_titles_normalized.len();
            snapshot.watched_titles = cache.watched_titles_normalized.len();
        }
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(format!("Unable to read cache snapshot: {error:#}"))
        }
    }

    match load_json::<NightlySweepProgress>(&paths.nightly_sweep_progress_file) {
        Ok(Some(progress)) => snapshot.checkpoint_pages = progress.pages.len(),
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(format!("Unable to read checkpoint state: {error:#}"))
        }
    }

    match load_json::<RuntimeStatus>(&paths.runtime_status_file) {
        Ok(Some(runtime_status)) => snapshot.runtime_status = Some(runtime_status),
        Ok(None) => {}
        Err(error) => {
            snapshot.status_error = Some(format!("Unable to read runtime status: {error:#}"))
        }
    }

    snapshot
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use chrono::Utc;
    use tempfile::tempdir;

    use super::*;
    use crate::config::{AppConfig, RuntimePaths};
    use crate::state::{
        PageCheckpoint, ReconciliationRuntimeStatus, RuntimeStatus, save_json_atomic,
        save_text_atomic,
    };

    #[test]
    fn collect_status_reads_supervisor_files() {
        let temp = tempdir().unwrap();
        let config_path = temp.path().join("config.toml");
        std::fs::write(&config_path, include_str!("../config.toml")).unwrap();
        let config: AppConfig = toml::from_str(include_str!("../config.toml")).unwrap();
        let paths = RuntimePaths::resolve(&config_path, &config);

        save_text_atomic(&paths.pid_file, &std::process::id().to_string()).unwrap();
        save_text_atomic(&paths.last_event_id_file, "evt-1").unwrap();
        save_json_atomic(
            &paths.processed_revids_file,
            &ProcessedRevidsState {
                capacity: 10,
                revids: vec![1, 2, 3],
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.cache_file,
            &SuppressionListCache {
                source_title: "Source".to_string(),
                source_pageid: Some(1),
                source_lastrevid: Some(2),
                source_last_timestamp: Some(Utc::now()),
                fetched_at: Utc::now(),
                listed_titles_normalized: vec!["a".to_string(), "b".to_string()],
                watched_titles_normalized: vec!["a".to_string(), "b".to_string(), "c".to_string()],
                redirect_map: BTreeMap::new(),
                titles_hash_sha256: "hash".to_string(),
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.nightly_sweep_progress_file,
            &NightlySweepProgress {
                pages: BTreeMap::from([("Page".to_string(), PageCheckpoint::default())]),
            },
        )
        .unwrap();
        save_json_atomic(
            &paths.runtime_status_file,
            &RuntimeStatus {
                daemon_state: "running".to_string(),
                dry_run: false,
                last_notice: Some("ok".to_string()),
                last_notice_at: Some(Utc::now()),
                reconciliation: ReconciliationRuntimeStatus::default(),
            },
        )
        .unwrap();

        let snapshot = collect_status(&paths, Some("daemon"));

        assert_eq!(snapshot.managed_session.as_deref(), Some("daemon"));
        assert!(snapshot.daemon_running);
        assert_eq!(snapshot.last_event_id.as_deref(), Some("evt-1"));
        assert_eq!(snapshot.processed_revids, 3);
        assert_eq!(snapshot.listed_titles, 2);
        assert_eq!(snapshot.watched_titles, 3);
        assert_eq!(snapshot.checkpoint_pages, 1);
        assert_eq!(
            snapshot
                .runtime_status
                .as_ref()
                .map(|status| status.daemon_state.as_str()),
            Some("running")
        );
    }
}
