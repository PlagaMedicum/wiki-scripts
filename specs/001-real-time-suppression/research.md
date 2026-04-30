---
docmeta:
  status: draft
  review: feature-local
  purpose: Design research decisions for real-time suppression recovery.
  source: speckit-plan on 2026-04-29
---

# Research: Real-Time Suppression Recovery


## Decision: Automatic recovery anchors on `last_successful_hide_at`

**Rationale**: The clarified requirement is that if the daemon was offline, stalled, or recovered
from a stream error, it must cover watched-page exposure from the last known successful hide, not
from an arbitrary recent fixed window. The runtime state already persists `last_successful_hide_at`,
so the safest compatible design is to treat that timestamp as the primary recovery anchor and use an
older documented trusted anchor only when this value is missing or unreadable.

**Alternatives considered**:

- Keep a fixed recent recovery window such as 60 seconds or 30 minutes. Rejected because it is the
  behavior that still lets missed edits wait for nightly reconciliation.
- Recover only from the last observed stream event or cursor. Rejected because reconnect noise and
  resume-cursor ambiguity do not prove live hides succeeded.
- Recover from midnight or the next daytime sweep. Rejected because the requirement is tied to the
  last successful suppression action, not calendar boundaries.

## Decision: Keep three distinct verification scopes

**Rationale**: The feature now has three operator-meaningful recovery or verification scopes that
must not be conflated:

- gap recovery from `last_successful_hide_at` to now
- randomized daytime rolling last-24h verification
- randomized nightly full watched-set recheck

Keeping these scopes distinct makes the operator surface readable and prevents a successful rolling
verification from being misread as full recovery of a missed gap, or vice versa.

**Alternatives considered**:

- Use one generic “reconciliation” label for all non-live work. Rejected because it hides the exact
  coverage window and is the root of the current operator confusion.
- Replace nightly full recheck with repeated rolling last-24h runs only. Rejected because the user
  explicitly wants both.
- Treat the daytime run as “current day since midnight”. Rejected because the approved behavior is
  a rolling last 24 hours window.

## Decision: Preserve current config surfaces additively where practical

**Rationale**: The constitution now requires a compatibility strategy, approval point, and rollback
path before incompatible setup changes. The current config already has `[current_day_recheck]` and
`[nightly_sweep]`. The least disruptive approach is to keep those sections loading and reinterpret
or extend them compatibly:

- `[current_day_recheck]` continues to provide the randomized daytime delay range, but the work it
  schedules becomes rolling last-24h verification.
- `[nightly_sweep]` remains the nightly full recheck section, with optional additive fields only if
  the randomized night-hour selection needs more than the current single `start_time`.

**Alternatives considered**:

- Rename config sections immediately and require manual migration now. Rejected because operator
  surfaces and local config are already in use.
- Keep the old names and old behavior unchanged. Rejected because the behavior itself is wrong.
- Add a second parallel scheduler config tree and deprecate the first in the same release. Rejected
  because it adds complexity before the operator-surface problem is solved.

## Decision: Reserve daemon realtime truth for the daemon only

**Rationale**: The long-running daemon must remain the only writer of realtime health. One-shot
commands such as emergency catch-up, last-24h coverage verification, and nightly recheck requests
may emit bounded stdout summaries and `command_report.json`, but they must not overwrite or
impersonate daemon-owned `runtime_status.json`.

**Alternatives considered**:

- Let one-shot commands continue to bootstrap a runtime and write the same status file. Rejected
  because it makes the TUI show command activity as if the daemon itself entered recovery.
- Remove command reports entirely. Rejected because operators still need bounded command results.
- Infer daemon truth from logs only. Rejected because the operator surface must remain immediately
  actionable.

## Decision: Design the TUI around operator questions, not internal counters

**Rationale**: The status panel should answer a small set of human questions first:

- Is protection working now?
- What background work is active?
- What is the current recovery or verification window?
- What was the last successful hide?
- What is the latest actionable problem?
- How long has the daemon been protecting edits?

Internal counters such as raw resume cursors, checkpoint counts, or processed-ring sizes may still
exist, but they belong in secondary diagnostics, not the primary operator view.

