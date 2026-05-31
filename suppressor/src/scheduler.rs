#![allow(dead_code)]

use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use chrono::{DateTime, NaiveTime, TimeDelta, TimeZone, Utc};
use chrono_tz::Tz;
use metrics::histogram;
use rand::Rng;
use tracing::{debug, info, warn};

use crate::cache::{CachePersistence, CacheRefreshMode, refresh_cache};
use crate::mw_api::classify_api_failure;
use crate::reconcile::ReconcileMode;
use crate::runtime::AppRuntime;

pub fn spawn_metadata_refresh_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        info!(
            every_seconds = runtime.config.suppression_list.metadata_recheck_seconds,
            "metadata recheck loop started"
        );
        let mut last_failure_key: Option<String> = None;
        let mut repeated_failure_count: usize = 0;
        loop {
            let result = refresh_cache(
                &runtime.cache,
                &runtime.client,
                &runtime.config,
                &runtime.paths,
                CacheRefreshMode::Automatic,
                if runtime.dry_run {
                    CachePersistence::Ephemeral
                } else {
                    CachePersistence::Persist
                },
            )
            .await;
            match result {
                Ok(_) => {
                    if repeated_failure_count > 0 {
                        info!(
                            count = repeated_failure_count,
                            "metadata recheck recovered after repeated failures"
                        );
                        runtime
                            .record_notice(
                                "metadata recheck recovered; watched-page cache is readable",
                            )
                            .await;
                    }
                    last_failure_key = None;
                    repeated_failure_count = 0;
                }
                Err(error) => {
                    let snapshot =
                        classify_api_failure(&error, "source-metadata-recheck", None, None);
                    let failure_key = format!(
                        "{}|{}|{}",
                        snapshot.class,
                        snapshot.api_code.as_deref().unwrap_or(""),
                        snapshot
                            .http_status
                            .map(|status| status.to_string())
                            .unwrap_or_default()
                    );
                    if last_failure_key.as_deref() == Some(failure_key.as_str()) {
                        repeated_failure_count += 1;
                    } else {
                        last_failure_key = Some(failure_key);
                        repeated_failure_count = 1;
                    }
                    if repeated_failure_count == 1 || repeated_failure_count.is_multiple_of(6) {
                        warn!(
                            count = repeated_failure_count,
                            class = %snapshot.class,
                            api_code = ?snapshot.api_code,
                            http_status = ?snapshot.http_status,
                            retry_after_seconds = ?snapshot.retry_after_seconds,
                            "metadata recheck failed"
                        );
                    }
                    runtime.record_api_failure(snapshot).await;
                }
            }
            tokio::time::sleep(Duration::from_secs(
                runtime.config.suppression_list.metadata_recheck_seconds,
            ))
            .await;
        }
    });
}

pub fn spawn_nightly_reconciliation_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        if !runtime.config.nightly_sweep.enabled {
            info!("nightly reconciliation loop disabled");
            return;
        }
        info!(
            timezone = %runtime.config.nightly_sweep.timezone,
            start_time = %runtime.config.nightly_sweep.start_time,
            randomized_window_minutes = runtime.config.nightly_sweep.randomized_window_minutes,
            page_concurrency = runtime.config.nightly_sweep.page_concurrency,
            "nightly reconciliation loop started"
        );
        loop {
            match next_nightly_delay(
                &runtime.config.nightly_sweep.timezone,
                &runtime.config.nightly_sweep.start_time,
                runtime.config.nightly_sweep.randomized_window_minutes,
            )
            .await
            {
                Ok(delay) => {
                    debug!(
                        delay_seconds = delay.as_secs(),
                        "waiting for next nightly reconciliation window"
                    );
                    histogram!("nightly_scheduler_delay_seconds").record(delay.as_secs_f64());
                    tokio::time::sleep(delay).await;
                }
                Err(error) => {
                    warn!("nightly scheduler failed: {error:#}");
                    tokio::time::sleep(Duration::from_secs(60)).await;
                }
            }
            if let Some(delay) =
                scheduler_backoff_delay(Utc::now(), runtime.current_backoff_until().await)
                    .filter(|delay| !delay.is_zero())
            {
                runtime
                    .record_notice(format!(
                        "full watched-set recheck deferred by backoff for {}s",
                        delay.as_secs()
                    ))
                    .await;
                tokio::time::sleep(delay).await;
            }
            runtime.reconcile.request_run(ReconcileMode::Full).await;
        }
    });
}

pub fn spawn_current_day_reconciliation_loop(runtime: Arc<AppRuntime>) {
    tokio::spawn(async move {
        if !runtime.config.daytime_verification.enabled {
            info!("rolling last-24h verification loop disabled");
            return;
        }
        info!(
            min_delay_seconds = runtime.config.daytime_verification.min_delay_seconds,
            max_delay_seconds = runtime.config.daytime_verification.max_delay_seconds,
            window_hours = runtime.config.daytime_verification.window_hours,
            "rolling last-24h verification loop started"
        );
        loop {
            let delay = next_current_day_delay(
                runtime.config.daytime_verification.min_delay_seconds,
                runtime.config.daytime_verification.max_delay_seconds,
            );
            debug!(
                delay_seconds = delay.as_secs(),
                "waiting for next rolling last-24h verification run"
            );
            histogram!("last_24h_scheduler_delay_seconds").record(delay.as_secs_f64());
            tokio::time::sleep(delay).await;
            if let Some(delay) =
                scheduler_backoff_delay(Utc::now(), runtime.current_backoff_until().await)
                    .filter(|delay| !delay.is_zero())
            {
                runtime
                    .record_notice(format!(
                        "Last 24 hours verification deferred by backoff for {}s",
                        delay.as_secs()
                    ))
                    .await;
                tokio::time::sleep(delay).await;
            }
            runtime
                .reconcile
                .request_run(ReconcileMode::CurrentDay)
                .await;
        }
    });
}

