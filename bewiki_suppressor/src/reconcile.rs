use std::cmp::max;
use std::collections::BTreeSet;
use std::sync::Arc;

use anyhow::Result;
use chrono::{DateTime, NaiveTime, TimeZone, Utc};
use chrono_tz::Tz;
use futures_util::StreamExt;
use rand::Rng;
use tokio::sync::Mutex;
use tracing::{debug, info, warn};

use crate::cache::{CachePersistence, enrich_redirects, fetch_redirect_target};
use crate::runtime::{ReconcilePassContext, ReconciliationRuntime, RevDelMode};
use crate::state::{NightlySweepProgress, PageCheckpoint, save_json_atomic};

#[derive(Copy, Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum ReconcileMode {
    CurrentDay,
    Full,
}

#[derive(Default)]
struct CoordinatorState {
    active: bool,
    pending: Option<ReconcileMode>,
}

#[derive(Default)]
pub struct ReconcileCoordinator {
    state: Mutex<CoordinatorState>,
}

impl ReconcileCoordinator {
    pub async fn request_run(
        self: &Arc<Self>,
        runtime: Arc<ReconciliationRuntime>,
        mode: ReconcileMode,
    ) {
        let mut guard = self.state.lock().await;
        if guard.active {
            let queued_mode = guard.pending.unwrap_or(mode).max(mode);
            guard.pending = Some(queued_mode);
            drop(guard);
            runtime
                .update_runtime_status(move |status| {
                    status.reconciliation.queued_mode = Some(queued_mode.label().to_string());
                    status.last_notice = Some(format!(
                        "queued {} reconciliation rerun",
                        queued_mode.label()
                    ));
                    status.last_notice_at = Some(Utc::now());
                })
                .await;
            info!(
                requested_mode = %mode.label(),
                queued_mode = %queued_mode.label(),
                "queued reconciliation rerun because another pass is active"
            );
            return;
        }
        guard.active = true;
        drop(guard);

        let coordinator = Arc::clone(self);
        tokio::spawn(async move {
            let mut current_mode = mode;
            loop {
                if let Err(error) = runtime.run_reconciliation_pass(current_mode).await {
                    warn!("reconciliation {:?} failed: {error:#}", current_mode);
                }
                let mut state = coordinator.state.lock().await;
                if let Some(next_mode) = state.pending.take() {
                    current_mode = next_mode;
                    drop(state);
                    continue;
                }
                state.active = false;
                break;
            }
        });
    }
}

pub async fn reconciliation_loop(ctx: Arc<ReconcilePassContext>) -> Result<()> {
    let listed_titles = ctx.listed_titles.clone();
    ctx.update_runtime_status(|status| {
        status.reconciliation.phase = Some("resolving redirects".to_string());
        status.reconciliation.total_titles = listed_titles.len();
        status.reconciliation.completed_titles = 0;
        status.reconciliation.phase_total = listed_titles.len();
        status.reconciliation.phase_completed = 0;
        status.reconciliation.current_title = None;
        status.reconciliation.queued_mode = None;
    })
    .await;
    if listed_titles.is_empty() {
        info!(
            mode = ?ctx.mode,
            "skipping reconciliation because no listed titles are cached"
        );
        return Ok(());
    }
    info!(
        mode = ?ctx.mode,
        listed_titles = listed_titles.len(),
        "starting reconciliation pass"
    );

    let listed_titles_set = listed_titles.iter().cloned().collect::<BTreeSet<_>>();
    let mut progress = ctx.progress.lock().await.clone();
    progress
        .pages
        .retain(|title, _| listed_titles_set.contains(title));
    let shared_progress = Arc::new(Mutex::new(progress));
    let mut discovered_redirects = std::collections::BTreeMap::new();
    for (index, title) in listed_titles.iter().enumerate() {
        ctx.update_runtime_status({
            let title = title.clone();
            move |status| {
                status.reconciliation.current_title = Some(title);
                status.reconciliation.phase_completed = index;
            }
        })
        .await;
        if let Some(target) = fetch_redirect_target(&ctx.client, title).await? {
            discovered_redirects.insert(title.clone(), target);
        }
        ctx.update_runtime_status(move |status| {
            status.reconciliation.phase_completed = index + 1;
        })
        .await;
    }
    ctx.update_runtime_status(|status| {
        status.reconciliation.phase = Some("checking page revisions".to_string());
        status.reconciliation.phase_completed = 0;
        status.reconciliation.phase_total = status.reconciliation.total_titles;
        status.reconciliation.current_title = None;
        status.last_notice =
            Some("redirect discovery finished; checking page revisions".to_string());
        status.last_notice_at = Some(Utc::now());
    })
    .await;

    futures_util::stream::iter(listed_titles.into_iter())
        .for_each_concurrent(ctx.page_concurrency, |title| {
            let ctx = Arc::clone(&ctx);
            let shared_progress = Arc::clone(&shared_progress);
            async move {
                ctx.update_runtime_status({
                    let title = title.clone();
                    move |status| {
                        status.reconciliation.current_title = Some(title);
                    }
                })
                .await;
                if let Err(error) = reconcile_title(&ctx, &shared_progress, &title).await {
                    warn!("reconciliation for {title} failed: {error:#}");
                }
                ctx.update_runtime_status(|status| {
                    status.reconciliation.completed_titles += 1;
                    status.reconciliation.phase_completed += 1;
                })
                .await;
            }
        })
        .await;

    let progress = shared_progress.lock().await.clone();
    *ctx.progress.lock().await = progress.clone();
    if matches!(ctx.persistence, CachePersistence::Persist) {
        save_json_atomic(&ctx.paths.nightly_sweep_progress_file, &progress)?;
    }
    info!(
        mode = ?ctx.mode,
        checkpoint_pages = progress.pages.len(),
        redirects = discovered_redirects.len(),
        "reconciliation pass completed"
    );
    enrich_redirects(
        &ctx.cache,
        &ctx.paths,
        std::mem::take(&mut discovered_redirects),
        ctx.persistence,
    )
    .await?;
    Ok(())
}

