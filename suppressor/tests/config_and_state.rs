use std::fs;

use suppressor::config::AppConfig;
use suppressor::state::{ProcessedRevidsState, load_json, save_json_atomic};
use tempfile::tempdir;

#[test]
fn loads_tracked_config() {
    let config = AppConfig::load(std::path::Path::new("config.toml")).unwrap();
    assert_eq!(config.wiki.wiki_code, "bewiki");
    assert_eq!(config.queue.capacity, 100);
}

#[test]
fn persists_processed_revid_state() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("processed_revids.json");
    let state = ProcessedRevidsState {
        capacity: 2,
        revids: vec![7, 9],
    };
    save_json_atomic(&path, &state).unwrap();
    let loaded: ProcessedRevidsState = load_json(&path).unwrap().unwrap();
    assert_eq!(loaded.revids, vec![7, 9]);
    fs::remove_file(path).unwrap();
}
