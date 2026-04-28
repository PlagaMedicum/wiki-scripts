use std::future::Future;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, Utc};
use metrics::histogram;
use reqwest::{
    Client, StatusCode, Url,
    header::{CONTENT_TYPE, RETRY_AFTER},
};
use serde_json::Value;
use tracing::warn;

use crate::config::{EnvConfig, RetryConfig};
use crate::state::ApiFailureSnapshot;

#[derive(Clone)]
pub struct MediaWikiClient {
    http: Client,
    api_url: String,
    stream_url: String,
    user_agent: String,
}

#[derive(Clone, Debug)]
pub struct PageMetadata {
    pub pageid: Option<u64>,
    pub lastrevid: Option<u64>,
    pub timestamp: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug)]
pub struct PageContent {
    pub metadata: PageMetadata,
    pub content: String,
}

#[derive(Clone, Debug)]
pub struct RevisionRecord {
    pub revid: u64,
    pub timestamp: DateTime<Utc>,
    pub user_hidden: bool,
    pub comment_hidden: bool,
}

#[derive(Clone, Debug)]
pub struct ApiUserInfo {
    pub name: String,
    pub rights: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct ApiError {
    pub code: String,
    pub info: String,
    pub http_status: Option<u16>,
    pub content_type: Option<String>,
    pub retry_after_seconds: Option<u64>,
}

#[derive(Clone, Debug)]
pub struct ApiTransportError {
    pub class: String,
    pub info: String,
    pub http_status: Option<u16>,
    pub content_type: Option<String>,
    pub retry_after_seconds: Option<u64>,
    pub retryable: bool,
}

impl MediaWikiClient {
    pub fn new(env: &EnvConfig) -> Result<Self> {
        let http = Client::builder()
            .cookie_store(true)
            .user_agent(env.user_agent.clone())
            .build()
            .context("Failed to build HTTP client")?;
        Ok(Self {
            http,
            api_url: env.api_url.clone(),
            stream_url: env.stream_url.clone(),
            user_agent: env.user_agent.clone(),
        })
    }

    pub fn stream_url(&self) -> &str {
        &self.stream_url
    }

    pub fn user_agent(&self) -> &str {
        &self.user_agent
    }

    pub async fn get_login_token(&self) -> Result<String> {
        let value = self
            .get_json(&[("action", "query"), ("meta", "tokens"), ("type", "login")])
            .await?;
        value["query"]["tokens"]["logintoken"]
            .as_str()
            .map(str::to_string)
            .ok_or_else(|| anyhow::anyhow!("Missing login token in API response"))
    }

    pub async fn login(&self, username: &str, password: &str, token: &str) -> Result<()> {
        let value = self
            .post_form_json(&[
                ("action", "login".to_string()),
                ("lgname", username.to_string()),
                ("lgpassword", password.to_string()),
                ("lgtoken", token.to_string()),
            ])
            .await?;
        let result = value["login"]["result"].as_str().unwrap_or_default();
        if result != "Success" {
            bail!("MediaWiki login failed with result {}", result);
        }
        Ok(())
    }

    pub async fn get_csrf_token(&self) -> Result<String> {
        let value = self
            .get_json(&[("action", "query"), ("meta", "tokens")])
            .await?;
        value["query"]["tokens"]["csrftoken"]
            .as_str()
            .map(str::to_string)
            .ok_or_else(|| anyhow::anyhow!("Missing CSRF token in API response"))
    }

