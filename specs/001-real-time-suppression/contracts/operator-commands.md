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
- Default window is the preceding 30 minutes ending at now unless the operator supplies explicit bounds.
- Maximum automatic scope is configuration-driven; windows above the configured limit require an explicit operator override or report-only mode.

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

- Required start timestamp in RFC 3339 format with timezone.
- Required end timestamp in RFC 3339 format with timezone, or default `now`.
- Optional dry-run/report-only mode.
- Invalid, inverted, timezone-less, or over-limit windows must fail before API calls and explain the accepted input shape.

Output:

- Window summary.
- Per-outcome counts.
- Unresolved item list.
- Recommendation to rerun, retry, inspect rights/session, or manually review.

Success:

- 100% of checked eligible edits are counted as hidden, already-hidden, skipped, failed, or unresolved.
- Any unresolved eligible edit keeps the report actionable and prevents treating the accident window as fully closed unless an operator explicitly records the exception.

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

### Source-List Immediate Recovery

Purpose: Handle changes to `Удзельнік:Wizardist/SuppressionList` and source-adjacent request pages without waiting for reconciliation.

Inputs:

- Recentchange event for `Удзельнік:Wizardist/SuppressionList`.
- Recentchange event for `Вікіпедыя:Запыты да схавальнікаў` or a configured request-page title.
- Optional operator-triggered reload remains available, but it is not the primary path.

Output:

- Cache refresh outcome.
- Count of newly added and removed watched titles.
- Immediate catch-up trigger and title scope.
- Catch-up summary with hidden, already-hidden, skipped, failed, and unresolved counts.
- Actionable refresh or catch-up error when the source page or API fails.

Success:

- Newly added watched pages are checked immediately in a bounded recent window.
- The operator can see whether the source-list edit was handled, skipped as unchanged, or failed.

Failure:

- Refresh failure is reported as an unhealthy/actionable notice.
- Catch-up failure is summarized by root cause and unresolved count.
- The daemon does not silently ignore source-list refresh errors.

### Test Page Benchmark

Purpose: Produce production-safe end-to-end latency evidence using the approved bot test page.

Inputs:

- Test page title: `Удзельнік:Plaga med Bot/suppressor/tests`.
- Requested edit count.
- Optional run label.
- Optional dry-run/report-only mode for transport and catch-up checks.

Required wiki behavior:

- Automated benchmark edits may write only to `Удзельнік:Plaga med Bot/suppressor/tests`.
- Every benchmark edit must be submitted with the MediaWiki bot edit marker.
- Edit summaries must identify the run as a suppressor benchmark.
- Routine benchmark runs must not edit `Удзельнік:Wizardist/SuppressionList`; source-list behavior is tested only when explicitly requested.

Output:

- Run ID and test page title.
- Count of created bot-marked edits.
- Count hidden, already-hidden, failed, unresolved, and skipped.
- Publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timing samples.
- p50/p95/p99 only when sample size is sufficient; otherwise mark the run as smoke evidence.

Success:

- All benchmark revisions are hidden or explicitly accounted for.
- Timing evidence is safe to copy into operator docs.

Failure:

- Any unhidden benchmark revision is reported with revision ID, reason, and next action.
- Missing bot marker is a hard benchmark failure.

### Resource Economy Verification

Purpose: Prove the daemon and TUI remain suitable for low-spec local hardware while preserving realtime safety.

Inputs:

- Scenario name: idle daemon, daemon plus TUI, live edit, startup catch-up, source-refresh catch-up, benchmark, or failure storm.
- Optional sample duration.
- Optional report-only mode.

Output:

- Scenario and duration.
- RSS/memory summary when available.
- CPU summary when available.
- Maximum queue depth and API concurrency.
- State file size summary.
- Log volume summary and warning aggregation count.
- Any resource limit that was hit or approached.

Success:

- Resource use remains bounded and the realtime/recovery targets are still met.
- Warning coalescing prevents repeated root-cause failures from flooding the terminal.

Failure:

- Unbounded queue/state/log growth, hot-loop CPU use, or unacceptable memory growth blocks production-readiness claims until fixed or explicitly documented as a release limitation.

## TUI Action Placement

- Keep the Actions list short and operator-focused.
- Prefer adding "Emergency catch-up" and "Coverage report" only if they map to implemented one-shot commands.
- Keep manual cache reload and nightly reconciliation visible as slower diagnostic/fallback actions, not as the expected live hiding path.
- Add benchmark entry points only if they are clearly labeled as test-page actions and cannot accidentally target production sensitive pages.
- Prefer one-shot resource verification commands or docs-guided measurement over always-on heavy profiling.