**Alternatives considered**:

- Keep the current mixed status panel and just rename a few rows. Rejected because the operator
  still cannot tell what matters now.
- Hide all diagnostics and show only a single health word. Rejected because recovery scope, latest
  error, and last successful hide are operationally necessary.
- Move all detail into logs. Rejected because logs are less trustworthy during incidents than a
  compact primary status summary.

## Decision: Report lag and last meaningful events with direct operator context

**Rationale**: Current `lag=0s` is misleading because it is only set on event observation and not
  recalculated. The runtime contract should instead expose a wall-clock lag estimate with sub-second
  precision when appropriate, plus operator-meaningful last-event summaries:

- last observed target-wiki event
- last matched watched-page revision
- last successful hide
- latest actionable error or degraded state

Whenever safe, revision identifiers should carry direct browser-openable URLs so the operator can
inspect them from the terminal without a separate lookup action.

**Alternatives considered**:

- Keep integer seconds only. Rejected because `0s` hides useful timing detail.
- Keep raw `last_event_id` JSON as the main recent-event field. Rejected because it is a transport
  cursor, not a human-readable operator fact.
- Add a separate “open in browser” action instead of link rendering. Rejected because the user
  explicitly asked only for direct link rendering.

## Decision: Make emergency catch-up useful by defaulting to the active recovery anchor when possible

**Rationale**: The operator complaint about emergency catch-up being useless is valid if the command
defaults to an arbitrary recent window while the real missed period started earlier. The most useful
default is:

- if the daemon has an active or recent recovery anchor from `last_successful_hide_at`, use that
  anchor to `now`
- otherwise use a bounded recent emergency window

This keeps the command aligned with the actual protection gap without forcing the operator to supply
timestamps every time.

**Alternatives considered**:

- Keep a hard-coded recent default forever. Rejected because it does not match the failure mode.
- Force start and end timestamps every time. Rejected because the operator specifically wants a
  practical incident tool.
- Always run a full watched-set recheck. Rejected because it is too expensive for a default action.

## Decision: Provide an explicit operator-visible `Last 24 hours` preset

**Rationale**: The current `coverage-report` command requires `--start`, which makes the TUI action
crash and hides the intended routine verification flow. A dedicated preset should create a rolling
last-24h window, label it explicitly in the operator surface, and keep that label distinct from
arbitrary timestamped coverage reports.

**Alternatives considered**:

- Keep generic timestamp entry only. Rejected because the user asked for an explicit last-24h
  preset and the current TUI cannot supply free-form timestamps.
- Reuse emergency catch-up for this purpose. Rejected because emergency catch-up is a recovery
  action, while last-24h verification is a routine evidence action.
- Hide the action until prompt support exists. Rejected because the operator wants this available
  now.

## Decision: Keep full watched-set catch-up for true bootstrap, verified gaps, or explicit full checks

**Rationale**: Ordinary EventStreams reopen noise should not trigger a full startup recovery. Full
watched-set work should remain limited to cases where the operator can defend the cost:

- true daemon bootstrap
- verified gap recovery where the gap scope demands it
- explicit operator request
- randomized nightly full recheck

All other reopen or reconnect cases should use the narrowest truthful recovery needed.

**Alternatives considered**:

- Keep triggering full startup catch-up on every stream `Open`. Rejected because it wastes API
  budget and keeps the daemon in `catching-up` too often.
- Disable all automatic catch-up on reconnect. Rejected because real gaps still need bounded
  backfill.
- Always recover only title deltas. Rejected because daemon-wide outage gaps affect more than new
  titles.

## Decision: Keep rate limiting and repeated-root-cause backoff as a first-class contract

**Rationale**: The current production failures are largely `HTTP 429` non-JSON responses on both
catch-up and live paths. Recovery, rolling verification, and nightly recheck must therefore share a
common throttle contract: classify the cause, expose `Retry-After` or local backoff, pause or stop
early under one repeated root cause, and retain only bounded unresolved samples.

**Alternatives considered**:

- Treat `429` like a generic retryable error with no operator context. Rejected because the user
  needs to see why protection is degraded now.