    pub async fn get_userinfo(&self) -> Result<ApiUserInfo> {
        let value = self
            .get_json(&[
                ("action", "query"),
                ("meta", "userinfo"),
                ("uiprop", "rights"),
            ])
            .await?;
        let info = &value["query"]["userinfo"];
        let name = info["name"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Missing authenticated username"))?
            .to_string();
        let rights = info["rights"]
            .as_array()
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .filter_map(|item| item.as_str().map(str::to_string))
            .collect();
        Ok(ApiUserInfo { name, rights })
    }

    pub async fn fetch_page_metadata(&self, title: &str) -> Result<PageMetadata> {
        let value = self
            .get_json(&[
                ("action", "query"),
                ("titles", title),
                ("prop", "revisions"),
                ("rvlimit", "1"),
                ("rvprop", "ids|timestamp"),
            ])
            .await?;
        let page = first_page(&value)?;
        let revision = page["revisions"].as_array().and_then(|items| items.first());
        Ok(PageMetadata {
            pageid: page["pageid"].as_u64(),
            lastrevid: revision.and_then(|revision| revision["revid"].as_u64()),
            timestamp: revision
                .and_then(|revision| revision["timestamp"].as_str())
                .map(parse_timestamp)
                .transpose()?,
        })
    }

    pub async fn fetch_page_content(&self, title: &str) -> Result<PageContent> {
        let value = self
            .get_json(&[
                ("action", "query"),
                ("titles", title),
                ("prop", "revisions"),
                ("rvlimit", "1"),
                ("rvprop", "ids|timestamp|content"),
                ("rvslots", "main"),
            ])
            .await?;
        let page = first_page(&value)?;
        let revision = page["revisions"]
            .as_array()
            .and_then(|items| items.first())
            .ok_or_else(|| anyhow::anyhow!("Missing page content revision"))?;
        let content = revision["slots"]["main"]["content"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("Missing revision content"))?
            .to_string();
        Ok(PageContent {
            metadata: PageMetadata {
                pageid: page["pageid"].as_u64(),
                lastrevid: revision["revid"].as_u64(),
                timestamp: revision["timestamp"]
                    .as_str()
                    .map(parse_timestamp)
                    .transpose()?,
            },
            content,
        })
    }

    pub async fn fetch_revisions(
        &self,
        title: &str,
        since: Option<DateTime<Utc>>,
    ) -> Result<Vec<RevisionRecord>> {
        let mut result = Vec::new();
        let mut continue_token: Option<String> = None;

        loop {
            let mut params = vec![
                ("action", "query".to_string()),
                ("titles", title.to_string()),
                ("prop", "revisions".to_string()),
                ("rvlimit", "max".to_string()),
                ("rvprop", "ids|timestamp|user|comment".to_string()),
                ("rvdir", "newer".to_string()),
            ];
            if let Some(since) = since {
                params.push(("rvstart", mediawiki_timestamp(since)));
            }
            if let Some(token) = continue_token.clone() {
                params.push(("rvcontinue", token));
            }
            let borrowed = params
                .iter()
                .map(|(key, value)| (*key, value.as_str()))
                .collect::<Vec<_>>();
            let value = self.get_json(&borrowed).await?;
            let page = first_page(&value)?;
            if let Some(revisions) = page["revisions"].as_array() {
                for revision in revisions {
                    if let (Some(revid), Some(timestamp)) =
                        (revision["revid"].as_u64(), revision["timestamp"].as_str())
                    {
                        result.push(RevisionRecord {
                            revid,
                            timestamp: parse_timestamp(timestamp)?,
                            user_hidden: revision.get("userhidden").is_some(),
                            comment_hidden: revision.get("commenthidden").is_some(),
                        });
                    }
                }
            }

            continue_token = value["continue"]["rvcontinue"].as_str().map(str::to_string);
            if continue_token.is_none() {
                break;
            }
        }

        Ok(result)
    }

    pub async fn fetch_revisions_in_window(
        &self,
        title: &str,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
    ) -> Result<Vec<RevisionRecord>> {
        let revisions = self.fetch_revisions(title, Some(start)).await?;
        Ok(revisions
            .into_iter()
            .filter(|revision| revision.timestamp >= start && revision.timestamp <= end)
            .collect())
    }

    pub async fn resolve_redirect_target(&self, title: &str) -> Result<Option<String>> {
        let value = self
            .get_json(&[("action", "query"), ("titles", title), ("redirects", "1")])
            .await?;
        Ok(value["query"]["redirects"]
            .as_array()
            .and_then(|redirects| redirects.first())
            .and_then(|redirect| redirect["to"].as_str())
            .map(str::to_string))
    }

    pub async fn revision_delete(&self, ids: &[u64], reason: &str, csrf_token: &str) -> Result<()> {
        let joined = ids.iter().map(u64::to_string).collect::<Vec<_>>().join("|");
        let value = self
            .post_form_json(&[
                ("action", "revisiondelete".to_string()),
                ("type", "revision".to_string()),
                ("ids", joined),
                ("hide", "user|comment".to_string()),
                ("suppress", "no".to_string()),
                ("reason", reason.to_string()),
                ("token", csrf_token.to_string()),
            ])
            .await?;
        if value.get("revisiondelete").is_none() && value.get("success").is_none() {
            bail!("Unexpected revisiondelete response");
        }
        Ok(())
    }

    pub async fn revision_delete_with_retry<Relogin, RefreshToken, ReloginFuture, RefreshFuture>(
        &self,
        ids: &[u64],
        reason: &str,
        csrf_token: &mut String,
        retry: &RetryConfig,
        relogin: Relogin,
        refresh_token: RefreshToken,
    ) -> Result<()>
    where
        Relogin: Fn() -> ReloginFuture,
        RefreshToken: Fn() -> RefreshFuture,
        ReloginFuture: Future<Output = Result<String>> + Send + 'static,
        RefreshFuture: Future<Output = Result<String>> + Send + 'static,
    {
        let mut attempts = 0;
        loop {
            match self.revision_delete(ids, reason, csrf_token).await {
                Ok(()) => return Ok(()),
                Err(error) => {
                    attempts += 1;
                    if let Some(api_error) = error.downcast_ref::<ApiError>() {
                        match api_error.code.as_str() {
                            "badtoken" if attempts <= 1 => {
                                *csrf_token = refresh_token().await?;
                                continue;
                            }
                            "notloggedin" | "assertuserfailed" if attempts <= 2 => {
                                *csrf_token = relogin().await?;
                                continue;
                            }
                            "permissiondenied" | "cantdelete" => {
                                bail!(
                                    "Permission failure during revisiondelete: {}",
                                    api_error.info
                                );
                            }
                            _ => {}
                        }
                    }
                    if attempts <= retry.api_max_retries && is_transient(&error) {
                        let delay = 2_u64.saturating_pow(attempts - 1);
                        warn!(
                            attempts,
                            delay_seconds = delay,
                            ids_count = ids.len(),
                            "transient revisiondelete failure; retrying after backoff"
                        );
                        histogram!("api_retry_backoff_seconds").record(delay as f64);
                        tokio::time::sleep(std::time::Duration::from_secs(delay)).await;
                        continue;
                    }
                    return Err(error);
                }
            }
        }
    }

    async fn get_json(&self, params: &[(&str, &str)]) -> Result<Value> {
        let mut request = self.http.get(&self.api_url);
        for (key, value) in params {
            request = request.query(&[(*key, *value)]);
        }
        request = request.query(&[("format", "json"), ("formatversion", "2")]);
        let response = request.send().await.context("GET request failed")?;
        parse_response(response).await
    }

    async fn post_form_json(&self, params: &[(&str, String)]) -> Result<Value> {
        let form = params
            .iter()
            .map(|(key, value)| (*key, value.clone()))
            .chain([
                ("format", "json".to_string()),
                ("formatversion", "2".to_string()),
            ])
            .collect::<Vec<_>>();
        let response = self
            .http
            .post(&self.api_url)
            .form(&form)
            .send()
            .await
            .context("POST request failed")?;
        parse_response(response).await
    }

    pub fn build_stream_url(
        &self,
        last_event_id: Option<&str>,
        since_seconds: Option<i64>,
    ) -> Result<Url> {
        let mut url = Url::parse(&self.stream_url).context("Invalid stream URL")?;
        if last_event_id.is_none()
            && let Some(seconds) = since_seconds
        {
            let since = mediawiki_timestamp(Utc::now() - chrono::TimeDelta::seconds(seconds));
            url.query_pairs_mut().append_pair("since", &since);
        }
        Ok(url)
    }
}

pub fn mediawiki_timestamp(timestamp: DateTime<Utc>) -> String {
    timestamp.format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

pub fn is_fatal_auth_or_permission_error(error: &anyhow::Error) -> bool {
    if let Some(api_error) = error.downcast_ref::<ApiError>() {
        return matches!(
            api_error.code.as_str(),
            "permissiondenied" | "cantdelete" | "notloggedin" | "assertuserfailed" | "badtoken"
        );
    }
    let rendered = format!("{error:#}");
    rendered.contains("Permission failure during revisiondelete")
        || rendered.contains("re-login failed")
        || rendered.contains("CSRF refresh failed")
        || rendered.contains("Authenticated session lacks")
}

pub fn parse_timestamp(value: &str) -> Result<DateTime<Utc>> {
    Ok(DateTime::parse_from_rfc3339(value)
        .with_context(|| format!("Invalid RFC3339 timestamp {}", value))?
        .with_timezone(&Utc))
}

pub fn classify_api_failure(
    error: &anyhow::Error,
    operation: &str,
    sample_title: Option<&str>,
    sample_revid: Option<u64>,
) -> ApiFailureSnapshot {
    if let Some(api_error) = error.downcast_ref::<ApiError>() {
        let class = if matches!(
            api_error.code.as_str(),
            "badtoken" | "notloggedin" | "assertuserfailed" | "permissiondenied" | "cantdelete"
        ) {
            "auth-session"
        } else {
            "api-json-error"
        };
        return ApiFailureSnapshot {
            class: class.to_string(),
            api_code: Some(api_error.code.clone()),
            http_status: api_error.http_status,
            content_type: api_error.content_type.clone(),
            retryable: api_code_retryable(&api_error.code),
            retry_after_seconds: api_error.retry_after_seconds,
            operation: operation.to_string(),
            sample_title: sample_title.map(str::to_string),
            sample_revid,
            message: safe_error_message(&api_error.info),
            occurred_at: Some(Utc::now()),
        };
    }
    if let Some(transport_error) = error.downcast_ref::<ApiTransportError>() {
        return ApiFailureSnapshot {
            class: transport_error.class.clone(),
            api_code: None,
            http_status: transport_error.http_status,
            content_type: transport_error.content_type.clone(),
            retryable: transport_error.retryable,
            retry_after_seconds: transport_error.retry_after_seconds,
            operation: operation.to_string(),
            sample_title: sample_title.map(str::to_string),
            sample_revid,
            message: safe_error_message(&transport_error.info),
            occurred_at: Some(Utc::now()),
        };
    }
    if let Some(reqwest_error) = error.downcast_ref::<reqwest::Error>() {
        let class = if reqwest_error.is_timeout() {
            "timeout"
        } else {
            "network"
        };
        return ApiFailureSnapshot {
            class: class.to_string(),
            api_code: None,
            http_status: reqwest_error.status().map(|status| status.as_u16()),
            content_type: None,
            retryable: reqwest_error.is_timeout()
                || reqwest_error.is_connect()
                || reqwest_error
                    .status()
                    .map(|status| {
                        status.is_server_error() || status == StatusCode::TOO_MANY_REQUESTS
                    })
                    .unwrap_or(false),
            retry_after_seconds: None,
            operation: operation.to_string(),
            sample_title: sample_title.map(str::to_string),
            sample_revid,
            message: safe_error_message(&reqwest_error.to_string()),
            occurred_at: Some(Utc::now()),
        };
    }
    let rendered = format!("{error:#}");
    let class = if rendered.contains("Failed to decode JSON response") {
        "decode-error"
    } else if rendered.contains("Permission failure")
        || rendered.contains("re-login failed")
        || rendered.contains("CSRF refresh failed")
        || rendered.contains("Authenticated session lacks")
    {
        "auth-session"
    } else {
        "unknown"
    };
    ApiFailureSnapshot {
        class: class.to_string(),
        api_code: None,
        http_status: None,
        content_type: None,
        retryable: class != "auth-session",
        retry_after_seconds: None,
        operation: operation.to_string(),
        sample_title: sample_title.map(str::to_string),
        sample_revid,
        message: safe_error_message(&rendered),
        occurred_at: Some(Utc::now()),
    }
}

fn first_page(value: &Value) -> Result<&Value> {
    value["query"]["pages"]
        .as_array()
        .and_then(|pages| pages.first())
        .ok_or_else(|| anyhow::anyhow!("Missing page data in API response"))
}

fn is_transient(error: &anyhow::Error) -> bool {
    if let Some(api_error) = error.downcast_ref::<ApiError>() {
        return api_code_retryable(&api_error.code);
    }
    if let Some(transport_error) = error.downcast_ref::<ApiTransportError>() {
        return transport_error.retryable;
    }
    error
        .downcast_ref::<reqwest::Error>()
        .map(|err| {
            err.is_timeout()
                || err.is_connect()
                || err
                    .status()
                    .map(|status| {
                        status.is_server_error() || status == StatusCode::TOO_MANY_REQUESTS
                    })
                    .unwrap_or(false)
        })
        .unwrap_or(false)
}

async fn parse_response(response: reqwest::Response) -> Result<Value> {
    let status = response.status();
    let retry_after_seconds = response
        .headers()
        .get(RETRY_AFTER)
        .and_then(parse_retry_after_seconds);
    let content_type = response
        .headers()
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(str::to_string);
    let body = response
        .text()
        .await
        .context("Failed to read response body")?;
    let value: Value = serde_json::from_str(&body).map_err(|error| {
        let class = if content_type
            .as_deref()
            .map(|value| value.to_ascii_lowercase().contains("json"))
            .unwrap_or(false)
        {
            "decode-error"
        } else {
            "non-json-response"
        };
        anyhow::Error::new(ApiTransportError {
            class: class.to_string(),
            info: format!("Failed to decode JSON response: {error}"),
            http_status: Some(status.as_u16()),
            content_type: content_type.clone(),
            retry_after_seconds,
            retryable: status.is_server_error() || status == StatusCode::TOO_MANY_REQUESTS,
        })
    })?;
    if let Some(error) = value.get("error") {
        let api_error = ApiError {
            code: error["code"].as_str().unwrap_or("unknown").to_string(),
            info: error["info"].as_str().unwrap_or("unknown").to_string(),
            http_status: Some(status.as_u16()),
            content_type: content_type.clone(),
            retry_after_seconds,
        };
        return Err(anyhow::Error::new(api_error));
    }
    if !status.is_success() {
        return Err(anyhow::Error::new(ApiTransportError {
            class: "http-status".to_string(),
            info: format!("API request failed with HTTP status {}", status),
            http_status: Some(status.as_u16()),
            content_type,
            retry_after_seconds,
            retryable: status.is_server_error() || status == StatusCode::TOO_MANY_REQUESTS,
        }));
    }
    Ok(value)
}

fn parse_retry_after_seconds(value: &reqwest::header::HeaderValue) -> Option<u64> {
    let raw = value.to_str().ok()?.trim();
    if let Ok(seconds) = raw.parse::<u64>() {
        return Some(seconds);
    }
    let retry_at = DateTime::parse_from_rfc2822(raw).ok()?.with_timezone(&Utc);
    let delta = retry_at.signed_duration_since(Utc::now()).num_seconds();
    Some(delta.max(0) as u64)
}

fn api_code_retryable(code: &str) -> bool {
    matches!(
        code,
        "badtoken" | "notloggedin" | "assertuserfailed" | "maxlag" | "ratelimited" | "readonly"
    )
}

fn safe_error_message(value: &str) -> String {
    let compact = value.split_whitespace().collect::<Vec<_>>().join(" ");
    compact.chars().take(180).collect()
}

impl std::fmt::Display for ApiError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.info)
    }
}

