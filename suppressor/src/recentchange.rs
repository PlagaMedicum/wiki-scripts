use anyhow::{Context, Result};
use serde::Deserialize;

use crate::titles::normalize_title;

#[derive(Clone, Debug, Deserialize)]
pub struct RecentChangeEvent {
    #[serde(default)]
    pub meta: Option<Meta>,
    #[serde(default)]
    pub wiki: Option<String>,
    #[serde(default)]
    pub server_name: Option<String>,
    #[serde(rename = "type", default)]
    pub change_type: Option<String>,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub user: Option<String>,
    #[serde(default)]
    pub comment: Option<String>,
    #[serde(default)]
    pub revision: Option<RevisionPayload>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Meta {
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub domain: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RevisionPayload {
    #[serde(default)]
    pub old: Option<u64>,
    #[serde(default)]
    pub new: Option<u64>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LiveRevisionCandidate {
    pub title: String,
    pub normalized_title: String,
    pub revid: u64,
    pub old_revid: Option<u64>,
    pub user: Option<String>,
    pub comment: Option<String>,
    pub event_id: Option<String>,
}

impl RecentChangeEvent {
    pub fn parse(data: &str) -> Result<Self> {
        serde_json::from_str(data).context("Failed to decode recentchange event")
    }

    pub fn event_id(&self, sse_id: Option<&str>) -> Option<String> {
        sse_id
            .map(str::to_string)
            .or_else(|| self.meta.as_ref().and_then(|meta| meta.id.clone()))
    }

    pub fn is_canary(&self) -> bool {
        self.meta.as_ref().and_then(|meta| meta.domain.as_deref()) == Some("canary")
    }

    pub fn matches_wiki(&self, wiki_code: &str, server_name: &str) -> bool {
        self.wiki.as_deref() == Some(wiki_code) || self.server_name.as_deref() == Some(server_name)
    }

    pub fn is_revision_event(&self) -> bool {
        matches!(self.change_type.as_deref(), Some("edit") | Some("new"))
    }

    pub fn to_candidate(&self, sse_id: Option<&str>) -> Option<LiveRevisionCandidate> {
        let revid = self.revision.as_ref()?.new?;
        let title = self.title.clone()?;
        Some(LiveRevisionCandidate {
            normalized_title: normalize_title(&title),
            title,
            revid,
            old_revid: self.revision.as_ref().and_then(|revision| revision.old),
            user: self.user.clone(),
            comment: self.comment.clone(),
            event_id: self.event_id(sse_id),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_edit_event_with_revision_new() {
        let event = RecentChangeEvent::parse(
            r#"{"meta":{"domain":"be.wikipedia.org","id":"abc"},"wiki":"bewiki","server_name":"be.wikipedia.org","type":"edit","title":"Foo_bar","user":"Alice","comment":"Test","revision":{"old":1,"new":2}}"#,
        )
        .unwrap();
        let candidate = event.to_candidate(Some("stream-1")).unwrap();
        assert_eq!(candidate.revid, 2);
        assert_eq!(candidate.normalized_title, "Foo bar");
        assert_eq!(candidate.event_id.as_deref(), Some("stream-1"));
    }

    #[test]
    fn rejects_missing_revision_new() {
        let event = RecentChangeEvent::parse(
            r#"{"meta":{"domain":"be.wikipedia.org"},"wiki":"bewiki","type":"edit","title":"Foo","revision":{"old":1}}"#,
        )
        .unwrap();
        assert!(event.to_candidate(None).is_none());
    }

    #[test]
    fn rejects_canary_and_non_matching_wikis() {
        let canary = RecentChangeEvent::parse(
            r#"{"meta":{"domain":"canary","id":"1"},"wiki":"bewiki","type":"edit","title":"Foo","revision":{"new":2}}"#,
        )
        .unwrap();
        assert!(canary.is_canary());

        let other = RecentChangeEvent::parse(
            r#"{"meta":{"domain":"en.wikipedia.org","id":"2"},"wiki":"enwiki","server_name":"en.wikipedia.org","type":"edit","title":"Foo","revision":{"new":3}}"#,
        )
        .unwrap();
        assert!(!other.matches_wiki("bewiki", "be.wikipedia.org"));
    }
}
