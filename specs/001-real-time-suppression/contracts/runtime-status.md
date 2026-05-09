---
docmeta:
  status: draft
  review: feature-local
  purpose: Runtime status contract for real-time suppression recovery.
  source:
  - speckit-plan on 2026-04-29
  - speckit-plan server-running launch-path mismatch update on 2026-05-07
  - speckit-plan live-priority parallel execution update on 2026-05-09
  - speckit-plan live-latency clarification update on 2026-05-09
---

# Contract: Runtime Status


## Surface

The daemon persists local runtime status for the TUI and operator diagnostics in
`runtime_status.json`. This file is daemon-owned realtime truth. One-shot commands may read it but
must not overwrite it. The contract is compatibility-first: existing fields remain readable where
practical, new fields are additive, and older shapes must degrade safely into non-healthy or
migration-needed diagnostics instead of false healthy status.

The primary TUI status view should not render this file field-for-field. It should derive a compact
operator-first summary from it and leave raw transport or bookkeeping fields as secondary
diagnostics.

## Required Top-Level Shape

```json
{
  "daemon_state": "running",
  "dry_run": false,
  "launch_path": {
    "kind": "server-start",
    "pid": 43217,
    "binary_path": "/opt/suppressor/suppressor",
    "config_path": "/opt/suppressor/config.toml",
    "pid_file": "/opt/suppressor/state/daemon.pid",
    "runtime_status_file": "/opt/suppressor/state/runtime_status.json",
    "log_path": "/opt/suppressor/state/daemon.log",
    "started_at": "2026-04-29T08:30:00Z"
  },
  "last_notice": "rolling last-24h verification completed",
  "last_notice_at": "2026-04-29T09:10:03Z",
  "resource_economy": {
    "queue_depth_max_recent": 4,
    "live_queue_depth_max_recent": 1,
    "background_queue_depth_max_recent": 4,
    "api_concurrency_max_recent": 2,
    "state_bytes_recent": 210542,
    "coalesced_warning_count_recent": 12,
    "latest_measurement_at": "2026-04-29T09:10:03Z"
  },
  "compatibility_notice": null,
  "realtime": {
    "state": "healthy",
    "last_state_changed_at": "2026-04-29T09:08:11Z",
    "stale_threshold_seconds": 10,
    "last_stream_opened_at": "2026-04-29T09:01:10Z",
    "last_event_observed_at": "2026-04-29T09:10:02Z",
    "last_event_id": "[resume cursor omitted from primary TUI]",
    "last_matching_edit_at": "2026-04-29T09:10:01Z",
    "last_matching_title": "Synthetic Watched Page",
    "last_matching_revid": 9000001,
    "last_matching_revid_url": "https://example.invalid/wiki/Special:Diff/9000001",
    "last_action_queued_at": "2026-04-29T09:10:01Z",
    "last_action_completed_at": "2026-04-29T09:10:02Z",
    "last_successful_hide_at": "2026-04-29T09:10:02Z",
    "last_successful_hide_title": "Synthetic Watched Page",
    "last_successful_hide_revid": 9000001,
    "last_successful_hide_url": "https://example.invalid/wiki/Special:Diff/9000001",
    "current_lag_seconds": 0,
    "current_lag_millis": 284,
    "current_lag_source": "stream",
    "queue_depth": 0,
    "live_lane": {
      "queue_depth": 0,
      "queue_capacity": 100,
      "in_flight": 0,
      "concurrency_limit": 1,
      "latest_saturation_at": null,
      "latest_saturation_reason": null
    },
    "background_lane": {
      "queue_depth": 0,
      "queue_capacity": 100,
      "in_flight": 0,
      "concurrency_limit": 2,
      "latest_saturation_at": null,
      "latest_saturation_reason": null
    },
    "latency": {
      "observed_to_queue": {
        "sample_count": 24,
        "latest_ms": 37,
        "min_ms": 18,
        "p50_ms": 33,
        "p95_ms": 74,
        "p99_ms": 91,
        "max_ms": 91
      },
      "queue_to_submit": {
        "sample_count": 24,
        "latest_ms": 12,
        "min_ms": 4,
        "p50_ms": 8,
        "p95_ms": 24,
        "p99_ms": 31,
        "max_ms": 31
      },
      "submit_to_complete": {
        "sample_count": 24,
        "latest_ms": 266,
        "min_ms": 188,
        "p50_ms": 241,
        "p95_ms": 612,
        "p99_ms": 784,
        "max_ms": 784
      },
      "observed_to_hidden": {
        "sample_count": 24,
        "latest_ms": 315,
        "min_ms": 220,
        "p50_ms": 290,
        "p95_ms": 710,
        "p99_ms": 890,
        "max_ms": 890
      }
    },
    "daemon_started_at": "2026-04-29T08:30:00Z",
    "current_task": {
      "task_kind": "idle",
      "label": "waiting for watched-page edits",
      "progress_done": null,
      "progress_total": null,
      "window_start": null,
      "window_end": null,
      "started_at": "2026-04-29T09:10:02Z",
      "expected_resume_at": null
    },
    "last_recovery_trigger": null,
    "last_recovery_started_at": "2026-04-29T08:31:00Z",
    "last_recovery_completed_at": "2026-04-29T08:31:08Z",
    "last_reconnect_reason": null,
    "last_freshness_probe_at": null,
    "last_freshness_probe_source": "stream",
    "catchup_active": false,
    "backoff_until": null,
    "latest_error_code": null,
    "latest_error": null,
    "latest_actionable_issue": null,
    "latest_outcome": {
      "title": "Synthetic Watched Page",
      "revid": 9000001,
      "outcome": "hidden",
      "reason_code": null,
      "mode": "live",
      "completed_at": "2026-04-29T09:10:02Z"
    },
    "latest_recovery_summary": {
      "scope_label": "since last successful hide",
      "requested_by": "stream-gap",
      "started_at": "2026-04-29T08:31:00Z",
      "ended_at": "2026-04-29T08:31:08Z",
      "pages_checked": 17,
      "edits_checked": 3,
      "hidden_count": 1,
      "already_hidden_count": 1,
      "skipped_count": 0,
      "failed_count": 0,
      "unresolved_count": 1,
      "stopped_early_reason": null,
      "backoff_until": null,
      "warning_summaries": []
    },
    "latest_recovery_warnings": [],
    "last_source_refresh": null,
    "last_daytime_verification_at": "2026-04-29T07:44:03Z",
    "last_daytime_verification_window_start": "2026-04-28T07:44:03Z",
    "last_daytime_verification_window_end": "2026-04-29T07:44:03Z",
    "last_nightly_full_recheck_at": "2026-04-29T02:17:18Z",
    "latest_notice": "hidden synthetic revid 9000001"
  },
  "reconciliation": {
    "active": false,
    "mode": "nightly-full",
    "phase": "idle",
    "queued_mode": null,
    "freshness": {
      "target_hours": 24,
      "total_pages": 1465,
      "pages_older_than_target": 0,
      "oldest_full_check_at": "2026-04-29T02:17:18Z",
      "oldest_full_check_title": "Synthetic Watched Page",
      "oldest_full_check_age_seconds": 2475,
      "last_daytime_verification_result": "completed",
      "last_nightly_full_recheck_result": "completed",
      "computed_at": "2026-04-29T09:10:03Z"
    }
  }
}
```