impl std::error::Error for ApiError {}

impl std::fmt::Display for ApiTransportError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.class, self.info)
    }
}

impl std::error::Error for ApiTransportError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mediawiki_timestamp_uses_utc_second_precision_without_fractionals() {
        let timestamp = DateTime::parse_from_rfc3339("2026-04-25T08:58:18.582411Z")
            .unwrap()
            .with_timezone(&Utc);

        assert_eq!(mediawiki_timestamp(timestamp), "2026-04-25T08:58:18Z");
    }

    #[test]
    fn api_json_errors_preserve_code_and_safe_metadata() {
        let error = anyhow::Error::new(ApiError {
            code: "badtimestamp".to_string(),
            info: "Invalid timestamp value at rvstart".to_string(),
            http_status: Some(200),
            content_type: Some("application/json; charset=utf-8".to_string()),
            retry_after_seconds: None,
        });

        let snapshot = classify_api_failure(&error, "fetch-revisions", Some("Title"), None);

        assert_eq!(snapshot.class, "api-json-error");
        assert_eq!(snapshot.api_code.as_deref(), Some("badtimestamp"));
        assert_eq!(snapshot.http_status, Some(200));
        assert!(!snapshot.retryable);
        assert_eq!(snapshot.sample_title.as_deref(), Some("Title"));
    }

    #[test]
    fn transport_errors_preserve_class_status_and_content_type() {
        let error = anyhow::Error::new(ApiTransportError {
            class: "non-json-response".to_string(),
            info: "Failed to decode JSON response".to_string(),
            http_status: Some(502),
            content_type: Some("text/html".to_string()),
            retry_after_seconds: Some(45),
            retryable: true,
        });

        let snapshot = classify_api_failure(&error, "fetch-revisions", None, Some(42));

        assert_eq!(snapshot.class, "non-json-response");
        assert_eq!(snapshot.http_status, Some(502));
        assert_eq!(snapshot.content_type.as_deref(), Some("text/html"));
        assert_eq!(snapshot.retry_after_seconds, Some(45));
        assert!(snapshot.retryable);
        assert_eq!(snapshot.sample_revid, Some(42));
    }

    #[test]
    fn api_errors_preserve_retry_after_seconds() {
        let error = anyhow::Error::new(ApiError {
            code: "ratelimited".to_string(),
            info: "Too many requests".to_string(),
            http_status: Some(429),
            content_type: Some("application/json; charset=utf-8".to_string()),
            retry_after_seconds: Some(30),
        });

        let snapshot = classify_api_failure(&error, "fetch-revisions", Some("Title"), None);

        assert_eq!(snapshot.api_code.as_deref(), Some("ratelimited"));
        assert_eq!(snapshot.http_status, Some(429));
        assert_eq!(snapshot.retry_after_seconds, Some(30));
        assert!(snapshot.retryable);
    }

    #[test]
    fn parses_retry_after_seconds_header_value() {
        let header = reqwest::header::HeaderValue::from_static("120");
        assert_eq!(parse_retry_after_seconds(&header), Some(120));
    }
}
