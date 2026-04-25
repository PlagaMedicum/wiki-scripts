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
rtk cargo test --manifest-path suppressor/Cargo.toml -- --test-threads=1
```

If the known parallel test instability is resolved during implementation, also run:

```bash
rtk cargo test --manifest-path suppressor/Cargo.toml
```

Run the repo docs gate before close-out:

```bash
rtk python3 tools/doc_workflow.py all
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

## API Timestamp And Error Classification Check

1. Run a mocked MediaWiki API test where `rvstart` receives the daemon's serialized catch-up timestamp.
2. Confirm the timestamp has UTC second precision and no fractional component.
3. Run a mocked `badtimestamp` response and confirm the daemon records `api_code=badtimestamp`, operation `fetch-revisions`, and a non-retryable outcome.
4. Run mocked non-JSON, HTTP status, timeout, and network-failure responses.
5. Confirm runtime status and TUI output distinguish those cases without showing response bodies, cookies, tokens, hidden text, or raw comments.
6. Confirm repeated catch-up failures produce a summary count and safe sample titles instead of one terminal warning per watched page.

## Source-List Immediate Recovery Check

1. Simulate a recentchange event for `Удзельнік:Wizardist/SuppressionList`.
2. Mock the refreshed source page so it adds at least one watched title.
3. Confirm cache refresh diffs the old and new watched sets.
4. Confirm immediate bounded catch-up runs for newly added titles before the source-list edit is treated as handled.
5. Simulate a recentchange event for `Вікіпедыя:Запыты да схавальнікаў`.
6. Confirm the daemon runs the configured immediate recent-window catch-up or reports a clear actionable reason if it cannot.
7. Confirm refresh failures are visible in runtime status and are not silently ignored.

## Accident-Window Check

1. Choose a bounded start and end time covering the suppressor-rights accident or a controlled local test window.
2. Run the accident-window coverage action.
3. Confirm the report accounts for all checked eligible edits as hidden, already-hidden, skipped, failed, or unresolved.
4. Confirm unresolved items include page title, revision ID, age, reason, and next action without exposing sensitive content.

## Benchmark And Latency Evidence

1. Collect the existing `event_to_api_submit_latency_ms` and `immediate_hide_latency_ms` metrics during controlled runs.
2. Add or record an end-to-end event-observed-to-hide timing for each controlled eligible edit.
3. Summarize p50, p95, and p99 for normal live handling and for recovery-driven handling.
4. During a production-safe manual check, record publish-to-hide wall clock from the wiki timestamp or recent-changes observation to confirmed hidden state.
5. Use at least 100 controlled observations before claiming percentile compliance; smaller production-safe manual checks are smoke evidence, not SLO proof.
6. Compare the collected evidence with the feature targets for normal hiding, stale detection, and recovery completion.

## Bot Test Page Benchmark

Approved external test page:

```text
Удзельнік:Plaga med Bot/suppressor/tests
```

Rules:

- Automated and manual benchmark edits may write only to that test page.
- Every benchmark edit must be marked as a bot edit through the MediaWiki edit API.
- Edit summaries must include a suppressor benchmark run label.
- Benchmark content must be test-only and must not include sensitive payloads.
- Routine benchmark runs must not edit `Удзельнік:Wizardist/SuppressionList`; source-list behavior is tested separately and only when explicitly requested.

Benchmark flow:

1. Confirm the bot account is authenticated and has the required rights.
2. Create a unique run ID.
3. Submit the requested number of edits to `Удзельнік:Plaga med Bot/suppressor/tests` with the bot marker set.
4. Observe the edits through the realtime path or the explicit benchmark harness.
5. Confirm each benchmark revision is hidden or explicitly reported as already-hidden, failed, or unresolved.
6. Record publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings.
7. Mark runs with fewer than the documented percentile sample size as smoke checks, not SLO proof.
8. Copy final benchmark evidence into `suppressor/docs/operations.md` during release close-out.

## Resource Economy And Boundary Check

1. Run the daemon alone and record idle CPU, memory, queue depth, and state file sizes.
2. Run the daemon with the TUI open and repeat the same measurements.
3. Run a bounded startup catch-up, a source-refresh catch-up, and a mocked repeated-failure catch-up.
4. Confirm API concurrency, queue depth, retained outcomes, benchmark samples, and log output stay bounded.
5. Confirm repeated failures are coalesced into aggregate warnings and do not flood the TUI.
6. Inspect the code boundaries for stream ingestion, source refresh, catch-up, MediaWiki API transport, worker execution, runtime state, and TUI rendering.
7. Confirm cross-boundary data uses typed structs/enums or small function contracts rather than raw string conventions where stable behavior matters.
8. Record low-spec evidence and any remaining resource tradeoffs in `suppressor/docs/operations.md` and architecture notes in `suppressor/docs/implementation.md`; do not accept a tradeoff that lowers performance targets or drops durable documentation evidence.

## Durable Lesson Check

1. Confirm regression tests cover MediaWiki timestamp formatting, `badtimestamp` classification, source-list immediate catch-up, source-refresh failures, warning coalescing, and bot-marked benchmark edits.
2. Confirm implementation docs explain internal service boundaries and resource-economy defaults.
3. Confirm operations docs explain how to read classified errors, warning summaries, source refresh status, low-spec evidence, and benchmark output.
4. Confirm runtime-boundary docs list any new or changed state fields and their retention bounds.
5. Keep code comments limited to non-obvious protocol or safety rules that tests alone do not explain.

## Production Readiness Gate

Do not call the fix production-ready until:

- realtime live hide verification passes;
- silent-starvation and reconnect recovery verification passes;
- MediaWiki timestamp serialization and API error classification checks pass;
- source-list immediate recovery checks pass;
- accident-window coverage verification passes for the chosen window;
- latency evidence shows the target path and recovery path are within the documented thresholds, or the remaining gap is explicitly documented before release;
- resource-economy verification passes for daemon, TUI, catch-up, source-refresh catch-up, benchmark, and repeated-failure scenarios while preserving the realtime/recovery performance targets and enough documentation evidence for maintainers to repeat the checks;
- unresolved accident-window items are zero, or each remaining item has a documented owner, reason, next action, and explicit release decision;
- rights/session loss, blocked state, unrecoverable API errors, or stale realtime state after deployment are treated as release stop conditions until resolved or explicitly accepted for a dry-run/report-only release;
- unavailable external wiki conditions are documented with the exact checks that could not run and the narrower confidence claim that remains;
- suppressor tests pass with the documented command;
- repo docs workflow passes;
- operator docs describe realtime health, emergency catch-up, and coverage reports.
- maintained docs and targeted tests preserve the incident lessons required to prevent recurrence.

## Feature Close-Out Notes

- Durable operational lessons belong in `suppressor/README.md`, `suppressor/docs/operations.md`, `suppressor/docs/implementation.md`, `suppressor/docs/runtime-boundaries.md`, and `suppressor/docs/testing-strategy.md`.
- Temporary feature-local planning notes under `specs/001-real-time-suppression/` may be removed only after durable lessons and release evidence are copied into maintained suppressor docs and the branch history preserves the full feature trail.
