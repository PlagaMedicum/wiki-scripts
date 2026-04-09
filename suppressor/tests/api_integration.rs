use suppressor::auth::authenticate;
use suppressor::config::EnvConfig;
use suppressor::config::RetryConfig;
use suppressor::mw_api::{MediaWikiClient, is_fatal_auth_or_permission_error};
use wiremock::matchers::{body_string_contains, method, path, query_param};
use wiremock::{Mock, MockServer, ResponseTemplate};

#[tokio::test]
async fn authenticates_and_reads_rights() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/w/api.php"))
        .and(query_param("action", "query"))
        .and(query_param("meta", "tokens"))
        .and(query_param("type", "login"))
        .respond_with(ResponseTemplate::new(200).set_body_raw(
            r#"{"query":{"tokens":{"logintoken":"LOGIN_TOKEN"}}}"#,
            "application/json",
        ))
        .mount(&server)
        .await;

    Mock::given(method("POST"))
        .and(path("/w/api.php"))
        .and(body_string_contains("action=login"))
        .respond_with(
            ResponseTemplate::new(200)
                .set_body_raw(r#"{"login":{"result":"Success"}}"#, "application/json"),
        )
        .mount(&server)
        .await;

    Mock::given(method("GET"))
        .and(path("/w/api.php"))
        .and(query_param("action", "query"))
        .and(query_param("meta", "tokens"))
        .respond_with(ResponseTemplate::new(200).set_body_raw(
            r#"{"query":{"tokens":{"csrftoken":"CSRF_TOKEN"}}}"#,
            "application/json",
        ))
        .mount(&server)
        .await;

    Mock::given(method("GET"))
        .and(path("/w/api.php"))
        .and(query_param("action", "query"))
        .and(query_param("meta", "userinfo"))
        .respond_with(ResponseTemplate::new(200).set_body_raw(
            r#"{"query":{"userinfo":{"name":"Wizardist","rights":["deleterevision","deletelogentry","apihighlimits"]}}}"#,
            "application/json",
        ))
        .mount(&server)
        .await;

    let env = EnvConfig {
        api_url: format!("{}/w/api.php", server.uri()),
        stream_url: "https://stream.wikimedia.org/v2/stream/recentchange".to_string(),
        bot_username: "Bot@password".to_string(),
        bot_password: "secret".to_string(),
        user_agent: "test-agent".to_string(),
        env_file: std::path::PathBuf::from(".env"),
    };
    let client = MediaWikiClient::new(&env).unwrap();
    let auth = authenticate(&client, &env).await.unwrap();
    assert_eq!(auth.username, "Wizardist");
    assert!(auth.has_required_rights());
    assert!(auth.has_high_limits());
}

#[tokio::test]
async fn retries_revisiondelete_after_badtoken_once() {
    let server = MockServer::start().await;
    let env = EnvConfig {
        api_url: format!("{}/w/api.php", server.uri()),
        stream_url: "https://stream.wikimedia.org/v2/stream/recentchange".to_string(),
        bot_username: "Bot@password".to_string(),
        bot_password: "secret".to_string(),
        user_agent: "test-agent".to_string(),
        env_file: std::path::PathBuf::from(".env"),
    };
    let client = MediaWikiClient::new(&env).unwrap();
    let retry = RetryConfig {
        stream_backoff_initial_ms: 1000,
        stream_backoff_max_ms: 30000,
        api_max_retries: 3,
        since_recovery_seconds: 60,
    };
    let mut csrf = "OLD_TOKEN".to_string();

    Mock::given(method("POST"))
        .and(path("/w/api.php"))
        .and(body_string_contains("action=revisiondelete"))
        .and(body_string_contains("token=OLD_TOKEN"))
        .respond_with(ResponseTemplate::new(200).set_body_raw(
            r#"{"error":{"code":"badtoken","info":"Bad token"}}"#,
            "application/json",
        ))
        .up_to_n_times(1)
        .mount(&server)
        .await;

    Mock::given(method("POST"))
        .and(path("/w/api.php"))
        .and(body_string_contains("action=revisiondelete"))
        .and(body_string_contains("token=NEW_TOKEN"))
        .and(body_string_contains("ids=123"))
        .respond_with(ResponseTemplate::new(200).set_body_raw(
            r#"{"revisiondelete":{"status":"Success"}}"#,
            "application/json",
        ))
        .mount(&server)
        .await;

    client
        .revision_delete_with_retry(
            &[123],
            "reason",
            &mut csrf,
            &retry,
            || async { Ok("RELOGIN_TOKEN".to_string()) },
            || async { Ok("NEW_TOKEN".to_string()) },
        )
        .await
        .unwrap();

    assert_eq!(csrf, "NEW_TOKEN");
}

#[test]
fn classifies_fatal_permission_errors() {
    let error = anyhow::anyhow!("Permission failure during revisiondelete: denied");
    assert!(is_fatal_auth_or_permission_error(&error));
}
