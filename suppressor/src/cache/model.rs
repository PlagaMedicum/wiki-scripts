use std::collections::{BTreeMap, BTreeSet, HashSet};

use anyhow::{Result, bail};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use tracing::warn;

use crate::mw_api::PageContent;
use suppressor_core::titles::{normalize_title, parse_source_list};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SuppressionListCache {
    pub source_title: String,
    pub source_pageid: Option<u64>,
    pub source_lastrevid: Option<u64>,
    pub source_last_timestamp: Option<DateTime<Utc>>,
    pub fetched_at: DateTime<Utc>,
    pub listed_titles_normalized: Vec<String>,
    pub watched_titles_normalized: Vec<String>,
    pub redirect_map: BTreeMap<String, String>,
    pub titles_hash_sha256: String,
}

#[derive(Clone, Debug)]
pub struct RuntimeCache {
    pub snapshot: SuppressionListCache,
    pub watched_set: HashSet<String>,
    pub source_title_normalized: String,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct WatchedTitleDiff {
    pub added: Vec<String>,
    pub removed: Vec<String>,
}

impl RuntimeCache {
    pub fn from_snapshot(snapshot: SuppressionListCache) -> Self {
        let watched_set = snapshot
            .watched_titles_normalized
            .iter()
            .cloned()
            .collect::<HashSet<_>>();
        let source_title_normalized = normalize_title(&snapshot.source_title);
        Self {
            snapshot,
            watched_set,
            source_title_normalized,
        }
    }

    pub fn replace_snapshot(&mut self, snapshot: SuppressionListCache) {
        *self = Self::from_snapshot(snapshot);
    }

    pub fn watched_titles(&self) -> &[String] {
        &self.snapshot.watched_titles_normalized
    }
}

impl SuppressionListCache {
    pub fn initial(source_title: &str) -> Self {
        Self {
            source_title: source_title.to_string(),
            source_pageid: None,
            source_lastrevid: None,
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: Vec::new(),
            watched_titles_normalized: Vec::new(),
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: String::new(),
        }
    }

    pub fn from_source_content(previous: &Self, content: PageContent) -> Result<Self> {
        let parsed = parse_source_list(&content.content);
        for warning in parsed.warnings {
            warn!("{}", warning);
        }
        if parsed.titles.is_empty() {
            bail!("Suppression list source page produced no valid titles");
        }
        let hash = compute_hash(&parsed.titles);
        let listed_changed = previous.titles_hash_sha256 != hash;
        let redirect_map = if listed_changed {
            BTreeMap::new()
        } else {
            previous.redirect_map.clone()
        };
        let watched_titles_normalized =
            if listed_changed || previous.watched_titles_normalized.is_empty() {
                parsed.titles.clone()
            } else {
                previous.watched_titles_normalized.clone()
            };
        Ok(Self {
            source_title: previous.source_title.clone(),
            source_pageid: content.metadata.pageid,
            source_lastrevid: content.metadata.lastrevid,
            source_last_timestamp: content.metadata.timestamp,
            fetched_at: Utc::now(),
            listed_titles_normalized: parsed.titles,
            watched_titles_normalized,
            redirect_map,
            titles_hash_sha256: hash,
        })
    }

    pub fn with_redirects(&self, discovered: BTreeMap<String, String>) -> Self {
        let mut watched = self
            .listed_titles_normalized
            .iter()
            .cloned()
            .collect::<HashSet<_>>();
        for (from, to) in &discovered {
            watched.insert(from.clone());
            watched.insert(to.clone());
        }
        let mut watched_titles_normalized = watched.into_iter().collect::<Vec<_>>();
        watched_titles_normalized.sort();
        Self {
            watched_titles_normalized,
            redirect_map: discovered,
            ..self.clone()
        }
    }

    pub fn watched_title_diff(&self, newer: &Self) -> WatchedTitleDiff {
        let old = self
            .watched_titles_normalized
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        let new = newer
            .watched_titles_normalized
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        WatchedTitleDiff {
            added: new.difference(&old).cloned().collect(),
            removed: old.difference(&new).cloned().collect(),
        }
    }
}

fn compute_hash(values: &[String]) -> String {
    use sha2::{Digest, Sha256};

    let mut hasher = Sha256::new();
    for value in values {
        hasher.update(value.as_bytes());
        hasher.update(b"\n");
    }
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mw_api::PageMetadata;

    #[test]
    fn runtime_cache_builds_watched_set() {
        let snapshot = SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string()],
            watched_titles_normalized: vec!["Foo".to_string(), "Bar".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "abc".to_string(),
        };
        let cache = RuntimeCache::from_snapshot(snapshot);
        assert!(cache.watched_set.contains("Foo"));
        assert!(cache.watched_set.contains("Bar"));
    }

