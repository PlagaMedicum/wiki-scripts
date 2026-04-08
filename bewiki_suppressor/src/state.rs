use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File};
use std::io::Write;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize, de::DeserializeOwned};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ProcessedRevidsState {
    pub capacity: usize,
    pub revids: Vec<u64>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct NightlySweepProgress {
    pub pages: BTreeMap<String, PageCheckpoint>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct RuntimeStatus {
    pub daemon_state: String,
    pub dry_run: bool,
    pub last_notice: Option<String>,
    pub last_notice_at: Option<DateTime<Utc>>,
    pub reconciliation: ReconciliationRuntimeStatus,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ReconciliationRuntimeStatus {
    pub active: bool,
    pub mode: Option<String>,
    pub phase: Option<String>,
    pub queued_mode: Option<String>,
    pub total_titles: usize,
    pub completed_titles: usize,
    pub phase_total: usize,
    pub phase_completed: usize,
    pub current_title: Option<String>,
    pub last_started_at: Option<DateTime<Utc>>,
    pub last_completed_at: Option<DateTime<Utc>>,
    pub last_result: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PageCheckpoint {
    pub last_full_check_at: Option<DateTime<Utc>>,
    pub last_reconciled_at: Option<DateTime<Utc>>,
    pub last_reconciled_revision_timestamp: Option<DateTime<Utc>>,
    pub last_reconciled_revid: Option<u64>,
}

impl ProcessedRevidsState {
    pub fn contains(&self, revid: u64) -> bool {
        self.revids.contains(&revid)
    }

    pub fn insert(&mut self, revid: u64) {
        if self.contains(revid) {
            return;
        }
        let mut queue = VecDeque::from(self.revids.clone());
        queue.push_back(revid);
        while self.capacity > 0 && queue.len() > self.capacity {
            let _ = queue.pop_front();
        }
        self.revids = queue.into_iter().collect();
    }
}

pub fn load_json<T: DeserializeOwned>(path: &Path) -> Result<Option<T>> {
    if !path.exists() {
        return Ok(None);
    }
    let raw =
        fs::read_to_string(path).with_context(|| format!("Failed to read {}", path.display()))?;
    let value = serde_json::from_str(&raw)
        .with_context(|| format!("Failed to parse {}", path.display()))?;
    Ok(Some(value))
}

pub fn save_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let raw = serde_json::to_vec_pretty(value).context("Failed to serialize JSON state")?;
    save_bytes_atomic(path, &raw)
}

pub fn load_text(path: &Path) -> Result<Option<String>> {
    if !path.exists() {
        return Ok(None);
    }
    let raw =
        fs::read_to_string(path).with_context(|| format!("Failed to read {}", path.display()))?;
    Ok(Some(raw.trim().to_string()))
}

pub fn save_text_atomic(path: &Path, value: &str) -> Result<()> {
    save_bytes_atomic(path, value.as_bytes())
}

fn save_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create {}", parent.display()))?;
    }
    let tmp_path = path.with_extension("tmp");
    let mut file = File::create(&tmp_path)
        .with_context(|| format!("Failed to create {}", tmp_path.display()))?;
    file.write_all(bytes)
        .with_context(|| format!("Failed to write {}", tmp_path.display()))?;
    file.sync_all()
        .with_context(|| format!("Failed to flush {}", tmp_path.display()))?;
    fs::rename(&tmp_path, path)
        .with_context(|| format!("Failed to move {} into place", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;

    #[test]
    fn processed_revids_respects_capacity() {
        let mut state = ProcessedRevidsState {
            capacity: 3,
            revids: vec![],
        };
        state.insert(1);
        state.insert(2);
        state.insert(3);
        state.insert(4);
        assert_eq!(state.revids, vec![2, 3, 4]);
    }

    #[test]
    fn saves_and_loads_json_atomically() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("processed.json");
        let state = ProcessedRevidsState {
            capacity: 2,
            revids: vec![10, 20],
        };
        save_json_atomic(&path, &state).unwrap();
        let loaded: ProcessedRevidsState = load_json(&path).unwrap().unwrap();
        assert_eq!(loaded.revids, vec![10, 20]);
    }

    #[test]
    fn runtime_status_loads_with_missing_new_fields() {
        let raw = r#"{
          "daemon_state": "running",
          "dry_run": false,
          "last_notice": "received manual nightly reconciliation signal",
          "reconciliation": {
            "active": true,
            "mode": "nightly",
            "queued_mode": null,
            "total_titles": 1425,
            "completed_titles": 0,
            "current_title": null,
            "last_started_at": "2026-04-08T14:02:59Z",
            "last_completed_at": null,
            "last_result": null
          }
        }"#;

        let loaded: RuntimeStatus = serde_json::from_str(raw).unwrap();
        assert_eq!(loaded.daemon_state, "running");
        assert!(loaded.reconciliation.active);
        assert_eq!(loaded.reconciliation.mode.as_deref(), Some("nightly"));
        assert_eq!(loaded.reconciliation.total_titles, 1425);
        assert_eq!(loaded.reconciliation.completed_titles, 0);
        assert_eq!(loaded.reconciliation.phase_total, 0);
        assert_eq!(loaded.reconciliation.phase_completed, 0);
        assert_eq!(loaded.reconciliation.phase, None);
    }
}
