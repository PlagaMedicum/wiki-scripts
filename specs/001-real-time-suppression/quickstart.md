---
docmeta:
  status: draft
  review: feature-local
  purpose: Verification quickstart for real-time suppression recovery.
  source: speckit-plan on 2026-04-29
---

# Quickstart: Real-Time Suppression Recovery


## Verification Goal

Prove that the running suppressor:

- hides eligible watched-page edits automatically in realtime
- recovers missed coverage from the last successful hide after downtime or failure
- performs randomized rolling last-24h daytime verification and randomized nightly full rechecks
- shows truthful operator-first runtime status
- preserves or explicitly explains compatibility for the actual deployment path in use

Important architectural limit: the suppressor observes edits after MediaWiki publishes them.
Verification should minimize and measure publish-to-hide exposure, but it must not claim guaranteed
zero first-view prevention.

## Primary Status Questions

During verification, the primary status view should let a human answer these questions immediately:

- Is protection working now?
- What exact work is active right now?
- What is the truthful lag right now?
- When was the last successful hide, and for which revision?
- What is the latest actionable issue?
- How long has this daemon been running continuously?

If the TUI instead makes the operator infer that from resume-cursor JSON, checkpoint counters, or
ambiguous status jargon, the verification run should be treated as failed even if hiding still
works underneath.

## Local Development Checks

Run from the repository root unless noted.

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

If parallel instability is resolved during implementation, also run:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml
```

Run the repo docs gate before close-out:

```bash
rtk python3 tools/doc_workflow.py all
```

## Compatibility Approval Check

Before trusting a new version in the operator environment:

1. Confirm release evidence states whether the previously documented setup is still valid.
2. If not, confirm the evidence names the new authoritative verification path, the required human
   approval checkpoint, the operator migration steps, and the fallback or rollback path to the last
   trusted workflow.
3. Confirm stale or incompatible prior artifacts produce migration-needed or non-healthy diagnostics
   rather than a false healthy reading.

## Actual Launch-Path Check

1. Confirm whether this host is using:
   - a TUI-managed daemon child
   - a `systemd`-managed daemon
   - another explicit supervisor path
2. Treat only the actual launch path in use as authoritative for this run.
3. If the daemon is not running under `systemd`, do not treat `journalctl -u suppressor.service` as
   authoritative evidence.
4. Confirm `runtime_status.json` is the daemon-owned realtime surface and `command_report.json` is
   only the last bounded one-shot command result.

## Realtime Protection Check

1. Start the daemon in live or dry-run mode.
2. Confirm the primary status view shows one clear protection state row with PID and uptime.
3. Feed or simulate a watched-page recentchange event.
4. Confirm the status view updates:
   - current work
   - lag
   - last observed watched edit
   - last successful hide
   - latest actionable issue
5. Confirm a successful path hides the revision or, in dry-run mode, records exactly what would
   have been hidden.
6. Confirm the revision ID is rendered as a direct browser-openable link or URL.

## Recovery Anchor Check

1. Record the current `last_successful_hide_at`.
2. Simulate downtime, stream failure, or missed events after that point.
3. Restart or recover the daemon.
4. Confirm automatic recovery labels its scope as `since last successful hide` or another explicit
   trusted fallback anchor if the primary timestamp is unavailable.
5. Confirm the daemon does not declare healthy until edits in that scope are hidden or reported
   unresolved.
6. Confirm a reconnect without a real missed gap does not get mislabeled as full startup recovery.

## Daytime Rolling Last-24h Verification Check

1. Keep the daemon running through a randomized daytime scheduler interval.
2. Confirm a verification run occurs for a rolling `now-24h .. now` window, not a calendar-day
   window from midnight.
3. Confirm the operator surface records the exact covered window and distinguishes it from other
   recovery work.
4. Confirm the run remains bounded under repeated throttling and preserves compact warning summaries.

## Nightly Full Recheck Check

1. Keep the daemon running through the configured night window.
2. Confirm a full watched-set recheck runs at a randomized night hour.
3. Confirm the operator surface names it as a full watched-set recheck, not as last-24h
   verification.
4. Confirm compatibility remains intact if new scheduler fields were added; otherwise confirm a
   migration notice exists.

## Emergency Catch-Up Check

1. Trigger `Emergency catch-up`.
2. If a recovery anchor exists, confirm the command defaults to the anchor-to-now window.
3. Otherwise confirm it uses the bounded recent emergency window documented by config.
4. Confirm the command emits a bounded command report and does not overwrite daemon realtime truth.
5. Confirm unresolved items carry safe revision links and next actions.

## Coverage: Last 24 Hours Check

1. Trigger the `Last 24 hours` preset from the TUI or equivalent command path.
2. Confirm the report label is exactly `Last 24 hours`.
3. Confirm the output shows the exact rolling start and end timestamps.
4. Confirm the action does not crash because of missing timestamp input.
5. Confirm the result remains visibly distinct from an arbitrary timestamped coverage report.

## Source Refresh Check

1. Simulate an edit to `Удзельнік:Wizardist/SuppressionList`.
2. Confirm the operator surface shows:
   - whether the watched set changed
   - added and removed title counts
   - whether immediate catch-up started or was deferred
3. Simulate a request-page change for `Вікіпедыя:Запыты да схавальнікаў`.
4. Confirm the source-refresh outcome is visible and actionable, not a silent cache reload.

## Throttle And Backoff Check

1. Run mocked or controlled `HTTP 429` cases with and without `Retry-After`.
2. Confirm live, recovery, and verification paths classify the error consistently.
3. Confirm the primary status view shows degraded protection or backoff instead of a false healthy
   state.
4. Confirm repeated-root-cause failures stop or pause early and keep unresolved samples bounded.

## TUI Truthfulness Check

1. Open the TUI while the daemon is running.
2. Trigger a one-shot command such as emergency catch-up or last-24h coverage.
3. Confirm the primary status view still reflects daemon-owned realtime truth.
4. Confirm command logs and daemon logs are visibly distinct.
5. Confirm latest-follow mode shows the newest rendered rows even when log lines wrap.
6. Confirm secondary diagnostics do not push current protection state out of the primary view.

## Benchmark And Resource Check

1. Use the approved test page:

```text
Удзельнік:Plaga med Bot/suppressor/tests
```

2. Confirm benchmark edits are bot-marked and test-only.
3. Measure publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings.
4. Confirm runtime lag uses truthful wall-clock calculation and is not pinned to `0s`.
5. Measure idle and active CPU, memory, queue depth, state size, and warning-summary counts for the
   daemon alone and daemon plus TUI.
6. Confirm bounded-state behavior under repeated failure storms.

## Production Readiness Gate

Do not treat the fix as production-ready until all of the following are true:

- live protection checks pass
- recovery-from-last-successful-hide checks pass
- rolling last-24h daytime verification checks pass
- randomized nightly full recheck checks pass
- emergency catch-up and `Last 24 hours` preset checks pass
- source-refresh checks pass
- throttle and backoff checks pass
- TUI truthfulness checks pass
- compatibility approval and launch-path checks pass
- suppressor tests pass
- docs workflow passes
- maintained docs describe the new operator workflow, compatibility expectations, and architectural
  limit honestly