async fn reconcile_title(
    ctx: &Arc<ReconcilePassContext>,
    shared_progress: &Arc<Mutex<NightlySweepProgress>>,
    title: &str,
) -> Result<()> {
    let Some(_page_guard) = ctx.page_locks.try_lock(title.to_string()) else {
        return Ok(());
    };
    let checkpoint = {
        shared_progress
            .lock()
            .await
            .pages
            .get(title)
            .cloned()
            .unwrap_or_default()
    };
    let since = reconciliation_since(ctx.mode, checkpoint.last_reconciled_at, &ctx.timezone)?;
    let revisions = ctx.client.fetch_revisions(title, since).await?;
    let revisions_checked = revisions.len();
    metrics::counter!("nightly_sweep_pages_total").increment(1);
    metrics::counter!("nightly_sweep_revisions_checked_total").increment(revisions_checked as u64);

    let mut to_hide = Vec::new();
    let mut last_seen_timestamp = checkpoint.last_reconciled_at;
    let mut last_seen_revid = checkpoint.last_reconciled_revid;
    for revision in revisions {
        last_seen_timestamp = Some(
            last_seen_timestamp
                .map(|timestamp| timestamp.max(revision.timestamp))
                .unwrap_or(revision.timestamp),
        );
        last_seen_revid = Some(revision.revid);
        if !revision.user_hidden || !revision.comment_hidden {
            to_hide.push(revision.revid);
        }
    }

    for batch in to_hide.chunks(ctx.batch_limit) {
        if !batch.is_empty() {
            metrics::counter!("nightly_sweep_revisions_hidden_total").increment(batch.len() as u64);
            debug!(
                title = %title,
                batch_revids = ?batch,
                mode = ?ctx.mode,
                "queueing reconciliation revisiondelete batch"
            );
            ctx.actions
                .dispatch_action_batch(
                    title.to_string(),
                    batch.to_vec(),
                    None,
                    None,
                    None,
                    RevDelMode::Reconciliation,
                )
                .await?;
            tokio::time::sleep(std::time::Duration::from_millis(ctx.batch_sleep_ms)).await;
        }
    }
    info!(
        title = %title,
        revisions_checked,
        revisions_to_hide = to_hide.len(),
        last_reconciled_revid = ?last_seen_revid,
        "reconciled listed title"
    );

    let next_checkpoint =
        next_checkpoint(ctx.mode, &checkpoint, last_seen_timestamp, last_seen_revid);
    shared_progress
        .lock()
        .await
        .pages
        .insert(title.to_string(), next_checkpoint);
    Ok(())
}

pub async fn next_nightly_delay(timezone: &str, start_time: &str) -> Result<std::time::Duration> {
    let tz: Tz = timezone.parse()?;
    let local_now = Utc::now().with_timezone(&tz);
    let start = NaiveTime::parse_from_str(start_time, "%H:%M")?;
    let today = local_now.date_naive();
    let mut target = tz
        .from_local_datetime(&today.and_time(start))
        .single()
        .ok_or_else(|| anyhow::anyhow!("Unable to resolve nightly local time"))?;
    if target <= local_now {
        target = tz
            .from_local_datetime(&(today.succ_opt().unwrap().and_time(start)))
            .single()
            .ok_or_else(|| anyhow::anyhow!("Unable to resolve next nightly local time"))?;
    }
    Ok((target.with_timezone(&Utc) - Utc::now())
        .to_std()
        .unwrap_or_else(|_| std::time::Duration::from_secs(0)))
}

