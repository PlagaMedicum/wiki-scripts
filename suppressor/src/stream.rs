use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use chrono::Utc;
use futures_util::StreamExt;
use metrics::{counter, histogram};
use reqwest_eventsource::{Event, EventSource};
use tracing::{debug, info, warn};

use crate::cache::{CachePersistence, CacheRefreshMode, refresh_cache};
use crate::recentchange::LiveRevisionCandidate;
use crate::runtime::{AppRuntime, RevDelDispatch, RevDelMode};
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
                runtime
                    .mark_realtime_state(
                        "reconnecting",
                        Some(if use_since_recovery {
                            "invalid-resume".to_string()
                        } else {
                            "reconnect-error".to_string()
                        }),
                        Some(error.to_string()),
                        Some("stream-open-failed".to_string()),
                        "real-time stream failed to open".to_string(),
                    )
                    .await;
                warn!(
                    use_since_recovery,
                    error = %error,
                    "failed to open event stream"
                );
                debug!(
                    backoff_ms,
                    use_since_recovery, "waiting before reopening recentchange stream"
                );
                histogram!("stream_reconnect_backoff_ms").record(backoff_ms as f64);
                tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
                backoff_ms = (backoff_ms.saturating_mul(2)).min(max_backoff);
                continue;
            }
        };
        let read_timeout =
            Duration::from_secs(runtime.config.realtime.stream_read_timeout_seconds.max(1));
        loop {
            let item = match tokio::time::timeout(read_timeout, stream.next()).await {
                Ok(Some(item)) => item,
                Ok(None) => {
                    counter!("event_reconnect_total").increment(1);
                    runtime
                        .mark_realtime_state(
                            "reconnecting",
                            Some("stream-closed".to_string()),
                            Some("event stream ended".to_string()),
                            None,
                            "real-time stream closed; reconnecting".to_string(),
                        )
                        .await;
                    break;
                }
                Err(_) => {
                    counter!("event_stream_starvation_total").increment(1);
                    let trigger = "silent-starvation".to_string();
                    runtime
                        .mark_realtime_state(
                            "stale",
                            Some(trigger.clone()),
                            Some(format!("no stream item for {}s", read_timeout.as_secs())),
                            Some("stream-silent".to_string()),
                            stream_silence_notice(read_timeout.as_secs()),
                        )
                        .await;
                    spawn_bounded_catchup(Arc::clone(&runtime), trigger.clone());
                    use_since_recovery = true;
                    break;
                }
            };
            match item {
                Ok(Event::Open) => {
                    use_since_recovery = false;
                    backoff_ms = initial_backoff;
                    info!("recentchange stream opened");
                    runtime.mark_realtime_stream_open().await;
                    spawn_bounded_catchup(Arc::clone(&runtime), "startup".to_string());
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
                    if let Some(event_id) =
                        handle_recentchange_event(&runtime, event, Some(&message.id)).await?
                    {
                        last_event_id = Some(event_id.clone());
                        if !runtime.dry_run {
                            save_text_atomic(&runtime.paths.last_event_id_file, &event_id)?;
                        }
                    }
                }
                Err(error) => {
                    counter!("event_reconnect_total").increment(1);
                    use_since_recovery =
                        should_use_since_recovery(resume_event_id.as_deref(), &error);
                    let trigger = if use_since_recovery {
                        "invalid-resume"
                    } else {
                        "reconnect-error"
                    };
                    runtime
                        .mark_realtime_state(
                            "reconnecting",
                            Some(trigger.to_string()),
                            Some(error.to_string()),
                            Some("stream-error".to_string()),
                            "real-time stream reconnecting after error".to_string(),
                        )
                        .await;
                    spawn_bounded_catchup(Arc::clone(&runtime), trigger.to_string());
                    warn!(
                        use_since_recovery,
                        error = %error,
                        "event stream reconnecting after error"
                    );
                    break;
                }
            }
        }
        debug!(
            backoff_ms,
            use_since_recovery, "waiting before reconnecting to recentchange stream"
        );
        histogram!("stream_reconnect_backoff_ms").record(backoff_ms as f64);
        tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
        backoff_ms = (backoff_ms.saturating_mul(2)).min(max_backoff);
    }
}

fn spawn_bounded_catchup(runtime: Arc<AppRuntime>, trigger: String) {
    tokio::spawn(async move {
        if let Err(error) = crate::catchup::run_default_catchup(&runtime, trigger.clone()).await {
            warn!(error = %error, trigger = %trigger, "bounded catch-up failed");
            runtime
                .mark_realtime_state(
                    "unhealthy",
                    Some(trigger),
                    Some("catch-up failed".to_string()),
                    Some("catchup-failed".to_string()),
                    format!("bounded catch-up failed: {error}"),
                )
                .await;
        }
    });
}

pub async fn handle_recentchange_event(
    runtime: &Arc<AppRuntime>,
    event: crate::recentchange::RecentChangeEvent,
    sse_id: Option<&str>,
) -> Result<Option<String>> {
    if runtime.config.matching.drop_canary && event.is_canary() {
        return Ok(None);
    }
    if !event.matches_wiki(
        &runtime.config.wiki.wiki_code,
        &runtime.config.wiki.server_name,
    ) {
        return Ok(None);
    }
    counter!("events_bewiki_total").increment(1);
    let event_id = event.event_id(sse_id);
    runtime.mark_realtime_event(event_id.clone()).await;
    if let Some(title) = event.title.as_deref() {
        let normalized_title = crate::titles::normalize_title(title);
        let source_title = runtime.cache.read().await.source_title_normalized.clone();
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
            return Ok(event_id);
        }
    }
    if !event.is_revision_event() {
        return Ok(event_id);
    }
    let Some(candidate) = event.to_candidate(sse_id) else {
        return Ok(event_id);
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
        return Ok(event_id);
    }
    counter!("events_matched_total").increment(1);
    info!(
        title = %candidate.title,
        revid = candidate.revid,
        old_revid = ?candidate.old_revid,
        event_id = ?candidate.event_id,
        "matched live watched revision"
    );
    runtime
        .mark_realtime_match(candidate.title.clone(), candidate.revid)
        .await;
    handle_live_candidate(runtime, candidate, Some(Utc::now())).await?;
    Ok(event_id)
}

async fn handle_live_candidate(
    runtime: &Arc<AppRuntime>,
    candidate: LiveRevisionCandidate,
    observed_at: Option<chrono::DateTime<Utc>>,
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
        .dispatch_action(RevDelDispatch {
            title: candidate.title,
            revids: vec![candidate.revid],
            event_id: candidate.event_id,
            user: candidate.user,
            comment: candidate.comment,
            mode: RevDelMode::Live,
            observed_at,
            recovery_trigger: None,
            completion_tx: None,
        })
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

pub fn stream_silence_notice(seconds: u64) -> String {
    format!("real-time stream silent for {seconds}s")
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

    #[test]
    fn stream_starvation_notice_is_actionable() {
        assert_eq!(stream_silence_notice(10), "real-time stream silent for 10s");
    }
}