    #[test]
    fn snapshot_resets_redirect_state_when_list_changes() {
        let previous = SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string()],
            watched_titles_normalized: vec!["Foo".to_string(), "Foo Redirect".to_string()],
            redirect_map: BTreeMap::from([("Foo".to_string(), "Foo Redirect".to_string())]),
            titles_hash_sha256: "old".to_string(),
        };
        let content = PageContent {
            metadata: PageMetadata {
                pageid: Some(1),
                lastrevid: Some(3),
                timestamp: None,
            },
            content: "Bar\n".to_string(),
        };

        let snapshot = SuppressionListCache::from_source_content(&previous, content).unwrap();

        assert_eq!(snapshot.listed_titles_normalized, vec!["Bar"]);
        assert_eq!(snapshot.watched_titles_normalized, vec!["Bar"]);
        assert!(snapshot.redirect_map.is_empty());
    }

    #[test]
    fn snapshot_preserves_redirect_state_when_list_is_unchanged() {
        let hash = compute_hash(&["Foo".to_string()]);
        let previous = SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string()],
            watched_titles_normalized: vec!["Foo".to_string(), "Foo Redirect".to_string()],
            redirect_map: BTreeMap::from([("Foo".to_string(), "Foo Redirect".to_string())]),
            titles_hash_sha256: hash,
        };
        let content = PageContent {
            metadata: PageMetadata {
                pageid: Some(1),
                lastrevid: Some(3),
                timestamp: None,
            },
            content: "Foo\n".to_string(),
        };

        let snapshot = SuppressionListCache::from_source_content(&previous, content).unwrap();

        assert_eq!(snapshot.listed_titles_normalized, vec!["Foo"]);
        assert_eq!(
            snapshot.watched_titles_normalized,
            vec!["Foo", "Foo Redirect"]
        );
        assert_eq!(
            snapshot.redirect_map,
            BTreeMap::from([("Foo".to_string(), "Foo Redirect".to_string())])
        );
    }

    #[test]
    fn applying_redirects_updates_watched_titles() {
        let snapshot = SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string()],
            watched_titles_normalized: vec!["Foo".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "abc".to_string(),
        };

        let updated = snapshot.with_redirects(BTreeMap::from([(
            "Foo".to_string(),
            "Foo Redirect".to_string(),
        )]));

        assert_eq!(
            updated.watched_titles_normalized,
            vec!["Foo".to_string(), "Foo Redirect".to_string()]
        );
        assert_eq!(
            updated.redirect_map,
            BTreeMap::from([("Foo".to_string(), "Foo Redirect".to_string())])
        );
    }

    #[test]
    fn watched_title_diff_reports_added_and_removed_titles() {
        let previous = SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string(), "Old".to_string()],
            watched_titles_normalized: vec!["Foo".to_string(), "Old".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "old".to_string(),
        };
        let newer = SuppressionListCache {
            listed_titles_normalized: vec!["Foo".to_string(), "New".to_string()],
            watched_titles_normalized: vec![
                "Foo".to_string(),
                "New".to_string(),
                "New Redirect".to_string(),
            ],
            titles_hash_sha256: "new".to_string(),
            ..previous.clone()
        };

        let diff = previous.watched_title_diff(&newer);

        assert_eq!(
            diff.added,
            vec!["New".to_string(), "New Redirect".to_string()]
        );
        assert_eq!(diff.removed, vec!["Old".to_string()]);
    }

    #[test]
    fn watched_title_diff_is_empty_for_unchanged_watched_set() {
        let snapshot = SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(2),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: vec!["Foo".to_string()],
            watched_titles_normalized: vec!["Foo".to_string(), "Foo Redirect".to_string()],
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: "hash".to_string(),
        };

        let diff = snapshot.watched_title_diff(&snapshot);

        assert!(diff.added.is_empty());
        assert!(diff.removed.is_empty());
    }
}