pub fn next_current_day_delay(
    min_delay_seconds: u64,
    max_delay_seconds: u64,
) -> std::time::Duration {
    let seconds = rand::thread_rng().gen_range(min_delay_seconds..=max_delay_seconds);
    std::time::Duration::from_secs(seconds)
}

fn current_local_midnight(timezone: &str) -> Result<DateTime<Utc>> {
    let tz: Tz = timezone.parse()?;
    let local_now = Utc::now().with_timezone(&tz);
    let midnight = tz
        .from_local_datetime(&local_now.date_naive().and_hms_opt(0, 0, 0).unwrap())
        .single()
        .ok_or_else(|| anyhow::anyhow!("Unable to resolve local midnight"))?;
    Ok(midnight.with_timezone(&Utc))
}

fn reconciliation_since(
    mode: ReconcileMode,
    previous: Option<DateTime<Utc>>,
    timezone: &str,
) -> Result<Option<DateTime<Utc>>> {
    match (mode, previous) {
        (_, None) => Ok(None),
        (ReconcileMode::Full, Some(previous)) => Ok(Some(previous)),
        (ReconcileMode::CurrentDay, Some(previous)) => {
            let midnight = current_local_midnight(timezone)?;
            Ok(Some(max(previous, midnight)))
        }
    }
}

pub(crate) fn revisiondelete_batch_limit(has_high_limits: bool) -> usize {
    if has_high_limits { 500 } else { 50 }
}

fn next_checkpoint(
    mode: ReconcileMode,
    checkpoint: &PageCheckpoint,
    last_seen_timestamp: Option<DateTime<Utc>>,
    last_seen_revid: Option<u64>,
) -> PageCheckpoint {
    PageCheckpoint {
        last_full_check_at: match mode {
            ReconcileMode::Full => last_seen_timestamp
                .or(checkpoint.last_full_check_at)
                .or(Some(Utc::now())),
            ReconcileMode::CurrentDay => checkpoint.last_full_check_at,
        },
        last_reconciled_at: last_seen_timestamp.or(Some(Utc::now())),
        last_reconciled_revision_timestamp: last_seen_timestamp,
        last_reconciled_revid: last_seen_revid,
    }
}

impl ReconcileMode {
    pub fn label(self) -> &'static str {
        match self {
            ReconcileMode::CurrentDay => "current-day",
            ReconcileMode::Full => "nightly",
        }
    }
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::*;

    #[test]
    fn batch_limit_uses_high_limit_rights() {
        assert_eq!(revisiondelete_batch_limit(true), 500);
        assert_eq!(revisiondelete_batch_limit(false), 50);
    }

    #[test]
    fn full_mode_since_keeps_previous_checkpoint() {
        let previous = Utc.with_ymd_and_hms(2026, 4, 7, 21, 0, 0).unwrap();
        let since =
            reconciliation_since(ReconcileMode::Full, Some(previous), "Europe/Warsaw").unwrap();

        assert_eq!(since, Some(previous));
    }

    #[test]
    fn next_checkpoint_preserves_full_check_for_current_day_runs() {
        let previous_full = Utc.with_ymd_and_hms(2026, 4, 6, 4, 0, 0).unwrap();
        let last_seen = Utc.with_ymd_and_hms(2026, 4, 8, 8, 30, 0).unwrap();
        let checkpoint = PageCheckpoint {
            last_full_check_at: Some(previous_full),
            ..PageCheckpoint::default()
        };

        let next = next_checkpoint(
            ReconcileMode::CurrentDay,
            &checkpoint,
            Some(last_seen),
            Some(123),
        );

        assert_eq!(next.last_full_check_at, Some(previous_full));
        assert_eq!(next.last_reconciled_at, Some(last_seen));
        assert_eq!(next.last_reconciled_revision_timestamp, Some(last_seen));
        assert_eq!(next.last_reconciled_revid, Some(123));
    }

    #[test]
    fn next_checkpoint_updates_full_check_for_full_runs() {
        let last_seen = Utc.with_ymd_and_hms(2026, 4, 8, 8, 30, 0).unwrap();
        let checkpoint = PageCheckpoint::default();

        let next = next_checkpoint(ReconcileMode::Full, &checkpoint, Some(last_seen), Some(123));

        assert_eq!(next.last_full_check_at, Some(last_seen));
        assert_eq!(next.last_reconciled_at, Some(last_seen));
        assert_eq!(next.last_reconciled_revision_timestamp, Some(last_seen));
        assert_eq!(next.last_reconciled_revid, Some(123));
    }
}