- Keep scanning every page and persisting every unresolved item. Rejected because it creates noisy
  state and burns API budget under a single transient fault.
- Disable verification under any throttle condition. Rejected because bounded resume is still
  required.

## Decision: Treat scheduled verification failure and full-recheck freshness as protection-trust evidence

**Rationale**: The latest runtime artifacts showed a failed scheduled reconciliation after only a
small amount of progress, `last_daytime_verification_at=null`, `last_nightly_full_recheck_at=null`,
and a checkpoint map whose oldest full-check timestamps are years old. That means operator trust is
not determined by stream freshness alone. The design must treat two things as first-class evidence:

- whether the latest daytime or nightly verification succeeded
- how stale the full watched-set checkpoint map currently is

The operator surface therefore needs explicit freshness evidence such as oldest full-check age,
oldest sample title, and stale-page count, and a failed scheduled verification must remain visible
as a real issue until a later successful run clears it.

**Alternatives considered**:

- Keep scheduled verification failure in raw logs only. Rejected because the operator already could
  not see the lag clearly enough from the current surface.
- Show only the number of checkpoint pages. Rejected because `1427` checkpoint pages says nothing
  about whether the newest full check is today or years old.
- Clear degradation as soon as the stream reopens. Rejected because healthy stream transport does
  not prove nightly or daytime verification actually caught up.

## Decision: Cross-check daemon runtime truth against the live process path

**Rationale**: The latest runtime inspection also showed a persisted `daemon_state="running"` and a
PID file for a process that no longer existed. The plan must therefore preserve the daemon-owned
status surface, but verification and operator guidance must still cross-check it against the actual
live process path so stale artifacts cannot masquerade as current protection.

**Alternatives considered**:

- Trust `runtime_status.json` unconditionally. Rejected because stale files can outlive the daemon.
- Trust the PID file only. Rejected because the status surface still carries the higher-level
  recovery and verification truth when the process is actually alive.
- Move all truth into external supervisor logs. Rejected because the feature still requires a
  machine-readable local runtime contract.

## Decision: Preserve one binary with microservice-like internal boundaries

**Rationale**: The operator asked for a better architecture, but the repo constitution and local
deployment model still favor one local daemon plus TUI. The right improvement is stronger internal
service boundaries, not more OS services. Recovery, scheduling, status, and TUI work should be
modular and testable without adding processes, ports, or a public monitoring surface.

**Alternatives considered**:

- Split status, worker, or scheduler into separate services now. Rejected because it adds operator
  burden and runtime cost without solving the immediate trust problem.
- Keep broad shared state and patch locally. Rejected because ambiguous ownership is part of the
  bug.
- Add a public dashboard. Rejected as outside the current scope.

## Decision: Verify the real deployment path and include a release approval checkpoint

**Rationale**: The host evidence already showed that the actual authoritative launch path is the
TUI-managed child process, not a default installed `systemd` unit. Because operator surfaces and
launch-path assumptions are part of the compatibility contract now, the release evidence must state:

- whether the previous setup still works
- the required human approval point before trusting the new setup
- any migration steps
- the fallback or rollback path to the last trusted workflow

**Alternatives considered**:

- Treat release notes or chat history as enough. Rejected because the runtime and docs themselves
  must remain trustworthy during incidents.
- Assume `systemd` is authoritative for all deployments. Rejected because it is false on the
  operator’s host.
- Defer compatibility evidence until after implementation. Rejected by the constitution.

## Decision: Keep the post-publication architectural limit explicit

**Rationale**: Even after these fixes, the daemon still reacts after MediaWiki publishes an edit.
The design should optimize and measure detection and hide latency, but docs and operator surfaces
must not imply a guarantee of zero first-view prevention.

**Alternatives considered**:

- Promise zero first-view exposure once the daemon is healthy. Rejected because it is not
  technically defensible for EventStreams-based post-publication handling.
- Ignore the limitation in docs. Rejected because the operator specifically wants trustworthy
  evidence.
- Broaden this feature into in-wiki pre-publication blocking. Rejected because it changes tool
  scope and deployment model.
