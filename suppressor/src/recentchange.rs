use anyhow::{Context, Result};
use chrono::{DateTime, TimeZone, Utc};
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
    pub timestamp: Option<i64>,
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

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PageChangeTrigger {
    pub title: String,
    pub normalized_title: String,
    pub trigger_revid: Option<u64>,
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

    pub fn observed_at(&self) -> Option<DateTime<Utc>> {
        self.timestamp
            .and_then(|value| Utc.timestamp_opt(value, 0).single())
    }

    pub fn normalized_title(&self) -> Option<String> {
        self.title.as_deref().map(normalize_title)
    }

    pub fn trigger_revid(&self) -> Option<u64> {
        self.revision.as_ref().and_then(|revision| revision.new)
    }

    pub fn to_page_change_trigger(&self) -> Option<PageChangeTrigger> {
        let title = self.title.clone()?;
        Some(PageChangeTrigger {
            normalized_title: normalize_title(&title),
            title,
            trigger_revid: self.trigger_revid(),
        })
    }

    pub fn to_candidate(&self, sse_id: Option<&str>) -> Option<LiveRevisionCandidate> {
        let revid = self.trigger_revid()?;
        let title = self.title.clone()?;
        Some(LiveRevisionCandidate {
            normalized_title: self
                .normalized_title()
                .expect("title clone guarantees normalized title"),
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
pub(crate) mod test_fixtures {
    use serde_json::json;

    use super::RecentChangeEvent;

    #[derive(Clone, Debug)]
    pub(crate) struct SyntheticRecentChange {
        meta_id: Option<String>,
        meta_domain: Option<String>,
        wiki: Option<String>,
        server_name: Option<String>,
        change_type: Option<String>,
        title: Option<String>,
        user: Option<String>,
        comment: Option<String>,
        timestamp: Option<i64>,
        old_revid: Option<u64>,
        new_revid: Option<u64>,
    }

    impl Default for SyntheticRecentChange {
        fn default() -> Self {
            Self {
                meta_id: Some("fixture-1".to_string()),
                meta_domain: Some("be.wikipedia.org".to_string()),
                wiki: Some("bewiki".to_string()),
                server_name: Some("be.wikipedia.org".to_string()),
                change_type: Some("edit".to_string()),
                title: Some("Fixture Page".to_string()),
                user: Some("FixtureUser".to_string()),
                comment: Some("Fixture comment".to_string()),
                timestamp: Some(1_714_379_810),
                old_revid: Some(1),
                new_revid: Some(2),
            }
        }
    }

    impl SyntheticRecentChange {
        pub(crate) fn with_title(mut self, title: impl Into<String>) -> Self {
            self.title = Some(title.into());
            self
        }

        pub(crate) fn with_change_type(mut self, change_type: impl Into<String>) -> Self {
            self.change_type = Some(change_type.into());
            self
        }

        pub(crate) fn with_domain(mut self, domain: impl Into<String>) -> Self {
            self.meta_domain = Some(domain.into());
            self
        }

        pub(crate) fn with_wiki(mut self, wiki: impl Into<String>) -> Self {
            self.wiki = Some(wiki.into());
            self
        }

        pub(crate) fn with_server_name(mut self, server_name: impl Into<String>) -> Self {
            self.server_name = Some(server_name.into());
            self
        }

        pub(crate) fn with_revision_ids(
            mut self,
            old_revid: Option<u64>,
            new_revid: Option<u64>,
        ) -> Self {
            self.old_revid = old_revid;
            self.new_revid = new_revid;
            self
        }

        pub(crate) fn to_json(&self) -> String {
            json!({
                "meta": {
                    "domain": self.meta_domain,
                    "id": self.meta_id,
                },
                "wiki": self.wiki,
                "server_name": self.server_name,
                "type": self.change_type,
                "title": self.title,
                "user": self.user,
                "comment": self.comment,
                "timestamp": self.timestamp,
                "revision": {
                    "old": self.old_revid,
                    "new": self.new_revid,
                },
            })
            .to_string()
        }

        pub(crate) fn parse(&self) -> RecentChangeEvent {
            RecentChangeEvent::parse(&self.to_json()).expect("synthetic recentchange should parse")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::recentchange::test_fixtures::SyntheticRecentChange;

    fn watched_edit_event_json(title: &str, revid: u64) -> String {
        SyntheticRecentChange::default()
            .with_title(title)
            .with_revision_ids(Some(1), Some(revid))
            .to_json()
    }

    #[test]
    fn accepts_edit_event_with_revision_new() {
        let raw = watched_edit_event_json("Foo_bar", 2);
        let event = RecentChangeEvent::parse(&raw).unwrap();
        let candidate = event.to_candidate(Some("stream-1")).unwrap();
        assert_eq!(candidate.revid, 2);
        assert_eq!(candidate.normalized_title, "Foo bar");
        assert_eq!(candidate.event_id.as_deref(), Some("stream-1"));
    }

    #[test]
    fn rejects_missing_revision_new() {
        let event = SyntheticRecentChange::default()
            .with_title("Foo")
            .with_revision_ids(Some(1), None)
            .parse();
        assert!(event.to_candidate(None).is_none());
    }

    #[test]
    fn rejects_canary_and_non_matching_wikis() {
        let canary = SyntheticRecentChange::default()
            .with_domain("canary")
            .with_title("Foo")
            .with_revision_ids(None, Some(2))
            .parse();
        assert!(canary.is_canary());

        let other = SyntheticRecentChange::default()
            .with_domain("en.wikipedia.org")
            .with_wiki("enwiki")
            .with_server_name("en.wikipedia.org")
            .with_title("Foo")
            .with_revision_ids(None, Some(3))
            .parse();
        assert!(!other.matches_wiki("bewiki", "be.wikipedia.org"));
    }

    #[test]
    fn synthetic_fixture_can_model_source_page_events() {
        let event = SyntheticRecentChange::default()
            .with_title("Удзельнік:Wizardist/SuppressionList")
            .with_change_type("edit")
            .with_revision_ids(Some(10), Some(11))
            .parse();

        assert_eq!(
            event.title.as_deref(),
            Some("Удзельнік:Wizardist/SuppressionList")
        );
        assert!(event.is_revision_event());
        assert!(event.matches_wiki("bewiki", "be.wikipedia.org"));
    }

    #[test]
    fn page_change_trigger_normalizes_title_and_keeps_trigger_revid() {
        let event = SyntheticRecentChange::default()
            .with_title("Вікіпедыя:Запыты_да_схавальнікаў")
            .with_revision_ids(Some(10), Some(11))
            .parse();

        let trigger = event.to_page_change_trigger().unwrap();

        assert_eq!(trigger.title, "Вікіпедыя:Запыты_да_схавальнікаў");
        assert_eq!(trigger.normalized_title, "Вікіпедыя:Запыты да схавальнікаў");
        assert_eq!(trigger.trigger_revid, Some(11));
    }
}