## Primary Operator View Contract

The compact primary operator view must answer these questions without requiring raw logs:

- Is protection working now?
- What background work is active?
- What exact recovery or verification window is in progress?
- When was the last successful hide, and what revision was it?
- What is the latest actionable problem?
- How long has the daemon been continuously protecting edits?

The primary view should therefore render, in priority order:

1. `Protection`: colored protection state plus PID, actual launch path, and daemon uptime.
2. `Current work`: idle, gap recovery, rolling last-24h verification, nightly full recheck,
   source refresh, or backoff, with progress and exact window or full-scope label.
3. `Lag`: wall-clock lag with sub-second precision under one second and the lag source.
4. `Live lane`: queue depth/cap, in-flight count, and recent p95/p99 timing when the lane is busy
   or near saturation.
5. `Last successful hide`: title, timestamp, and revision link.
6. `Last observed watched edit` or `Last observed target-wiki event`, whichever best explains the
   current state.
7. `Latest issue`: plain-language issue summary with next action when needed.
8. `Full recheck freshness`: oldest full-check age, stale-page count, and last failed scheduled
   verification result when that evidence affects trust.
9. `Compatibility` or `migration` notice when present.

The primary view should not spend its first rows on:

- raw `last_event_id` JSON
- processed revision ring size
- checkpoint-page counts
- verification path wording
- managed-session bookkeeping
- other low-level counters that do not answer the operator questions above

## Required Realtime Semantics

- `state=healthy` means all of the following are true:
  - live recentchange freshness is within threshold
  - no required recovery or verification is currently incomplete
  - no active throttle backoff blocks required recovery
  - scheduled verification evidence is not overdue for the current uninterrupted daemon period
  - the latest scheduled verification or full watched-set recheck has not failed without a still
    visible actionable issue
  - the latest live hide outcome is not failed, unresolved, or blocked without a compensating
    successful retry or recovery result
