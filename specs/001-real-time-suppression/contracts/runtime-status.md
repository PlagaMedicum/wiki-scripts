---
docmeta:
  status: draft
  review: feature-local
  purpose: Runtime status contract for real-time suppression recovery.
  source: speckit-plan on 2026-04-24
---

# Contract: Runtime Status


## Surface

The daemon persists local runtime status for the TUI and operator diagnostics in the existing runtime status state file.

## Required Realtime Section

```json
{
  "daemon_state": "running",
  "dry_run": false,
  "last_notice": "real-time stream healthy",
  "last_notice_at": "2026-04-24T16:25:00Z",
  "realtime": {
    "state": "healthy",
    "last_state_changed_at": "2026-04-24T16:24:05Z",
    "stale_threshold_seconds": 10,
    "last_stream_opened_at": "2026-04-24T16:24:05Z",
    "last_event_observed_at": "2026-04-24T16:24:59Z",
    "last_matching_edit_at": "2026-04-24T16:24:59Z",
    "last_action_queued_at": "2026-04-24T16:24:59Z",
    "last_action_completed_at": "2026-04-24T16:25:00Z",
    "last_successful_hide_at": "2026-04-24T16:25:00Z",
    "last_event_id": "[{\"topic\":\"codfw.mediawiki.recentchange\",\"partition\":0,\"timestamp\":1777051500000}]",
    "current_lag_seconds": 1,
    "queue_depth": 0,
    "last_recovery_trigger": null,
    "last_recovery_started_at": null,
    "last_recovery_completed_at": null,
    "last_reconnect_reason": null,
    "catchup_active": false,
    "latest_error_code": null,
    "latest_notice": "hidden revid 123456789"
  },
  "reconciliation": {
    "active": false,
    "mode": "nightly",
    "phase": "idle",
    "queued_mode": null
  }
}
```

## State Values

- `starting`: daemon has started but has not proven realtime freshness.
- `healthy`: realtime events are fresh and no catch-up is pending.
- `catching-up`: bounded recovery or manual coverage is running.
- `stale`: realtime freshness exceeded the threshold and recovery is pending or running.
- `reconnecting`: stream reconnect is in progress.
- `unhealthy`: realtime path is running but ineffective for a non-fatal reason.
- `blocked`: rights, session, or wiki-side condition prevents hiding.
- `stopped`: daemon is stopping or stopped.

## TUI Requirements

- Show realtime state separately from daemon process state and reconciliation state.
- Show freshness lag, stale threshold, and queue depth.
- Show last matched edit, last queued action, and last successful hide times when present.
- Show the active recovery trigger and latest reconnect reason when realtime state is not healthy.
- Color or label `stale`, `unhealthy`, and `blocked` as operator-action states.
- Do not display sensitive hidden content, raw comments, credentials, or tokens.
- Define `current_lag_seconds` as wall-clock seconds since the latest target-wiki event observed by the stream, or since the newest target-wiki change discovered by a bounded API freshness probe when the stream is silent.
- Define an actionable notice as a compact non-sensitive message that includes state, reason code or recovery trigger, affected revision identifier when safe, and the next operator action when manual review is required.
- In compact terminals, preserve daemon state, realtime state, lag, latest actionable notice, and blocked/error indicators before lower-priority reconciliation details.

## Compatibility

- Missing `realtime` in older state files must load as an unknown/stale-safe default.
- Existing reconciliation fields remain readable.
- Existing `last_event_id.txt` may remain as a legacy resume file, but the TUI should prefer the richer runtime status when available.
- Missing runtime status, stale PID files, and unreadable older status files must produce a non-healthy diagnostic state instead of a false healthy state.
