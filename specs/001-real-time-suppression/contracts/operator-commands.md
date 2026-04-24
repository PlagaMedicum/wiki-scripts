---
docmeta:
  status: draft
  review: feature-local
  purpose: Operator command contract for real-time suppression recovery.
  source: speckit-plan on 2026-04-24
---

# Contract: Operator Commands


## Existing Surfaces To Preserve

- Start daemon
- Start dry-run
- Stop daemon
- Check auth
- Print config
- Post reload signal
- Queue nightly reconciliation
- Refresh status
- Hide one revision by ID

## New Or Changed Operator Actions

### Emergency Catch-Up

Purpose: Check recent watched-page edits and hide or report eligible unresolved exposure quickly.

Inputs:

- Optional bounded duration or start/end window.
- Optional dry-run mode.

Output:

- Counts for checked, hidden, already-hidden, skipped, failed, and unresolved edits.
- Compact unresolved item list with page title, revision ID, age, reason, and next action.
- No hidden text or raw sensitive comments.

Success:

- Eligible recent edits are hidden or reported unresolved within the configured recovery target.

Failure:

- Rights/session failures report a blocked state.
- API/network failures report retrying, failed, or unresolved outcomes.

### Accident-Window Coverage

Purpose: Verify that edits in a known incident window are accounted for after suppressor-rights or realtime failures.

Inputs:

- Required start timestamp.
- Required end timestamp or default "now".
- Optional dry-run/report-only mode.

Output:

- Window summary.
- Per-outcome counts.
- Unresolved item list.
- Recommendation to rerun, retry, inspect rights/session, or manually review.

Success:

- 100% of checked eligible edits are counted as hidden, already-hidden, skipped, failed, or unresolved.

### Realtime Health Refresh

Purpose: Show the latest realtime state without depending on manual cache reload.

Inputs:

- None.

Output:

- Daemon state.
- Realtime state and lag.
- Realtime stale threshold, recovery trigger, and latest reconnect reason when applicable.
- Queue depth.
- Last observed event, matched edit, queued action, successful hide, and latest actionable error.
- Recent latency summary when recent hide attempts exist.

Success:

- Operator can distinguish healthy, catching-up, stale, unhealthy, and blocked states.

## TUI Action Placement

- Keep the Actions list short and operator-focused.
- Prefer adding "Emergency catch-up" and "Coverage report" only if they map to implemented one-shot commands.
- Keep manual cache reload and nightly reconciliation visible as slower diagnostic/fallback actions, not as the expected live hiding path.
