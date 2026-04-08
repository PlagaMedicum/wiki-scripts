use anyhow::Result;

use crate::cache::SuppressionListCache;
use crate::config::AppConfig;
use crate::mw_api::{MediaWikiClient, PageMetadata};
use crate::titles::normalize_title;

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

#[cfg(test)]
mod tests {
    use std::path::PathBuf;
    use wiremock::matchers::{method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    use crate::config::EnvConfig;
    use crate::mw_api::MediaWikiClient;

    use super::fetch_redirect_target;

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
}
