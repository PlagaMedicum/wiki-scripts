use std::path::Path;

use anyhow::Result;
use chrono::{DateTime, TimeDelta, Utc};
use serde::{Deserialize, Serialize};

use crate::mw_api::revision_url;
use crate::state::{ApiFailureSnapshot, ProcessedRevidsState, UnresolvedExposureItem, load_json};

pub(crate) const STATE_FILE_NAME: &str = "simple_daemon_state.json";
pub(crate) const PROCESSED_CAPACITY: usize = 10_000;
pub(crate) const MAX_PENDING_ITEMS: usize = 5_000;
pub(crate) const MAX_QUARANTINED_ITEMS: usize = 5_000;

const PENDING_RETRY_SECONDS: i64 = 30;

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub(crate) struct SimpleDaemonState {
    pub(crate) last_successful_poll_at: Option<DateTime<Utc>>,
    pub(crate) last_observed_change_at: Option<DateTime<Utc>>,
    pub(crate) last_successful_hide_at: Option<DateTime<Utc>>,
    pub(crate) last_successful_hide_title: Option<String>,
    pub(crate) last_successful_hide_revid: Option<u64>,
    pub(crate) last_successful_hide_source_label: Option<String>,
    pub(crate) latest_error: Option<ApiFailureSnapshot>,
    pub(crate) pending: Vec<PendingHide>,
    pub(crate) quarantined: Vec<PendingHide>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub(crate) struct PendingHide {
    pub(crate) title: String,
    pub(crate) revid: u64,
    pub(crate) observed_at: Option<DateTime<Utc>>,
    pub(crate) first_failed_at: DateTime<Utc>,
    pub(crate) last_failed_at: DateTime<Utc>,
    pub(crate) attempt_count: u32,
    pub(crate) last_error: Option<ApiFailureSnapshot>,
}

impl Default for PendingHide {
    fn default() -> Self {
        let now = Utc::now();
        Self {
            title: String::new(),
            revid: 0,
            observed_at: None,
            first_failed_at: now,
            last_failed_at: now,
            attempt_count: 0,
            last_error: None,
        }
    }
}

impl PendingHide {
    pub(crate) fn retry_due_at(&self) -> DateTime<Utc> {
        self.last_failed_at + TimeDelta::seconds(PENDING_RETRY_SECONDS)
    }

    pub(crate) fn retry_due(&self, now: DateTime<Utc>) -> bool {
        now >= self.retry_due_at()
    }

    pub(crate) fn is_blocking(&self) -> bool {
        self.last_error
            .as_ref()
            .map(is_blocking_failure)
            .unwrap_or(false)
    }

    fn has_terminal_failure(&self) -> bool {
        self.last_error
            .as_ref()
            .map(is_terminal_hide_failure)
            .unwrap_or(false)
    }
}

#[derive(Clone, Debug)]
pub(crate) struct HideTarget {
    pub(crate) title: String,
    pub(crate) revid: u64,
    pub(crate) observed_at: Option<DateTime<Utc>>,
    pub(crate) source_label: String,
}

pub(crate) fn load_processed_revids(path: &Path) -> Result<ProcessedRevidsState> {
    let mut processed: ProcessedRevidsState = load_json(path)?.unwrap_or_default();
    if processed.capacity == 0 {
        processed.capacity = PROCESSED_CAPACITY;
    }
    Ok(processed)
}

pub(crate) fn upsert_pending(
    state: &mut SimpleDaemonState,
    target: &HideTarget,
    failure: ApiFailureSnapshot,
) {
    let now = Utc::now();
    if let Some(existing) = state
        .pending
        .iter_mut()
        .find(|item| item.revid == target.revid)
    {
        existing.last_failed_at = now;
        existing.attempt_count = existing.attempt_count.saturating_add(1);
        existing.last_error = Some(failure);
        return;
    }
    state.pending.push(PendingHide {
        title: target.title.clone(),
        revid: target.revid,
        observed_at: target.observed_at,
        first_failed_at: now,
        last_failed_at: now,
        attempt_count: 1,
        last_error: Some(failure),
    });
}

pub(crate) fn upsert_quarantined(
    state: &mut SimpleDaemonState,
    target: &HideTarget,
    failure: ApiFailureSnapshot,
) {
    state.pending.retain(|item| item.revid != target.revid);
    let now = Utc::now();
    if let Some(existing) = state
        .quarantined
        .iter_mut()
        .find(|item| item.revid == target.revid)
    {
        existing.last_failed_at = now;
        existing.attempt_count = existing.attempt_count.saturating_add(1);
        existing.last_error = Some(failure);
        return;
    }
    state.quarantined.push(PendingHide {
        title: target.title.clone(),
        revid: target.revid,
        observed_at: target.observed_at,
        first_failed_at: now,
        last_failed_at: now,
        attempt_count: 1,
        last_error: Some(failure),
    });
}

fn upsert_quarantined_item(state: &mut SimpleDaemonState, mut item: PendingHide) {
    if let Some(existing) = state
        .quarantined
        .iter_mut()
        .find(|existing| existing.revid == item.revid)
    {
        if item.last_failed_at >= existing.last_failed_at {
            *existing = item;
        }
        return;
    }
    if item.attempt_count == 0 {
        item.attempt_count = 1;
    }
    state.quarantined.push(item);
}

pub(crate) fn migrate_terminal_pending_to_quarantine(state: &mut SimpleDaemonState) {
    let mut retained = Vec::with_capacity(state.pending.len());
    for item in std::mem::take(&mut state.pending) {
        if item.has_terminal_failure() {
            upsert_quarantined_item(state, item);
        } else {
            retained.push(item);
        }
    }
    state.pending = retained;
}

pub(crate) fn next_pending_retry_at(pending: &[PendingHide]) -> Option<DateTime<Utc>> {
    pending.iter().map(PendingHide::retry_due_at).min()
}

pub(crate) fn unresolved_count(state: &SimpleDaemonState) -> usize {
    state.pending.len() + state.quarantined.len()
}

pub(crate) fn latest_quarantined_error(state: &SimpleDaemonState) -> Option<ApiFailureSnapshot> {
    state
        .quarantined
        .iter()
        .max_by_key(|item| item.last_failed_at)
        .and_then(|item| item.last_error.clone())
}

pub(crate) fn unresolved_item_from_pending(
    item: &PendingHide,
    server_name: &str,
    next_action: &str,
) -> UnresolvedExposureItem {
    UnresolvedExposureItem {
        title: item.title.clone(),
        revid: item.revid,
        revision_url: Some(revision_url(server_name, item.revid)),
        age_seconds: item
            .observed_at
            .map(|observed| Utc::now().signed_duration_since(observed).num_seconds()),
        reason: item
            .last_error
            .as_ref()
            .map(|failure| failure.message.clone())
            .unwrap_or_else(|| "pending retry".to_string()),
        next_action: next_action.to_string(),
    }
}

pub(crate) fn effective_realtime_state(
    requested_state: &str,
    state: &SimpleDaemonState,
    latest_error: Option<&ApiFailureSnapshot>,
    now: DateTime<Utc>,
    stale_threshold_seconds: u64,
) -> String {
    if matches!(
        requested_state,
        "starting" | "catching-up" | "stopping" | "stopped"
    ) {
        return requested_state.to_string();
    }
    if latest_error.map(is_blocking_failure).unwrap_or(false)
        || state.pending.iter().any(PendingHide::is_blocking)
    {
        return "blocked".to_string();
    }
    if latest_error.is_some() || !state.pending.is_empty() || !state.quarantined.is_empty() {
        return "degraded".to_string();
    }
    let poll_is_fresh = state
        .last_successful_poll_at
        .map(|timestamp| {
            now.signed_duration_since(timestamp).num_seconds() <= stale_threshold_seconds as i64
        })
        .unwrap_or(false);
    if poll_is_fresh {
        "healthy".to_string()
    } else {
        "degraded".to_string()
    }
}

pub(crate) fn is_blocking_failure(failure: &ApiFailureSnapshot) -> bool {
    matches!(failure.class.as_str(), "auth-session")
}

pub(crate) fn is_terminal_hide_failure(failure: &ApiFailureSnapshot) -> bool {
    matches!(
        failure.api_code.as_deref(),
        Some("permissiondenied" | "cantdelete")
    ) || failure.class == "permission"
}

pub(crate) fn should_retry_after_fresh_auth(failure: &ApiFailureSnapshot) -> bool {
    matches!(failure.api_code.as_deref(), Some("permissiondenied")) || failure.class == "permission"
}

#[cfg(test)]
mod tests {
    use super::*;

    fn api_failure(class: &str) -> ApiFailureSnapshot {
        ApiFailureSnapshot {
            class: class.to_string(),
            operation: "revisiondelete".to_string(),
            message: "failed".to_string(),
            ..ApiFailureSnapshot::default()
        }
    }

    fn api_failure_with_code(class: &str, code: &str) -> ApiFailureSnapshot {
        ApiFailureSnapshot {
            api_code: Some(code.to_string()),
            retryable: false,
            ..api_failure(class)
        }
    }

    #[test]
    fn startup_catchup_uses_recent_window_without_cursor() {
        let end = DateTime::parse_from_rfc3339("2026-05-31T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let state = SimpleDaemonState::default();
        let start = state
            .last_successful_poll_at
            .unwrap_or(end - TimeDelta::seconds(1800));

        assert_eq!(start, end - TimeDelta::seconds(1800));
    }

    #[test]
    fn permission_quarantine_degrades_health() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            quarantined: vec![PendingHide {
                revid: 1,
                last_error: Some(api_failure_with_code("permission", "permissiondenied")),
                ..PendingHide::default()
            }],
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "degraded"
        );
    }

    #[test]
    fn auth_session_pending_blocks_health() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            pending: vec![PendingHide {
                revid: 1,
                last_error: Some(api_failure("auth-session")),
                ..PendingHide::default()
            }],
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "blocked"
        );
    }

    #[test]
    fn nonblocking_pending_degrades_health() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            pending: vec![PendingHide {
                revid: 1,
                last_error: Some(api_failure("non-json-response")),
                ..PendingHide::default()
            }],
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "degraded"
        );
    }

    #[test]
    fn fresh_empty_state_is_healthy() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "healthy"
        );
    }

    #[test]
    fn stale_empty_state_is_degraded() {
        let now = Utc::now();
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(now - TimeDelta::seconds(30)),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            effective_realtime_state("healthy", &state, None, now, 10),
            "degraded"
        );
    }

    #[test]
    fn upsert_pending_preserves_single_item_per_revision() {
        let mut state = SimpleDaemonState::default();
        let target = HideTarget {
            title: "Title".to_string(),
            revid: 42,
            observed_at: None,
            source_label: "test".to_string(),
        };

        upsert_pending(&mut state, &target, api_failure("timeout"));
        upsert_pending(&mut state, &target, api_failure("timeout"));

        assert_eq!(state.pending.len(), 1);
        assert_eq!(state.pending[0].attempt_count, 2);
    }

    #[test]
    fn terminal_pending_migrates_to_quarantine() {
        let mut state = SimpleDaemonState {
            pending: vec![PendingHide {
                revid: 42,
                last_error: Some(api_failure_with_code("permission", "permissiondenied")),
                attempt_count: 255,
                ..PendingHide::default()
            }],
            ..SimpleDaemonState::default()
        };

        migrate_terminal_pending_to_quarantine(&mut state);

        assert!(state.pending.is_empty());
        assert_eq!(state.quarantined.len(), 1);
        assert_eq!(state.quarantined[0].revid, 42);
        assert_eq!(state.quarantined[0].attempt_count, 255);
    }

    #[test]
    fn permission_failure_gets_fresh_auth_retry_before_quarantine() {
        let permission = api_failure_with_code("permission", "permissiondenied");
        let cantdelete = api_failure_with_code("permission", "cantdelete");
        let timeout = api_failure("timeout");

        assert!(should_retry_after_fresh_auth(&permission));
        assert!(is_terminal_hide_failure(&permission));
        assert!(should_retry_after_fresh_auth(&cantdelete));
        assert!(is_terminal_hide_failure(&cantdelete));
        assert!(!should_retry_after_fresh_auth(&timeout));
    }

    #[test]
    fn quarantine_summary_does_not_claim_auto_retry() {
        let item = PendingHide {
            title: "Title".to_string(),
            revid: 42,
            last_error: Some(api_failure_with_code("permission", "permissiondenied")),
            ..PendingHide::default()
        };

        let unresolved = unresolved_item_from_pending(
            &item,
            "be.wikipedia.org",
            "manual review required; daemon will not retry this non-retryable API failure automatically",
        );

        assert!(unresolved.next_action.contains("will not retry"));
        assert_eq!(
            unresolved.revision_url.as_deref(),
            Some("https://be.wikipedia.org/wiki/Special:Diff/42")
        );
    }
}
