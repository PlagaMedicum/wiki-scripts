use chrono::{DateTime, TimeDelta, Utc};

use crate::config::CatchupConfig;
use crate::daemon_backlog::SimpleDaemonState;

const LIVE_OVERLAP_SECONDS: i64 = 15;

pub(crate) fn startup_catchup_start(
    state: &SimpleDaemonState,
    catchup: &CatchupConfig,
    end: DateTime<Utc>,
) -> DateTime<Utc> {
    let fallback = end - TimeDelta::seconds(catchup.default_window_seconds);
    let Some(cursor) = state.last_successful_poll_at else {
        return fallback;
    };
    let max_start = end - TimeDelta::seconds(catchup.max_window_seconds);
    cursor.max(max_start).min(end)
}

pub(crate) fn live_poll_start(
    state: &SimpleDaemonState,
    catchup: &CatchupConfig,
    end: DateTime<Utc>,
) -> DateTime<Utc> {
    state
        .last_successful_poll_at
        .map(|cursor| cursor - TimeDelta::seconds(LIVE_OVERLAP_SECONDS))
        .unwrap_or_else(|| end - TimeDelta::seconds(catchup.default_window_seconds))
        .max(end - TimeDelta::seconds(catchup.max_window_seconds))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_catchup_config() -> CatchupConfig {
        CatchupConfig {
            default_window_seconds: 1_800,
            max_window_seconds: 7_200,
            ..CatchupConfig::default()
        }
    }

    #[test]
    fn startup_catchup_uses_default_window_without_poll_cursor() {
        let end = DateTime::parse_from_rfc3339("2026-05-31T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let state = SimpleDaemonState::default();

        assert_eq!(
            startup_catchup_start(&state, &test_catchup_config(), end),
            end - TimeDelta::seconds(1_800)
        );
    }

    #[test]
    fn startup_catchup_clamps_old_cursor_to_max_window() {
        let end = DateTime::parse_from_rfc3339("2026-05-31T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(end - TimeDelta::seconds(20_000)),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            startup_catchup_start(&state, &test_catchup_config(), end),
            end - TimeDelta::seconds(7_200)
        );
    }

    #[test]
    fn startup_catchup_clamps_future_cursor_to_now() {
        let end = DateTime::parse_from_rfc3339("2026-05-31T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let state = SimpleDaemonState {
            last_successful_poll_at: Some(end + TimeDelta::seconds(60)),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            startup_catchup_start(&state, &test_catchup_config(), end),
            end
        );
    }

    #[test]
    fn live_poll_reuses_overlap_without_exceeding_max_window() {
        let end = DateTime::parse_from_rfc3339("2026-05-31T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let catchup = test_catchup_config();
        let recent = SimpleDaemonState {
            last_successful_poll_at: Some(end - TimeDelta::seconds(60)),
            ..SimpleDaemonState::default()
        };
        let old = SimpleDaemonState {
            last_successful_poll_at: Some(end - TimeDelta::seconds(20_000)),
            ..SimpleDaemonState::default()
        };

        assert_eq!(
            live_poll_start(&recent, &catchup, end),
            end - TimeDelta::seconds(60 + LIVE_OVERLAP_SECONDS)
        );
        assert_eq!(
            live_poll_start(&old, &catchup, end),
            end - TimeDelta::seconds(7_200)
        );
    }
}
