---
docmeta:
  status: draft
  review: feature-local
  purpose: Verification quickstart for real-time suppression recovery.
  source: speckit-plan on 2026-04-24
---

# Quickstart: Real-Time Suppression Recovery


## Operator Verification Goal

Prove that a running daemon hides new eligible watched-page edits automatically, reports realtime health truthfully, and can catch up recent missed edits without waiting for nightly reconciliation.

## Local Development Checks

Run from the repository root unless noted.

```bash
cd suppressor
cargo test -- --test-threads=1
```

If the known parallel test instability is resolved during implementation, also run:

```bash
cd suppressor
cargo test
```

Run the repo docs gate before close-out:

```bash
python3 tools/doc_workflow.py all
```

## Controlled Functional Checks

1. Start the daemon in dry-run or controlled test mode.
2. Feed or simulate a target-wiki edit event for a watched sensitive page.
3. Record the event-observed time, queue time, and hide completion time.
4. Confirm the live path records a matched edit and queues a hide without manual refresh.
5. Confirm the worker records hidden, already-hidden, skipped, retrying, failed, unresolved, or blocked outcome.
6. Confirm the TUI shows realtime state, lag, queue depth, recovery trigger, last matched edit, last queued action, and last successful hide or latest error.

## Silent-Starvation And Recovery Check

1. Start the daemon and confirm realtime state becomes healthy.
2. Simulate an open stream that stops producing items, plus explicit disconnect and invalid-resume cases.
3. Confirm realtime state becomes reconnecting, stale, or unhealthy within the freshness target even when no explicit stream error arrives.
4. Confirm bounded catch-up runs with a visible recovery trigger.
5. Confirm eligible missed edits are hidden or reported unresolved before the state returns to healthy.

## Accident-Window Check

1. Choose a bounded start and end time covering the suppressor-rights accident or a controlled local test window.
2. Run the accident-window coverage action.
3. Confirm the report accounts for all checked eligible edits as hidden, already-hidden, skipped, failed, or unresolved.
4. Confirm unresolved items include page title, revision ID, age, reason, and next action without exposing sensitive content.

## Benchmark And Latency Evidence

1. Collect the existing `event_to_api_submit_latency_ms` and `immediate_hide_latency_ms` metrics during controlled runs.
2. Add or record an end-to-end event-observed-to-hide timing for each controlled eligible edit.
3. Summarize p50 and p95 for normal live handling and for recovery-driven handling.
4. During a production-safe manual check, record publish-to-hide wall clock from the wiki timestamp or recent-changes observation to confirmed hidden state.
5. Compare the collected evidence with the feature targets for normal hiding, stale detection, and recovery completion.

## Production Readiness Gate

Do not call the fix production-ready until:

- realtime live hide verification passes;
- silent-starvation and reconnect recovery verification passes;
- accident-window coverage verification passes for the chosen window;
- latency evidence shows the target path and recovery path are within the documented thresholds, or the remaining gap is explicitly documented before release;
- suppressor tests pass with the documented command;
- repo docs workflow passes;
- operator docs describe realtime health, emergency catch-up, and coverage reports.
