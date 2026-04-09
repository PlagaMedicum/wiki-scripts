use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use futures_util::StreamExt;
use metrics::counter;
use reqwest_eventsource::{Event, EventSource};
use tracing::{debug, info, warn};

use crate::cache::{CachePersistence, CacheRefreshMode, refresh_cache};
use crate::recentchange::LiveRevisionCandidate;
use crate::runtime::{AppRuntime, RevDelMode};
use crate::state::{load_text, save_text_atomic};

pub fn spawn_stream_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        if let Err(error) = stream_loop(runtime).await {
            tracing::error!("stream loop failed: {error:#}");
        }
    });
}

pub async fn stream_loop(runtime: Arc<AppRuntime>) -> Result<()> {
    let mut last_event_id = if runtime.dry_run {
        None
    } else {
        load_text(&runtime.paths.last_event_id_file)?
    };
    let mut use_since_recovery = false;
    let initial_backoff = runtime.config.retry.stream_backoff_initial_ms;
    let max_backoff = runtime
        .config
        .retry
        .stream_backoff_max_ms
        .max(initial_backoff);
    let mut backoff_ms = initial_backoff;
    loop {
        let resume_event_id = if use_since_recovery {
            None
        } else {
            last_event_id.clone()
        };
        let url = runtime.client.build_stream_url(
            resume_event_id.as_deref(),
            if use_since_recovery {
                Some(runtime.config.retry.since_recovery_seconds)
            } else {
                None
            },
        )?;
        info!(
            resume_event_id = ?resume_event_id,
            use_since_recovery,
            stream_url = %url,
            "connecting to recentchange stream"
        );
        let mut request = reqwest::Client::builder()
            .build()?
            .get(url)
            .header("Accept", "text/event-stream")
            .header("User-Agent", runtime.client.user_agent());
        if let Some(event_id) = resume_event_id.as_deref() {
            request = request.header("Last-Event-ID", event_id);
        }

        let mut stream = match EventSource::new(request) {
            Ok(stream) => stream,
            Err(error) => {
                counter!("event_reconnect_total").increment(1);
                use_since_recovery = should_use_since_recovery(resume_event_id.as_deref(), &error);
                warn!(
                    use_since_recovery,
                    error = %error,
                    "failed to open event stream"
                );
                tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
                backoff_ms = (backoff_ms.saturating_mul(2)).min(max_backoff);
                continue;
            }
        };
        while let Some(item) = stream.next().await {
            match item {
                Ok(Event::Open) => {
                    use_since_recovery = false;
                    backoff_ms = initial_backoff;
                    info!("recentchange stream opened");
                    continue;
                }
                Ok(Event::Message(message)) => {
                    use_since_recovery = false;
                    backoff_ms = initial_backoff;
                    counter!("events_received_total").increment(1);
                    let event = match crate::recentchange::RecentChangeEvent::parse(&message.data) {
                        Ok(event) => event,
                        Err(error) => {
                            warn!("failed to parse event: {error:#}");
                            continue;
                        }
                    };
                    if runtime.config.matching.drop_canary && event.is_canary() {
                        continue;
                    }
                    if !event.matches_wiki(
                        &runtime.config.wiki.wiki_code,
                        &runtime.config.wiki.server_name,
                    ) {
                        continue;
                    }
                    counter!("events_bewiki_total").increment(1);
                    let event_id = event.event_id(Some(&message.id));
                    if let Some(ref event_id) = event_id {
                        last_event_id = Some(event_id.clone());
                        if !runtime.dry_run {
                            save_text_atomic(&runtime.paths.last_event_id_file, event_id)?;
                        }
                    }
                    if let Some(title) = event.title.as_deref() {
                        let normalized_title = crate::titles::normalize_title(title);
                        let source_title =
                            runtime.cache.read().await.source_title_normalized.clone();
                        if normalized_title == source_title {
                            info!(title = %title, "source suppression list page changed; refreshing cache");
                            let _ = refresh_cache(
                                &runtime.cache,
                                &runtime.client,
                                &runtime.config,
                                &runtime.paths,
                                CacheRefreshMode::Forced,
                                if runtime.dry_run {
                                    CachePersistence::Ephemeral
                                } else {
                                    CachePersistence::Persist
                                },
                            )
                            .await;
                            continue;
                        }
                    }
                    if !event.is_revision_event() {
                        continue;
                    }
                    let Some(candidate) = event.to_candidate(Some(&message.id)) else {
                        continue;
                    };
                    if !runtime
                        .cache
                        .read()
                        .await
                        .watched_set
                        .contains(&candidate.normalized_title)
                    {
                        debug!(
                            title = %candidate.title,
                            normalized_title = %candidate.normalized_title,
                            "ignoring revision event because title is not in watched set"
                        );
                        continue;
                    }
                    counter!("events_matched_total").increment(1);
                    info!(
                        title = %candidate.title,
                        revid = candidate.revid,
                        old_revid = ?candidate.old_revid,
                        user = ?candidate.user,
                        event_id = ?candidate.event_id,
                        "matched live watched revision"
                    );
                    handle_live_candidate(&runtime, candidate).await?;
                }
                Err(error) => {
                    counter!("event_reconnect_total").increment(1);
                    use_since_recovery =
                        should_use_since_recovery(resume_event_id.as_deref(), &error);
                    warn!(
                        use_since_recovery,
                        error = %error,
                        "event stream reconnecting after error"
                    );
                    break;
                }
            }
        }
        tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
        backoff_ms = (backoff_ms.saturating_mul(2)).min(max_backoff);
    }
}

async fn handle_live_candidate(
    runtime: &Arc<AppRuntime>,
    candidate: LiveRevisionCandidate,
) -> Result<()> {
    if runtime
        .reconcile
        .actions
        .contains_processed(candidate.revid)
        .await
    {
        return Ok(());
    }
    runtime
        .reconcile
        .actions
        .dispatch_action_batch(
            candidate.title,
            vec![candidate.revid],
            candidate.event_id,
            candidate.user,
            candidate.comment,
            RevDelMode::Live,
        )
        .await
}

pub fn should_use_since_recovery(
    resume_event_id: Option<&str>,
    error: &dyn std::fmt::Display,
) -> bool {
    if resume_event_id.is_none() {
        return false;
    }
    let rendered = error.to_string().to_ascii_lowercase();
    rendered.contains("400")
        || rendered.contains("410")
        || rendered.contains("gone")
        || rendered.contains("last-event-id")
        || rendered.contains("invalid")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn since_recovery_is_disabled_without_resume_id() {
        assert!(!should_use_since_recovery(None, &"410 Gone"));
    }

    #[test]
    fn since_recovery_is_enabled_for_resume_errors() {
        assert!(should_use_since_recovery(Some("abc"), &"410 Gone"));
        assert!(should_use_since_recovery(
            Some("abc"),
            &"invalid Last-Event-ID"
        ));
    }

    #[test]
    fn since_recovery_is_disabled_for_generic_errors() {
        assert!(!should_use_since_recovery(
            Some("abc"),
            &"temporary network timeout"
        ));
    }
}
