use std::future::Future;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, Utc};
use metrics::histogram;
use reqwest::{
    Client, StatusCode, Url,
    header::{CONTENT_TYPE, RETRY_AFTER},
};
use serde::Serialize;
use serde_json::Value;
use tracing::warn;

use crate::config::{EnvConfig, RetryConfig};
use crate::state::ApiFailureSnapshot;
use suppressor_core::page::{PageContent, PageMetadata};

#[derive(Clone)]
pub struct MediaWikiClient {
    http: Client,
    api_url: String,
    stream_url: String,
    user_agent: String,
    retry: RetryConfig,
}

#[derive(Clone, Debug)]
pub struct RevisionRecord {
    pub revid: u64,
    pub timestamp: DateTime<Utc>,
    pub user_hidden: bool,
    pub comment_hidden: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecentChangeProbe {
    pub title: Option<String>,
    pub timestamp: DateTime<Utc>,
    pub revid: Option<u64>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RecentChangeRecord {
    pub title: String,
    pub timestamp: DateTime<Utc>,
    pub revid: u64,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RecentChangeWindow {
    pub changes: Vec<RecentChangeRecord>,
    pub chunk_count: usize,
    pub truncated: bool,
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
        Self::new_with_retry(env, &default_client_retry())
    }

    pub fn new_with_retry(env: &EnvConfig, retry: &RetryConfig) -> Result<Self> {
        let http = Client::builder()
            .cookie_store(true)
            .user_agent(env.user_agent.clone())
            .timeout(Duration::from_secs(60))
            .build()
            .context("Failed to build HTTP client")?;
        Ok(Self {
            http,
            api_url: env.api_url.clone(),
            stream_url: env.stream_url.clone(),
            user_agent: env.user_agent.clone(),
            retry: retry.clone(),
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
                    if let Some(record) = revision_record_from_value(revision)? {
                        result.push(record);
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

    pub async fn fetch_revision_by_id(&self, revid: u64) -> Result<Option<RevisionRecord>> {
        let revid_text = revid.to_string();
        let value = self
            .get_json(&[
                ("action", "query"),
                ("prop", "revisions"),
                ("revids", revid_text.as_str()),
                ("rvprop", "ids|timestamp|user|comment"),
            ])
            .await?;
        let Some(pages) = value["query"]["pages"].as_array() else {
            return Ok(None);
        };
        for page in pages {
            let Some(revisions) = page["revisions"].as_array() else {
                continue;
            };
            for revision in revisions {
                if let Some(record) = revision_record_from_value(revision)?
                    && record.revid == revid
                {
                    return Ok(Some(record));
                }
            }
        }
        Ok(None)
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

    pub async fn fetch_latest_recent_change(&self) -> Result<Option<RecentChangeProbe>> {
        let value = self
            .get_json(&[
                ("action", "query"),
                ("list", "recentchanges"),
                ("rclimit", "1"),
                ("rctype", "edit|new"),
                ("rcprop", "title|timestamp|ids"),
            ])
            .await?;
        let Some(change) = value["query"]["recentchanges"]
            .as_array()
            .and_then(|changes| changes.first())
        else {
            return Ok(None);
        };
        let Some(timestamp) = change["timestamp"].as_str() else {
            return Ok(None);
        };
        Ok(Some(RecentChangeProbe {
            title: change["title"].as_str().map(str::to_string),
            timestamp: parse_timestamp(timestamp)?,
            revid: change["revid"].as_u64(),
        }))
    }

    pub async fn fetch_recent_changes_in_window(
        &self,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
        limit: usize,
    ) -> Result<RecentChangeWindow> {
        if limit == 0 {
            return Ok(RecentChangeWindow::default());
        }
        let page_limit = limit.clamp(1, 500).to_string();
        let rcstart = mediawiki_timestamp(end);
        let rcend = mediawiki_timestamp(start);
        let mut continue_token: Option<String> = None;
        let mut changes = Vec::new();
        let mut chunk_count = 0;
        let mut truncated = false;

        loop {
            let mut params = vec![
                ("action", "query".to_string()),
                ("list", "recentchanges".to_string()),
                ("rclimit", page_limit.clone()),
                ("rctype", "edit|new".to_string()),
                ("rcprop", "title|timestamp|ids".to_string()),
                ("rcdir", "older".to_string()),
                ("rcstart", rcstart.clone()),
                ("rcend", rcend.clone()),
            ];
            if let Some(token) = continue_token.as_ref() {
                params.push(("rccontinue", token.clone()));
            }
            let borrowed = params
                .iter()
                .map(|(key, value)| (*key, value.as_str()))
                .collect::<Vec<_>>();
            let value = self.get_json(&borrowed).await?;
            chunk_count += 1;
            if let Some(raw_changes) = value["query"]["recentchanges"].as_array() {
                for change in raw_changes {
                    if changes.len() >= limit {
                        truncated = true;
                        break;
                    }
                    let (Some(title), Some(timestamp), Some(revid)) = (
                        change["title"].as_str(),
                        change["timestamp"].as_str(),
                        change["revid"].as_u64(),
                    ) else {
                        continue;
                    };
                    changes.push(RecentChangeRecord {
                        title: title.to_string(),
                        timestamp: parse_timestamp(timestamp)?,
                        revid,
                    });
                }
            }
            continue_token = value["continue"]["rccontinue"].as_str().map(str::to_string);
            if truncated || continue_token.is_none() {
                truncated = truncated || continue_token.is_some();
                break;
            }
        }

        Ok(RecentChangeWindow {
            changes,
            chunk_count,
            truncated,
        })
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

    pub async fn append_text(
        &self,
        title: &str,
        append_text: &str,
        summary: &str,
        csrf_token: &str,
    ) -> Result<u64> {
        let value = self
            .post_form_json(&[
                ("action", "edit".to_string()),
                ("title", title.to_string()),
                ("appendtext", append_text.to_string()),
                ("summary", summary.to_string()),
                ("minor", "1".to_string()),
                ("bot", "1".to_string()),
                ("token", csrf_token.to_string()),
            ])
            .await?;
        let result = value["edit"]["result"].as_str().unwrap_or_default();
        if result != "Success" {
            bail!("Unexpected edit response");
        }
        value["edit"]["newrevid"]
            .as_u64()
            .ok_or_else(|| anyhow::anyhow!("Missing newrevid in edit response"))
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
        let mut refreshed_token = false;
        let mut relogged_in = false;
        loop {
            match self.revision_delete(ids, reason, csrf_token).await {
                Ok(()) => return Ok(()),
                Err(error) => {
                    attempts += 1;
                    if let Some(api_error) = error.downcast_ref::<ApiError>() {
                        let auth_session_code = matches!(
                            api_error.code.as_str(),
                            "badtoken" | "notloggedin" | "assertuserfailed"
                        );
                        match api_error.code.as_str() {
                            "badtoken" if !refreshed_token => {
                                refreshed_token = true;
                                *csrf_token = refresh_token().await?;
                                continue;
                            }
                            "badtoken" | "notloggedin" | "assertuserfailed" if !relogged_in => {
                                relogged_in = true;
                                *csrf_token = relogin().await?;
                                continue;
                            }
                            "permissiondenied" | "cantdelete" => {
                                let info = api_error.info.clone();
                                return Err(error.context(format!(
                                    "Permission failure during revisiondelete: {info}"
                                )));
                            }
                            _ => {}
                        }
                        if auth_session_code {
                            return Err(error);
                        }
                    }
                    if attempts <= retry.api_max_retries && is_transient(&error) {
                        let delay = 2_u64.saturating_pow(attempts - 1);
                        warn!(
                            attempts,
                            delay_seconds = delay,
                            ids_count = ids.len(),
                            error = %error,
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

    async fn with_api_retry<F, Fut>(&self, operation: &str, mut request: F) -> Result<Value>
    where
        F: FnMut() -> Fut,
        Fut: Future<Output = Result<Value>>,
    {
        let mut attempts = 0;
        loop {
            match request().await {
                Ok(value) => return Ok(value),
                Err(error) => {
                    attempts += 1;
                    if attempts <= self.retry.api_max_retries && is_transient(&error) {
                        let delay = retry_delay_seconds(&error, attempts);
                        warn!(
                            operation,
                            attempts,
                            delay_seconds = delay,
                            error = %error,
                            "transient MediaWiki API failure; retrying after backoff"
                        );
                        histogram!("api_retry_backoff_seconds").record(delay as f64);
                        tokio::time::sleep(Duration::from_secs(delay)).await;
                        continue;
                    }
                    return Err(error);
                }
            }
        }
    }

    async fn get_json(&self, params: &[(&str, &str)]) -> Result<Value> {
        self.with_api_retry("GET", || self.get_json_once(params))
            .await
    }

    async fn get_json_once(&self, params: &[(&str, &str)]) -> Result<Value> {
        let mut request = self.http.get(&self.api_url);
        for (key, value) in params {
            request = request.query(&[(*key, *value)]);
        }
        request = request.query(&[("format", "json"), ("formatversion", "2")]);
        let response = request.send().await.context("GET request failed")?;
        parse_response(response).await
    }

    async fn post_form_json(&self, params: &[(&str, String)]) -> Result<Value> {
        self.with_api_retry("POST", || self.post_form_json_once(params))
            .await
    }

    async fn post_form_json_once(&self, params: &[(&str, String)]) -> Result<Value> {
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

fn default_client_retry() -> RetryConfig {
    RetryConfig {
        stream_backoff_initial_ms: 1000,
        stream_backoff_max_ms: 10000,
        api_max_retries: 0,
        since_recovery_seconds: 0,
    }
}

fn retry_delay_seconds(error: &anyhow::Error, attempts: u32) -> u64 {
    if let Some(api_error) = error.downcast_ref::<ApiError>()
        && let Some(seconds) = api_error.retry_after_seconds
    {
        return seconds;
    }
    if let Some(transport_error) = error.downcast_ref::<ApiTransportError>()
        && let Some(seconds) = transport_error.retry_after_seconds
    {
        return seconds;
    }
    2_u64.saturating_pow(attempts.saturating_sub(1))
}

pub fn revision_url(server_name: &str, revid: u64) -> String {
    format!("https://{server_name}/wiki/Special:Diff/{revid}")
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

fn revision_record_from_value(revision: &Value) -> Result<Option<RevisionRecord>> {
    let (Some(revid), Some(timestamp)) =
        (revision["revid"].as_u64(), revision["timestamp"].as_str())
    else {
        return Ok(None);
    };
    Ok(Some(RevisionRecord {
        revid,
        timestamp: parse_timestamp(timestamp)?,
        user_hidden: revision.get("userhidden").is_some(),
        comment_hidden: revision.get("commenthidden").is_some(),
    }))
}

pub fn classify_api_failure(
    error: &anyhow::Error,
    operation: &str,
    sample_title: Option<&str>,
    sample_revid: Option<u64>,
) -> ApiFailureSnapshot {
    if let Some(api_error) = error.downcast_ref::<ApiError>() {
        let class = api_error_class(&api_error.code);
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
    let class = rendered_error_class(&rendered);
    ApiFailureSnapshot {
        class: class.to_string(),
        api_code: None,
        http_status: None,
        content_type: None,
        retryable: !matches!(class, "auth-session" | "permission"),
        retry_after_seconds: None,
        operation: operation.to_string(),
        sample_title: sample_title.map(str::to_string),
        sample_revid,
        message: safe_error_message(&rendered),
        occurred_at: Some(Utc::now()),
    }
}

fn api_error_class(code: &str) -> &'static str {
    match code {
        "badtoken" | "notloggedin" | "assertuserfailed" => "auth-session",
        "permissiondenied" | "cantdelete" => "permission",
        _ => "api-json-error",
    }
}

fn rendered_error_class(rendered: &str) -> &'static str {
    if rendered.contains("Failed to decode JSON response") {
        "decode-error"
    } else if rendered.contains("Permission failure")
        || rendered.contains("Authenticated session lacks")
    {
        "permission"
    } else if rendered.contains("re-login failed") || rendered.contains("CSRF refresh failed") {
        "auth-session"
    } else {
        "unknown"
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
    matches!(code, "maxlag" | "ratelimited" | "readonly")
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
    use std::time::Duration;

    use super::*;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};

    use wiremock::matchers::{body_string_contains, method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn test_env(api_url: String) -> crate::config::EnvConfig {
        crate::config::EnvConfig {
            api_url,
            stream_url: "https://stream.wikimedia.org/v2/stream/recentchange".to_string(),
            bot_username: "Bot@password".to_string(),
            bot_password: "secret".to_string(),
            user_agent: "test-agent".to_string(),
            env_file: std::path::PathBuf::from(".env"),
        }
    }

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

    fn retry_config(max_retries: u32) -> RetryConfig {
        RetryConfig {
            stream_backoff_initial_ms: 1000,
            stream_backoff_max_ms: 10000,
            api_max_retries: max_retries,
            since_recovery_seconds: 0,
        }
    }

    #[tokio::test]
    async fn revision_delete_with_retry_refreshes_badtoken_once_then_succeeds() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=stale"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"badtoken","info":"bad csrf"}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=refreshed"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"revisiondelete":{"status":"Success"},"success":1}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(0)).unwrap();
        let refresh_calls = Arc::new(AtomicUsize::new(0));
        let relogin_calls = Arc::new(AtomicUsize::new(0));
        let mut csrf = "stale".to_string();

        client
            .revision_delete_with_retry(
                &[42],
                "test",
                &mut csrf,
                &retry_config(0),
                {
                    let relogin_calls = Arc::clone(&relogin_calls);
                    move || {
                        let relogin_calls = Arc::clone(&relogin_calls);
                        async move {
                            relogin_calls.fetch_add(1, Ordering::SeqCst);
                            Ok("relogged".to_string())
                        }
                    }
                },
                {
                    let refresh_calls = Arc::clone(&refresh_calls);
                    move || {
                        let refresh_calls = Arc::clone(&refresh_calls);
                        async move {
                            refresh_calls.fetch_add(1, Ordering::SeqCst);
                            Ok("refreshed".to_string())
                        }
                    }
                },
            )
            .await
            .unwrap();

        assert_eq!(csrf, "refreshed");
        assert_eq!(refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(relogin_calls.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn revision_delete_with_retry_relogins_after_second_badtoken() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=stale"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"badtoken","info":"bad csrf"}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=refreshed"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"badtoken","info":"still bad csrf"}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=relogged"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"revisiondelete":{"status":"Success"},"success":1}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(0)).unwrap();
        let refresh_calls = Arc::new(AtomicUsize::new(0));
        let relogin_calls = Arc::new(AtomicUsize::new(0));
        let mut csrf = "stale".to_string();

        client
            .revision_delete_with_retry(
                &[42],
                "test",
                &mut csrf,
                &retry_config(0),
                {
                    let relogin_calls = Arc::clone(&relogin_calls);
                    move || {
                        let relogin_calls = Arc::clone(&relogin_calls);
                        async move {
                            relogin_calls.fetch_add(1, Ordering::SeqCst);
                            Ok("relogged".to_string())
                        }
                    }
                },
                {
                    let refresh_calls = Arc::clone(&refresh_calls);
                    move || {
                        let refresh_calls = Arc::clone(&refresh_calls);
                        async move {
                            refresh_calls.fetch_add(1, Ordering::SeqCst);
                            Ok("refreshed".to_string())
                        }
                    }
                },
            )
            .await
            .unwrap();

        assert_eq!(csrf, "relogged");
        assert_eq!(refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(relogin_calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn revision_delete_with_retry_stops_after_refresh_and_relogin_fail_to_fix_badtoken() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=stale"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"badtoken","info":"bad csrf"}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=refreshed"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"badtoken","info":"still bad csrf"}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .and(body_string_contains("token=relogged"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"badtoken","info":"session still broken"}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(3)).unwrap();
        let refresh_calls = Arc::new(AtomicUsize::new(0));
        let relogin_calls = Arc::new(AtomicUsize::new(0));
        let mut csrf = "stale".to_string();

        let error = client
            .revision_delete_with_retry(
                &[42],
                "test",
                &mut csrf,
                &retry_config(3),
                {
                    let relogin_calls = Arc::clone(&relogin_calls);
                    move || {
                        let relogin_calls = Arc::clone(&relogin_calls);
                        async move {
                            relogin_calls.fetch_add(1, Ordering::SeqCst);
                            Ok("relogged".to_string())
                        }
                    }
                },
                {
                    let refresh_calls = Arc::clone(&refresh_calls);
                    move || {
                        let refresh_calls = Arc::clone(&refresh_calls);
                        async move {
                            refresh_calls.fetch_add(1, Ordering::SeqCst);
                            Ok("refreshed".to_string())
                        }
                    }
                },
            )
            .await
            .unwrap_err();

        let snapshot = classify_api_failure(&error, "revisiondelete", Some("Fixture"), Some(42));
        assert_eq!(csrf, "relogged");
        assert_eq!(refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(relogin_calls.load(Ordering::SeqCst), 1);
        assert_eq!(snapshot.class, "auth-session");
        assert_eq!(snapshot.api_code.as_deref(), Some("badtoken"));
    }

    #[tokio::test]
    async fn revision_delete_with_retry_preserves_permission_error_metadata() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=revisiondelete"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"error":{"code":"permissiondenied","info":"synthetic denied"}}"#,
                "application/json; charset=utf-8",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(3)).unwrap();
        let mut csrf = "csrf".to_string();
        let error = client
            .revision_delete_with_retry(
                &[42],
                "test",
                &mut csrf,
                &retry_config(3),
                || async { Ok("relogged".to_string()) },
                || async { Ok("refreshed".to_string()) },
            )
            .await
            .unwrap_err();

        let snapshot = classify_api_failure(&error, "revisiondelete", Some("Fixture"), Some(42));
        assert_eq!(snapshot.class, "permission");
        assert_eq!(snapshot.api_code.as_deref(), Some("permissiondenied"));
        assert_eq!(snapshot.http_status, Some(200));
        assert_eq!(
            snapshot.content_type.as_deref(),
            Some("application/json; charset=utf-8")
        );
        assert!(!snapshot.retryable);
    }

    #[test]
    fn classify_permission_failure_separately_from_auth_session() {
        let error = anyhow::anyhow!(
            "Permission failure during revisiondelete: You don't have permission to delete or undelete specific revisions of pages."
        );

        let snapshot = classify_api_failure(&error, "revisiondelete", Some("Fixture"), Some(42));

        assert_eq!(snapshot.class, "permission");
        assert!(!snapshot.retryable);
        assert_eq!(snapshot.sample_revid, Some(42));
    }

    #[tokio::test]
    async fn append_text_returns_new_revision_id() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/w/api.php"))
            .and(body_string_contains("action=edit"))
            .and(body_string_contains("bot=1"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"edit":{"result":"Success","newrevid":777}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(0)).unwrap();
        let revid = client
            .append_text("User:Bot/Test", "* smoke", "summary", "csrf")
            .await
            .unwrap();

        assert_eq!(revid, 777);
    }

    #[tokio::test]
    async fn generic_get_retries_retry_after_non_json_429() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("action", "query"))
            .respond_with(
                ResponseTemplate::new(429)
                    .insert_header("content-type", "text/plain; charset=utf-8")
                    .insert_header("retry-after", "0")
                    .set_body_string("too many requests"),
            )
            .expect(1)
            .up_to_n_times(1)
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("action", "query"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{"query":{"tokens":{"logintoken":"login-token"}}}"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(1)).unwrap();

        let token = client.get_login_token().await.unwrap();

        assert_eq!(token, "login-token");
    }

    #[tokio::test]
    async fn generic_get_exhausts_retry_with_classified_non_json_429() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("list", "recentchanges"))
            .respond_with(
                ResponseTemplate::new(429)
                    .insert_header("content-type", "text/plain; charset=utf-8")
                    .insert_header("retry-after", "0")
                    .set_body_string("too many requests"),
            )
            .expect(2)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new_with_retry(&env, &retry_config(1)).unwrap();
        let error = client.fetch_latest_recent_change().await.unwrap_err();
        let snapshot = classify_api_failure(&error, "recentchanges-poll", None, None);

        assert_eq!(snapshot.class, "non-json-response");
        assert_eq!(snapshot.http_status, Some(429));
        assert_eq!(snapshot.retry_after_seconds, Some(0));
        assert!(snapshot.retryable);
    }

    #[tokio::test]
    async fn classifies_non_json_429_with_retry_after_header() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(429)
                    .insert_header("content-type", "text/plain; charset=utf-8")
                    .insert_header("retry-after", "30")
                    .set_body_string("too many requests"),
            )
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new(&env).unwrap();
        let error = client.get_json(&[("action", "query")]).await.unwrap_err();

        let snapshot = classify_api_failure(&error, "fetch-revisions", Some("Title"), Some(42));

        assert_eq!(snapshot.class, "non-json-response");
        assert_eq!(snapshot.http_status, Some(429));
        assert!(
            snapshot
                .content_type
                .as_deref()
                .is_some_and(|value| value.starts_with("text/plain"))
        );
        assert_eq!(snapshot.retry_after_seconds, Some(30));
        assert!(snapshot.retryable);
        assert_eq!(snapshot.sample_title.as_deref(), Some("Title"));
        assert_eq!(snapshot.sample_revid, Some(42));
    }

    #[tokio::test]
    async fn classifies_json_decode_failures_from_json_content_type() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw("{not valid json", "application/json; charset=utf-8"),
            )
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new(&env).unwrap();
        let error = client.get_json(&[("action", "query")]).await.unwrap_err();

        let snapshot = classify_api_failure(&error, "fetch-page", None, None);

        assert_eq!(snapshot.class, "decode-error");
        assert_eq!(snapshot.http_status, Some(200));
        assert_eq!(
            snapshot.content_type.as_deref(),
            Some("application/json; charset=utf-8")
        );
        assert!(!snapshot.retryable);
    }

    #[tokio::test]
    async fn classifies_http_status_failures_even_when_body_is_json() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(503)
                    .insert_header("content-type", "application/json")
                    .set_body_raw(r#"{"batchcomplete":true}"#, "application/json"),
            )
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new(&env).unwrap();
        let error = client.get_json(&[("action", "query")]).await.unwrap_err();

        let snapshot = classify_api_failure(&error, "fetch-page", None, None);

        assert_eq!(snapshot.class, "http-status");
        assert_eq!(snapshot.http_status, Some(503));
        assert_eq!(snapshot.content_type.as_deref(), Some("application/json"));
        assert!(snapshot.retryable);
    }

    #[tokio::test]
    async fn classifies_reqwest_timeout_errors() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/timeout"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_delay(Duration::from_millis(100))
                    .set_body_raw(r#"{"ok":true}"#, "application/json"),
            )
            .mount(&server)
            .await;

        let error = reqwest::Client::builder()
            .timeout(Duration::from_millis(10))
            .build()
            .unwrap()
            .get(format!("{}/timeout", server.uri()))
            .send()
            .await
            .unwrap_err();

        let snapshot = classify_api_failure(&anyhow::Error::new(error), "fetch-page", None, None);

        assert_eq!(snapshot.class, "timeout");
        assert!(snapshot.retryable);
        assert_eq!(snapshot.http_status, None);
    }

    #[tokio::test]
    async fn classifies_reqwest_network_errors() {
        let error = reqwest::Client::new()
            .get("http://127.0.0.1:1")
            .send()
            .await
            .unwrap_err();

        let snapshot = classify_api_failure(&anyhow::Error::new(error), "fetch-page", None, None);

        assert_eq!(snapshot.class, "network");
        assert!(snapshot.retryable);
        assert_eq!(snapshot.http_status, None);
    }

    #[tokio::test]
    async fn fetches_latest_recent_change_probe() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{
                  "query": {
                    "recentchanges": [
                      {
                        "title": "Fixture Page",
                        "timestamp": "2026-04-29T09:10:02Z",
                        "revid": 9000001
                      }
                    ]
                  }
                }"#,
                "application/json",
            ))
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new(&env).unwrap();
        let probe = client.fetch_latest_recent_change().await.unwrap().unwrap();

        assert_eq!(probe.title.as_deref(), Some("Fixture Page"));
        assert_eq!(probe.revid, Some(9000001));
        assert_eq!(probe.timestamp.to_rfc3339(), "2026-04-29T09:10:02+00:00");
    }

    #[tokio::test]
    async fn fetches_recentchanges_window_candidates() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .and(query_param("list", "recentchanges"))
            .and(query_param("rcdir", "older"))
            .respond_with(ResponseTemplate::new(200).set_body_raw(
                r#"{
                  "query": {
                    "recentchanges": [
                      {
                        "title": "Fixture Page",
                        "timestamp": "2026-05-13T12:00:00Z",
                        "revid": 9000001
                      }
                    ]
                  }
                }"#,
                "application/json",
            ))
            .expect(1)
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new(&env).unwrap();
        let start = parse_timestamp("2026-05-13T11:59:00Z").unwrap();
        let end = parse_timestamp("2026-05-13T12:01:00Z").unwrap();
        let window = client
            .fetch_recent_changes_in_window(start, end, 50)
            .await
            .unwrap();

        assert_eq!(window.chunk_count, 1);
        assert!(!window.truncated);
        assert_eq!(window.changes.len(), 1);
        assert_eq!(window.changes[0].title, "Fixture Page");
        assert_eq!(window.changes[0].revid, 9000001);
    }

    #[tokio::test]
    async fn latest_recent_change_probe_allows_empty_results() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/w/api.php"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(r#"{"query":{"recentchanges":[]}}"#, "application/json"),
            )
            .mount(&server)
            .await;

        let env = test_env(format!("{}/w/api.php", server.uri()));
        let client = MediaWikiClient::new(&env).unwrap();

        assert!(client.fetch_latest_recent_change().await.unwrap().is_none());
    }
}
