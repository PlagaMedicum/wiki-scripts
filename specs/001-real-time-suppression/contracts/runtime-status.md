---
docmeta:
  status: draft
  review: feature-local
  purpose: Runtime status contract for real-time suppression recovery.
  source: speckit-plan on 2026-04-28
---

# Contract: Runtime Status


## Surface

The daemon persists local runtime status for the TUI and operator diagnostics in the existing runtime status state file. This file is daemon-owned realtime truth; one-shot commands may read it but must not overwrite it with their own temporary runtime. If an older state artifact, stale supervisor marker, or invalid launch-path assumption means the previous operator setup is no longer trustworthy, the surface should emit a compact compatibility notice instead of silently reading healthy.

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
  "compatibility_notice": null,
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
    "last_freshness_probe_at": null,
    "last_freshness_probe_source": "stream",
    "catchup_active": false,
    "backoff_until": null,
    "latest_error_code": null,
    "latest_error": null,
    "latest_outcome": null,
    "latest_recovery_warnings": [],
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
- Show daemon-owned realtime state separately from one-shot operator command progress or report output.
- Show freshness lag, stale threshold, and queue depth.
- Show last matched edit, last queued action, and last successful hide times when present.
- Show the active recovery trigger and latest reconnect reason when realtime state is not healthy.
- Show freshness-probe time and backoff-until time when those are the reason realtime is not yet healthy.
- Show classified latest API/source-list error details when present: class, API code, HTTP status, retryability, safe sample title or revision ID, and next action.
- Show the latest suppression outcome, including whether it came from `live`, `catchup`, `coverage`, `reconciliation`, or another explicit action mode, when that outcome explains current degraded protection.
- Show source-list refresh status when the source page or request page triggered cache refresh and immediate catch-up.
- Show resource-economy warning indicators only when bounds are approached or a release verification command is active; normal TUI rendering must stay compact.
- Color or label `stale`, `unhealthy`, and `blocked` as operator-action states.
- Do not display sensitive hidden content, raw comments, credentials, or tokens.
- Define `current_lag_seconds` as wall-clock seconds since the latest target-wiki event observed by the stream, or since the newest target-wiki change discovered by a bounded API freshness probe when the stream is silent.
- A fresh stream plus `current_lag_seconds=0` is not enough to imply `healthy`; a failed or unresolved latest live suppression outcome must still surface as degraded protection until recovery or retry succeeds.
- Define an actionable notice as a compact non-sensitive message that includes state, reason code or recovery trigger, affected revision identifier when safe, and the next operator action when manual review is required.
- In compact terminals, preserve daemon state, realtime state, lag, latest actionable notice, throttle/backoff indicators, and blocked/error indicators before lower-priority reconciliation details.
- Coalesce repeated catch-up failures by root cause instead of rendering one warning per watched page. The TUI should show aggregate count, error class/code, and a small safe title sample.
- When realtime is throttled or paused by repeated root-cause failures, that state takes priority over stale reconciliation failure text.
- `state=catching-up` must converge once recovery is no longer active; if `catchup_active=false`, `backoff_until=null`, and no recovery remains in progress, the daemon must move to `healthy`, `unhealthy`, `reconnecting`, or `blocked` according to the remaining evidence.
- The live-output pane must not hide the newest rows behind wrapped-line scroll drift while `latest` mode is active.
- If the TUI also shows one-shot command output, those lines must be distinctly labeled so operators do not confuse them with daemon runtime evidence.

## Error Snapshot Contract

When a MediaWiki call fails, runtime status may include:

```json
{
  "class": "non-json-response",
  "api_code": null,
  "http_status": 429,
  "content_type": "text/plain",
  "retryable": true,
  "retry_after_seconds": 30,
  "operation": "fetch-revisions",
  "sample_title": "Belcanto Airlines",
  "sample_revid": null,
  "message": "rate limited by MediaWiki edge",
  "occurred_at": "2026-04-25T17:04:54Z"
}
```

Rules:

