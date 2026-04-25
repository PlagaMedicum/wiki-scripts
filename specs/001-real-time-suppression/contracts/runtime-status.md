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
  "resource_economy": {
    "queue_depth_max_recent": 3,
    "api_concurrency_max_recent": 2,
    "state_bytes_recent": 210000,
    "coalesced_warning_count_recent": 1427,
    "latest_measurement_at": "2026-04-24T16:25:00Z"
  },
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
    "latest_error": null,
    "last_source_refresh": null,
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
- Show classified latest API/source-list error details when present: class, API code, HTTP status, retryability, safe sample title or revision ID, and next action.
- Show source-list refresh status when the source page or request page triggered cache refresh and immediate catch-up.
- Show resource-economy warning indicators only when bounds are approached or a release verification command is active; normal TUI rendering must stay compact.
- Color or label `stale`, `unhealthy`, and `blocked` as operator-action states.
- Do not display sensitive hidden content, raw comments, credentials, or tokens.
- Define `current_lag_seconds` as wall-clock seconds since the latest target-wiki event observed by the stream, or since the newest target-wiki change discovered by a bounded API freshness probe when the stream is silent.
- Define an actionable notice as a compact non-sensitive message that includes state, reason code or recovery trigger, affected revision identifier when safe, and the next operator action when manual review is required.
- In compact terminals, preserve daemon state, realtime state, lag, latest actionable notice, and blocked/error indicators before lower-priority reconciliation details.
- Coalesce repeated catch-up failures by root cause instead of rendering one warning per watched page. The TUI should show aggregate count, error class/code, and a small safe title sample.

## Error Snapshot Contract

When a MediaWiki call fails, runtime status may include:

```json
{
  "class": "api-json-error",
  "api_code": "badtimestamp",
  "http_status": 200,
  "content_type": "application/json; charset=utf-8",
  "retryable": false,
  "operation": "fetch-revisions",
  "sample_title": "Belcanto Airlines",
  "sample_revid": null,
  "message": "invalid MediaWiki timestamp parameter",
  "occurred_at": "2026-04-25T09:05:04Z"
}
```

Rules:

- Never persist response bodies, cookies, credentials, tokens, hidden text, or raw edit comments.
- Prefer MediaWiki API error code over lossy generic labels.
- Decode and non-JSON response failures must still record HTTP status and content type when available.
- Fatal auth/session/permission failures set realtime state to `blocked`; non-fatal classified failures set `unhealthy` or `retrying` according to retry state.

## Source Refresh Contract

When the source list or request page changes, runtime status may include:

```json
{
  "trigger_title": "Удзельнік:Wizardist/SuppressionList",
  "trigger_revid": 5132000,
  "old_source_revid": 5131786,
  "new_source_revid": 5132000,
  "new_titles_count": 2,
  "removed_titles_count": 0,
  "catchup_triggered": true,
  "catchup_title_scope": "new-titles",
  "outcome": "catchup-started",
  "started_at": "2026-04-25T09:10:00Z",
  "completed_at": null
}
```

Rules:

- A source-list refresh that changes watched titles must not leave realtime state `healthy` until immediate bounded catch-up has been started or explicitly failed.
- Request-page changes may trigger a recent-window catch-up even when the cached source list is unchanged.
- Refresh failure must be visible as an actionable latest notice.

## Compatibility

- Missing `realtime` in older state files must load as an unknown/stale-safe default.
- Existing reconciliation fields remain readable.
- Existing `last_event_id.txt` may remain as a legacy resume file, but the TUI should prefer the richer runtime status when available.
- Missing runtime status, stale PID files, and unreadable older status files must produce a non-healthy diagnostic state instead of a false healthy state.
- Missing `latest_error` or `last_source_refresh` in older state files must load as `null`.
- Missing `resource_economy` in older state files must load as `null` or a default empty summary.
