use anyhow::Result;

use crate::cache::SuppressionListCache;
use crate::config::AppConfig;
use crate::mw_api::{MediaWikiClient, PageMetadata};
use suppressor_core::titles::normalize_title;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SourceRefreshTriggerKind {
    SuppressionList,
    RequestPage,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SourceRefreshFollowup {
    None,
    TitleScoped {
        scope_label: &'static str,
        titles: Vec<String>,
    },
    RecentWindow {
        scope_label: &'static str,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceRefreshCatchupPlan {
    pub new_titles_count: usize,
    pub removed_titles_count: usize,
    pub redirects_reused: bool,
    pub followup: SourceRefreshFollowup,
}

impl SourceRefreshCatchupPlan {
    pub fn catchup_requested(&self) -> bool {
        !matches!(self.followup, SourceRefreshFollowup::None)
    }

    pub fn catchup_scope_label(&self) -> Option<&'static str> {
        match &self.followup {
            SourceRefreshFollowup::None => None,
            SourceRefreshFollowup::TitleScoped { scope_label, .. }
            | SourceRefreshFollowup::RecentWindow { scope_label } => Some(*scope_label),
        }
    }
}

pub async fn fetch_source_metadata(
    client: &MediaWikiClient,
    config: &AppConfig,
) -> Result<PageMetadata> {
    client
        .fetch_page_metadata(&config.suppression_list.title)
        .await
}

pub async fn fetch_bootstrap_snapshot(
    client: &MediaWikiClient,
    config: &AppConfig,
) -> Result<SuppressionListCache> {
    let content = client
        .fetch_page_content(&config.suppression_list.title)
        .await?;
    SuppressionListCache::from_source_content(
        &SuppressionListCache::initial(&config.suppression_list.title),
        content,
    )
}

pub async fn fetch_refreshed_snapshot(
    client: &MediaWikiClient,
    config: &AppConfig,
    current: &SuppressionListCache,
) -> Result<SuppressionListCache> {
    let content = client
        .fetch_page_content(&config.suppression_list.title)
        .await?;
    SuppressionListCache::from_source_content(current, content)
}

pub async fn fetch_redirect_target(
    client: &MediaWikiClient,
    title: &str,
) -> Result<Option<String>> {
    Ok(client
        .resolve_redirect_target(title)
        .await?
        .map(|target| normalize_title(&target))
        .filter(|target| target != title))
}

pub fn plan_source_refresh_catchup(
    before: &SuppressionListCache,
    after: &SuppressionListCache,
    trigger_kind: SourceRefreshTriggerKind,
    scope_limit: usize,
) -> SourceRefreshCatchupPlan {
    let diff = before.watched_title_diff(after);
    let added = diff.added;
    let removed = diff.removed;
    let followup = if !added.is_empty() {
        SourceRefreshFollowup::TitleScoped {
            scope_label: if added.len() > scope_limit {
                "new-titles-large"
            } else {
                "new-titles"
            },
            titles: added.clone(),
        }
    } else if matches!(trigger_kind, SourceRefreshTriggerKind::RequestPage) {
        SourceRefreshFollowup::RecentWindow {
            scope_label: "request-window",
        }
    } else {
        SourceRefreshFollowup::None
    };

    SourceRefreshCatchupPlan {
        new_titles_count: added.len(),
        removed_titles_count: removed.len(),
        redirects_reused: before.titles_hash_sha256 == after.titles_hash_sha256,
        followup,
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::path::PathBuf;
    use wiremock::matchers::{method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    use chrono::Utc;

    use crate::cache::SuppressionListCache;
    use crate::config::EnvConfig;
    use crate::mw_api::MediaWikiClient;

    use super::{
        SourceRefreshFollowup, SourceRefreshTriggerKind, fetch_redirect_target,
        plan_source_refresh_catchup,
    };

    #[tokio::test]
    async fn fetch_redirect_target_uses_api_redirect_targets() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("action", "query"))
            .and(query_param("titles", "Foo"))
            .and(query_param("redirects", "1"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"query":{"redirects":[{"from":"Foo","to":"Foo Redirect"}]}}"#,
                "application/json",
            ))
            .mount(&server)
            .await;

        let env = EnvConfig {
            api_url: format!("{}/w/api.php", server.uri()),
            stream_url: "https://stream.wikimedia.org/v2/stream/recentchange".to_string(),
            bot_username: "bot".to_string(),
            bot_password: "secret".to_string(),
            user_agent: "test-agent".to_string(),
            env_file: PathBuf::from(".env"),
        };
        let client = MediaWikiClient::new(&env).unwrap();
        let redirect = fetch_redirect_target(&client, "Foo").await.unwrap();

        assert_eq!(redirect, Some("Foo Redirect".to_string()));
    }

    fn test_snapshot(
        source_revid: u64,
        listed: &[&str],
        watched: &[&str],
        hash: &str,
    ) -> SuppressionListCache {
        SuppressionListCache {
            source_title: "Удзельнік:Wizardist/SuppressionList".to_string(),
            source_pageid: Some(1),
            source_lastrevid: Some(source_revid),
            source_last_timestamp: None,
            fetched_at: Utc::now(),
            listed_titles_normalized: listed.iter().map(|value| (*value).to_string()).collect(),
            watched_titles_normalized: watched.iter().map(|value| (*value).to_string()).collect(),
            redirect_map: BTreeMap::new(),
            titles_hash_sha256: hash.to_string(),
        }
    }

    #[test]
    fn suppression_list_refresh_prefers_new_titles_followup() {
        let before = test_snapshot(10, &["Foo"], &["Foo"], "old");
        let after = test_snapshot(11, &["Foo", "Bar"], &["Foo", "Bar"], "new");

        let plan = plan_source_refresh_catchup(
            &before,
            &after,
            SourceRefreshTriggerKind::SuppressionList,
            10,
        );

        assert_eq!(plan.new_titles_count, 1);
        assert_eq!(plan.removed_titles_count, 0);
        assert!(!plan.redirects_reused);
        assert_eq!(
            plan.followup,
            SourceRefreshFollowup::TitleScoped {
                scope_label: "new-titles",
                titles: vec!["Bar".to_string()],
            }
        );
    }

    #[test]
    fn request_page_refresh_uses_recent_window_when_titles_are_unchanged() {
        let before = test_snapshot(10, &["Foo"], &["Foo"], "same");
        let after = test_snapshot(11, &["Foo"], &["Foo"], "same");

        let plan =
            plan_source_refresh_catchup(&before, &after, SourceRefreshTriggerKind::RequestPage, 10);

        assert_eq!(plan.new_titles_count, 0);
        assert_eq!(plan.removed_titles_count, 0);
        assert!(plan.redirects_reused);
        assert_eq!(
            plan.followup,
            SourceRefreshFollowup::RecentWindow {
                scope_label: "request-window",
            }
        );
    }

    #[test]
    fn request_page_refresh_uses_new_titles_when_refresh_adds_pages() {
        let before = test_snapshot(10, &["Foo"], &["Foo"], "old");
        let after = test_snapshot(11, &["Foo", "Bar"], &["Foo", "Bar"], "new");

        let plan =
            plan_source_refresh_catchup(&before, &after, SourceRefreshTriggerKind::RequestPage, 10);

        assert_eq!(
            plan.followup,
            SourceRefreshFollowup::TitleScoped {
                scope_label: "new-titles",
                titles: vec!["Bar".to_string()],
            }
        );
    }
}