pub(crate) fn scheduler_backoff_delay(
    now: DateTime<Utc>,
    backoff_until: Option<DateTime<Utc>>,
) -> Option<Duration> {
    backoff_until.and_then(|until| {
        if until <= now {
            None
        } else {
            until.signed_duration_since(now).to_std().ok()
        }
    })
}

pub(crate) fn rolling_window_start(now: DateTime<Utc>, window_hours: u64) -> DateTime<Utc> {
    now - TimeDelta::hours(window_hours as i64)
}

pub(crate) fn next_current_day_delay(
    min_delay_seconds: u64,
    max_delay_seconds: u64,
) -> std::time::Duration {
    let seconds = rand::thread_rng().gen_range(min_delay_seconds..=max_delay_seconds);
    std::time::Duration::from_secs(seconds)
}

pub(crate) async fn next_nightly_delay(
    timezone: &str,
    start_time: &str,
    randomized_window_minutes: u64,
) -> Result<std::time::Duration> {
    next_nightly_delay_at(Utc::now(), timezone, start_time, randomized_window_minutes)
}

pub(crate) fn next_nightly_delay_at(
    now_utc: DateTime<Utc>,
    timezone: &str,
    start_time: &str,
    randomized_window_minutes: u64,
) -> Result<std::time::Duration> {
    let tz: Tz = timezone.parse()?;
    let local_now = now_utc.with_timezone(&tz);
    let start = NaiveTime::parse_from_str(start_time, "%H:%M")?;
    let offset_minutes = if randomized_window_minutes == 0 {
        0
    } else {
        rand::thread_rng().gen_range(0..=randomized_window_minutes)
    };
    let today = local_now.date_naive();
    let mut target = tz
        .from_local_datetime(&(today.and_time(start) + TimeDelta::minutes(offset_minutes as i64)))
        .single()
        .ok_or_else(|| anyhow::anyhow!("Unable to resolve nightly local time"))?;
    if target <= local_now {
        target = tz
            .from_local_datetime(
                &(today.succ_opt().unwrap().and_time(start)
                    + TimeDelta::minutes(offset_minutes as i64)),
            )
            .single()
            .ok_or_else(|| anyhow::anyhow!("Unable to resolve next nightly local time"))?;
    }
    Ok((target.with_timezone(&Utc) - now_utc)
        .to_std()
        .unwrap_or_else(|_| std::time::Duration::from_secs(0)))
}

#[cfg(test)]
mod tests {
    use chrono::{Duration as ChronoDuration, TimeZone};

    use super::*;

    #[test]
    fn scheduler_backoff_delay_is_none_without_active_backoff() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();

        assert_eq!(scheduler_backoff_delay(now, None), None);
        assert_eq!(
            scheduler_backoff_delay(now, Some(now - ChronoDuration::seconds(1))),
            None
        );
    }

    #[test]
    fn scheduler_backoff_delay_uses_remaining_backoff() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 0, 0).unwrap();
        let until = now + ChronoDuration::seconds(37);

        assert_eq!(
            scheduler_backoff_delay(now, Some(until)),
            Some(Duration::from_secs(37))
        );
    }

    #[test]
    fn daytime_delay_stays_inside_configured_range() {
        for _ in 0..64 {
            let delay = next_current_day_delay(10, 20);
            assert!(delay >= Duration::from_secs(10));
            assert!(delay <= Duration::from_secs(20));
        }
    }

    #[test]
    fn daytime_delay_uses_exact_value_for_fixed_interval() {
        assert_eq!(next_current_day_delay(42, 42), Duration::from_secs(42));
    }

    #[test]
    fn rolling_window_start_uses_exact_last_24_hours_window() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 9, 30, 0).unwrap();
        let start = rolling_window_start(now, 24);

        assert_eq!(start, Utc.with_ymd_and_hms(2026, 4, 28, 9, 30, 0).unwrap());
    }

    #[test]
    fn nightly_delay_rolls_to_next_local_night_after_today_window_has_passed() {
        let now = Utc.with_ymd_and_hms(2026, 4, 29, 4, 45, 0).unwrap();
        let delay = next_nightly_delay_at(now, "Europe/Warsaw", "02:00", 180).unwrap();

        assert!(delay >= Duration::from_secs(19 * 3600 + 15 * 60));
        assert!(delay <= Duration::from_secs(22 * 3600 + 15 * 60));
    }

    #[test]
    fn nightly_delay_stays_inside_expected_randomized_window() {
        let now = Utc.with_ymd_and_hms(2026, 4, 28, 21, 0, 0).unwrap();
        let delay = next_nightly_delay_at(now, "Europe/Warsaw", "02:00", 180).unwrap();

        assert!(delay >= Duration::from_secs(3 * 3600));
        assert!(delay <= Duration::from_secs(6 * 3600));
    }
}
