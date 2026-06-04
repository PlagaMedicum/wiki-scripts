# Daemon Refactor Plan

## Summary

There must be one active daemon runtime. The daemon should stay simple by design, but it must use
bounded concurrency where that protects live hiding and lets background recovery keep making
progress.

The 2026-06-04 source-list incident showed the current gap: the deployed daemon refreshed
`Удзельнік:Wizardist/SuppressionList` to revision `5150248` and loaded the newly added title, but it
did not schedule history suppression for that title. The fix belongs in the active daemon path, not
in retained or aspirational runtime code.

## Decisions

- Keep one active daemon implementation in `daemon.rs`.
- Keep daemon types named directly after their domain: `Daemon` and `DaemonState`.
- Use only `daemon_state.json` for daemon-owned pending/quarantine state.
- Do not add legacy state loading, aliases, or dual writes. Commit history is the legacy store.
- Keep live hiding behavior stable while adding source-list history sync.
- Do not switch this slice to the larger `AppRuntime` command/recovery runtime.

## Scheduler

- High-priority work is live watched-edit hiding.
- Low-priority work is source-list refresh, newly added title history sweep, and manual catch-up.
- Low-priority work runs while no high-priority task is queued or active.
- If high-priority work appears, low-priority work pauses at the next safe transaction boundary.
- After high-priority work completes, low-priority work resumes.
- Keep bounded defaults conservative: one live worker and one low-priority worker.
- Do not hold daemon state, processed-revision, or status persistence locks across MediaWiki API
  calls.

## Source-List Sync

- A source-list edit is still handled as a watched live edit.
- The same edit also enqueues low-priority source refresh.
- Automatic metadata refresh uses the same refresh planner.
- Refresh compares old and new watched-title snapshots.
- Newly added watched titles enqueue whole-history sweeps.
- Removed titles are recorded only.

## Whole-History Sweep

- Fetch all revisions for newly added titles with `fetch_revisions(title, None)`.
- Process newest-to-oldest.
- Treat each revision hide as one low-priority transaction boundary.
- Skip already hidden revisions and already processed revision IDs.
- Hide visible `user|comment` with source label `source-list-history`.
- Transient failures enter pending retry.
- Terminal permission or `cantdelete` failures enter quarantine and remain operator-visible without
  killing the daemon.

## Tests

- No removed daemon module, type, wording, or state-file references remain.
- Clippy and Ruff remain the primary quality guardrails. Do not add custom quality tooling when an
  established lint/test tool can cover the same risk.
- `daemon_state.json` is the only daemon state file.
- Low-priority work runs when high-priority work is idle.
- High-priority work pauses low-priority work at a transaction boundary.
- Low-priority work resumes after high-priority completion.
- Source-list edits and automatic refreshes enqueue added-title history sweeps.
- Added-title history sweeps hide all visible revisions and skip already hidden revisions.
- Transient failures enter pending retry; terminal failures enter quarantine.

## Verification

- `rtk cargo fmt --check`
- `rtk cargo test daemon`
- `rtk cargo test cache::source`
- `rtk cargo test --lib -- --test-threads=1`
- `rtk make -C suppressor test` outside the sandbox if local mock ports are blocked