- Never persist response bodies, cookies, credentials, tokens, hidden text, or raw edit comments.
- Prefer MediaWiki API error code over lossy generic labels.
- Decode and non-JSON response failures must still record HTTP status and content type when available.
- Preserve `retry_after_seconds` when the server provides a usable throttle hint or when the daemon applies a shared local backoff.
- `badtimestamp` remains the canonical non-retryable regression case for timestamp serialization tests.
- Fatal auth/session/permission failures set realtime state to `blocked`; non-fatal classified failures set `unhealthy` or `retrying` according to retry state.
- Repeated throttle failures may set realtime state to `catching-up` or `unhealthy` with `backoff_until` populated until the daemon is allowed to retry.
- The same classified error model applies to live-path revision queries as well as catch-up or reconciliation fetches; operator status must not imply that throttling is only a recovery-path problem.

## Recovery Summary Contract

When a bounded recovery run finishes or stops early, runtime status may include:

```json
{
  "checked_pages": 113,
  "checked_edits": 21,
  "unresolved_count": 5,
  "stopped_early_reason": "rate-limited",
  "warning_summaries": [
    {
      "class": "non-json-response",
      "http_status": 429,
      "operation": "fetch-revisions",
      "retryable": true,
      "count": 5,
      "sample_titles": ["Belcanto Airlines", "ПВК «Вагнер»"],
      "stopped_early": true
    }
  ]
}
```

Rules:

- Recovery summaries must keep counts for the full run but retain only bounded safe samples.
- `stopped_early_reason` must be set when the daemon pauses or aborts a run under a repeated root cause such as throttling.
- A stopped-early recovery summary is not a healthy state; the TUI should show the cause and the next retry point.
- `requested_by=startup` or `last_recovery_trigger=startup` should reflect true daemon bootstrap or an explicit bootstrap recovery decision, not every ordinary EventStreams reopen.

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
- If shared throttle state delays the follow-up catch-up, persist a deferred outcome and retry point instead of reporting a silent success.
- Refresh failure must be visible as an actionable latest notice.

## Compatibility Notice Contract

When runtime status detects an operator-facing incompatibility or migration requirement, it may include:

```json
{
  "scope": "launch-path",
  "severity": "migration-required",
  "detected_at": "2026-04-28T16:08:00Z",
  "previous_value": "journalctl -u suppressor.service",
  "expected_value": "TUI-managed daemon child plus daemon-owned runtime_status.json",
  "summary": "current deployment is not systemd-managed",
  "operator_action": "verify the TUI-managed child process and runtime_status.json before trusting healthy status",
  "blocking": true
}
```

Rules:

- Emit no notice when the previously documented setup remains valid and no operator action is required.
- Notices must stay compact and machine-readable; do not persist hidden text, raw comments, response bodies, credentials, cookies, or tokens.
- A `migration-required` or blocking notice must prevent a false healthy interpretation of the overall operator surface.
- Use a notice when stale PID files, unreadable older status files, incompatible report shapes, or invalid launch-path assumptions require the operator to change how they verify the daemon.

## Compatibility

- Missing `realtime` in older state files must load as an unknown/stale-safe default.
- Existing reconciliation fields remain readable.
- Existing `last_event_id.txt` may remain as a legacy resume file, but the TUI should prefer the richer runtime status when available.
- Missing runtime status, stale PID files, and unreadable older status files must produce a non-healthy diagnostic state instead of a false healthy state.
- If the daemon is not systemd-managed in a given deployment, operator verification must use the actual supervisor-managed process and its daemon-owned runtime file rather than assuming a systemd unit exists.
- If the previous operator setup cannot remain valid, runtime status must state the new authoritative diagnostics path and the required migration action explicitly rather than relying on an implied field or log change.
- Missing `latest_error` or `last_source_refresh` in older state files must load as `null`.
- Missing `backoff_until`, `last_freshness_probe_at`, `last_freshness_probe_source`, or `latest_recovery_warnings` in older state files must load as `null` or an empty list.
- Missing `resource_economy` in older state files must load as `null` or a default empty summary.
- Missing `compatibility_notice` in older state files must load as `null`.