- `state=recovering` or `state=catching-up` means an actual recovery, verification, or throttle
  backoff is active. The state must converge out of this label once work has ended.
- `state=stale` means the daemon is running but freshness exceeded threshold and recovery is needed
  or still being evaluated.
- `state=degraded` or `state=unhealthy` means the stream may still be fresh, but live protection is
  not trustworthy because the latest actionable live outcome failed, remained unresolved, is waiting
  on a recovery path, or because launch-path, PID-file, runtime-status, or detached-log evidence
  does not agree.
- `state=blocked` means rights, session, or wiki-side conditions prevent continued hiding.

## Required Field Semantics

- `last_event_id` remains a transport cursor for resume behavior. It is not a primary operator
  field, and the TUI should not label it as “last event” for humans.
- `current_lag_seconds` remains the compatibility whole-seconds lag field.
- `current_lag_millis` is an additive precise lag field for sub-second operator display.
- Both lag fields are recalculated from the latest observed target-wiki event or from a bounded API
  freshness probe when the stream is silent.
- `last_matching_revid_url` and `last_successful_hide_url` must be safe browser-openable URLs,
  typically `https://be.wikipedia.org/wiki/Special:Diff/<revid>`.
- `daemon_started_at` records the start of the current continuous protection session used for TUI
  uptime.
- `launch_path.kind` records the actual authoritative launch path for this run, such as
  `tui-managed`, `systemd`, `server-start`, or another explicit supervisor label.
- `launch_path.pid`, `pid_file`, `runtime_status_file`, and `log_path` must remain non-sensitive and
  must let the operator verify a detached `server-start` daemon after closing the SSH terminal.
- If a live process exists but `launch_path.pid`, the PID file, daemon-owned runtime status, or log
  path cannot be tied to the same process and deployed binary, the derived status must include a
  blocking compatibility notice or non-healthy state rather than allowing a healthy interpretation.
- `current_task` records the background task the operator should care about now, even if lower-level
  reconciliation counters still exist elsewhere.
- `live_lane` and `background_lane` are additive lane snapshots. The live lane records
  recentchange-triggered hide work; the background lane records catch-up, rolling verification,
  full recheck, reconciliation, and one-shot command work. Background queue pressure must not be
  interpreted as live queue pressure unless the live lane also reports pressure.
- `latency.observed_to_queue`, `latency.queue_to_submit`, `latency.submit_to_complete`, and
  `latency.observed_to_hidden` are bounded recent live samples. They support deterministic tests
  and release evidence for SC-001. Missing latency fields are compatible with older status files
  but block new latency-readiness claims.
- `latest_actionable_issue` is preferred over raw error codes for primary rendering. Raw
  `latest_error` remains available as secondary diagnostic detail.
- `last_daytime_verification_*` and `last_nightly_full_recheck_at` provide operator evidence that
  the scheduled verification duties are actually running.
- `reconciliation.freshness` is the compact operator-facing summary of full watched-set coverage
  age. It must summarize checkpoint staleness rather than merely expose checkpoint file size or
  page count.

## TUI Requirements

- Show one colored daemon or protection status row with PID instead of duplicating daemon state
  information across multiple near-identical rows.
- Use plain-language labels such as `Protection`, `Current work`, `Last successful hide`, `Latest
  issue`, and `Last 24 hours verification`.
- Make revision identifiers clickable or copyable as direct URLs where the terminal supports it.
- Keep daemon output and one-shot command output visibly distinct in the live log pane.
- Keep the newest rendered rows visible in latest-follow mode even when lines wrap.
- If secondary diagnostics are shown, they should be clearly lower priority than primary status.

## Error Snapshot Contract

When a MediaWiki or transport call fails, runtime status may include:

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
  "occurred_at": "2026-04-29T09:01:09Z"
}
```

Rules:

- Never persist response bodies, cookies, credentials, tokens, hidden text, or raw edit comments.
- Preserve throttle hints such as `retry_after_seconds` when available.
- The same error model applies to live, recovery, verification, source-refresh, and freshness-probe
  failures.
- Rate-limit failures may populate `latest_actionable_issue` even if the stream itself remains
  fresh.

## Recovery And Verification Summary Contract

When a recovery or verification run finishes or stops early, runtime status may include:

```json
{
  "scope_label": "last 24 hours",
  "requested_by": "scheduler-daytime",
  "started_at": "2026-04-29T07:44:03Z",
  "ended_at": "2026-04-29T07:45:18Z",
  "pages_checked": 1465,
  "edits_checked": 9,
  "hidden_count": 2,
  "already_hidden_count": 6,
  "skipped_count": 0,
  "failed_count": 0,
  "unresolved_count": 1,
  "stopped_early_reason": null,
  "backoff_until": null,
  "warning_summaries": []
}
```

Rules:

- The summary must carry an exact window label such as `since last successful hide`, `last 24
  hours`, or `full watched set`.
- Stopped-early runs are not healthy outcomes and must remain operator-visible until resolved or
  superseded.
- Daytime and nightly scheduled runs must remain distinct in naming and evidence.

## Scheduled Verification Freshness Contract

When runtime status or the derived operator surface summarizes full watched-set coverage freshness,
it may include:

```json
{
  "target_hours": 24,
  "total_pages": 1427,
  "pages_older_than_target": 1427,
  "oldest_full_check_at": "2018-01-12T20:19:50Z",
  "oldest_full_check_title": "Synthetic Stale Watched Page",
  "oldest_full_check_age_seconds": 261756000,
  "last_daytime_verification_result": "failed: non-json-response",
  "last_nightly_full_recheck_result": "not-yet-recorded",
  "computed_at": "2026-04-30T10:45:00Z"
}
```

Rules:

- This summary may be persisted directly in `runtime_status.json` or derived from
  `nightly_sweep_progress.json` plus runtime status, but the operator surface must treat it as
  first-class evidence.
- `pages_older_than_target > 0` means the operator does not currently have proof of a recent full
  watched-set recheck.
- A failed daytime or nightly verification result must feed `latest_actionable_issue` or another
  equally visible degraded-trust row until a later successful run clears it.
- Raw checkpoint-page counts are not an acceptable substitute for freshness age.

## Compatibility Notice Contract

When runtime status detects an operator-facing incompatibility or migration requirement, it may
include:

```json
{
  "scope": "launch-path",
  "severity": "migration-required",
  "detected_at": "2026-04-29T09:00:00Z",
  "previous_value": "journalctl -u suppressor.service",
  "expected_value": "TUI-managed daemon child plus daemon-owned runtime_status.json",
  "summary": "current deployment is not using the previously documented systemd path",
  "operator_action": "verify the TUI-managed child and runtime_status.json before trusting healthy status",
  "rollback_path": "restart the last trusted binary and verify using the previous documented workflow",
  "blocking": true
}
```

Rules:

- A blocking or `migration-required` notice prevents a fully healthy or release-ready
  interpretation.
- The notice must remain compact and machine-readable.
- Runtime status and one-shot command reports may both surface the notice, but command notices must
  not masquerade as daemon realtime truth.

## Compatibility

- Older runtime files missing new additive fields must still parse through safe defaults.
- Missing fields that are required for trustworthy interpretation must degrade into a non-healthy or
  migration-needed diagnostic, not a false healthy state.
- Existing reconciliation fields remain readable.
- Existing `last_event_id.txt` may remain a resume artifact, but the operator surface should prefer
  the richer daemon-owned runtime contract.
- If a deployment is not systemd-managed, the operator surface must state the actual authoritative
  path instead of silently assuming a unit exists.
- A detached `server-start` launch must identify itself as `server-start` or equivalent
  detached-binary wording so it is not confused with a TUI-managed child or a systemd unit.
- A detached `server-start` launch is trusted only when process liveness, PID file, runtime status,
  and launch-path evidence agree. A live process with mismatched evidence remains
  migration-required or unhealthy until the operator verifies the same run or restarts/falls back
  safely.

## Parallel Execution Contract

The daemon may stay one OS process, but runtime status must treat live and background work as
separate internal execution lanes.

Rules:

- Live recentchange suppression actions use the live lane.
- Reconciliation, catch-up, rolling last-24h verification, nightly full recheck, manual coverage,
  and one-shot command work use the background lane.
- A background lane backlog must not prevent a newly observed live edit from being accepted by the
  live lane or rejected with an immediate degraded-protection status.
- Queue, submit, completion, and processed-revision persistence are short transactions. No runtime
  status lock, processed-revision lock, or queue lock may be held while waiting on MediaWiki API
  calls, retry sleeps, page scans, or reconciliation loops.
- If a live action exceeds its immediate deadline or cannot enqueue because the live lane is full,
  runtime status records `latest_actionable_issue.source="live-hide"` and a non-healthy state.
- Background concurrency is bounded by the reviewed default API cap unless a later reviewed config
  decision changes it.
- Tests must prove that a blocked background lane does not force live lane queue-to-submit work to
  wait for the background lane to drain. Test timeouts are hang guards, not a fixed internal
  handoff SLA.
