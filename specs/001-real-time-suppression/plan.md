---
docmeta:
  status: draft
  review: feature-local
  purpose: Implementation plan for restoring urgent real-time suppressor hiding.
  source:
  - speckit-plan on 2026-04-29
  - speckit-plan stabilization update on 2026-05-05
  - speckit-plan config-stability update on 2026-05-06
---

# Implementation Plan: Real-Time Suppression Recovery


## Summary

Restore `suppressor` as a trustworthy real-time protection daemon for be.wikipedia.org sensitive
pages. The remaining work is not only faster hiding; it is also truthful recovery and truthful
operator evidence. Recovery must anchor on the last recorded successful hide, daytime verification
must recheck a rolling last 24 hours window at randomized intervals, nightly fallback must perform
a randomized full watched-set recheck, and the operator surface must clearly show whether
protection is working now, what recovery or verification is active, what the last meaningful hide
was, what problem requires action, and whether full watched-set coverage is becoming stale. A
failed scheduled verification or an overdue full watched-set checkpoint map must not disappear
behind a later healthy stream reopen. The implementation should preserve the current single local
daemon plus TUI deployment, keep status and command surfaces backward-compatible where practical,
and emit explicit migration or fallback guidance when compatibility cannot be preserved.

Constitution v1.8.0 puts this feature under an active human-safety freeze and makes config surfaces
human-reviewed operator contracts. The current plan is
therefore a stabilization reset: defer unrelated work, broad refactors, cosmetic TUI polish, new
services, and nonessential optimization until the minimal server-runnable daemon MVP is proven. The
critical path is automatic live hiding, automatic recovery/reconciliation, nightly fallback, shared
throttle/backoff safety, truthful non-healthy status, actual-launch-path verification, a repeatable
aarch64 Linux musl release build ready for `rsync` to the server, and a one-command detached
server-start path from the deployed binary. Config churn is not part of this MVP path: any config
file, schema, default, environment-variable, loading-semantic, or deployment-required-section change
must be motivated, explicitly human-reviewed, compatibility-tested, and rollback-safe before it can
support production trust.

## Technical Context

**Language/Version**: Rust edition 2024 in the existing `suppressor` crate
**Primary Dependencies**: `tokio`, `reqwest`, `reqwest-eventsource`, `serde`, `serde_json`,
`chrono`, `rand`, `tracing`, `metrics`, `clap`, `ratatui`, `crossterm`, `wiremock`
**Storage**: Local JSON/text state under `suppressor/state/`, including
`runtime_status.json`, `command_report.json`, `processed_revids.json`,
`nightly_sweep_progress.json`, `last_event_id.txt`, `daemon.pid`, server-start log evidence, and
the suppression-list cache
**Testing**: MVP gate uses `rtk cargo test --manifest-path suppressor/Cargo.toml --
--test-threads=1`, targeted tests for shared throttle/backoff, runtime-status truth, daemon-vs-
command isolation, scheduler/reconciliation visibility, and a dry-run or controlled live
launch-path smoke check. Full `rtk cargo test --manifest-path suppressor/Cargo.toml`, controlled
benchmark checks against `Удзельнік:Plaga med Bot/suppressor/tests`, and the repo docs gate remain
release evidence but must not displace the live daemon stabilization path. Test and server-build
evidence is fresh only for the source tree that produced it: any later daemon-critical edit to
`suppressor/src/`, `suppressor/tests/`, `suppressor/Cargo.toml`, `suppressor/Cargo.lock`,
`suppressor/Makefile`, or build/deployment code invalidates the prior T037/T038 evidence. T037 and
T038 must be rerun after Phase 2, US1, and US2 have changed daemon-critical paths before their
checkmarks can count as final MVP gate evidence.
**Target Platform**: Linux local host running one daemon plus the local supervisor TUI for
be.wikipedia.org; deployment artifact target is
`target/aarch64-unknown-linux-musl/release/suppressor` built with
`cargo zigbuild --release --target aarch64-unknown-linux-musl` for rsync to the server. The target
server must be able to execute that static aarch64 Linux binary, run one local shell command,
preserve a child detached by the binary after SSH logout, reach be.wikipedia.org, and write the
configured state directory, PID file, runtime-status file, cache files, and detached log path. The
server host must support an additive `server-start` command that starts the daemon detached from the
SSH terminal without relying on systemd, tmux, screen, shell backgrounding, or shell `nohup`.
**Project Type**: Single Rust CLI/daemon/TUI tool inside `suppressor/`
**Performance Goals**: At least 95% of eligible live edits hidden within 1 second and 99% within
5 seconds under normal availability; stale or ineffective protection surfaced within 10 seconds;
recovery from missed edits since the last successful hide completed or reported unresolved within 2
minutes for gaps up to 30 minutes; at least one randomized daytime rolling-24h verification and
one randomized nightly full recheck recorded per uninterrupted 24-hour daemon period; failed
scheduled verification or stale full watched-set coverage surfaced to the operator within 10
seconds of status inspection
**Resource Goals**: MVP defaults must keep live hiding isolated from slower work. Initial release
budgets: live hide queue bounded to a configured cap with visible degradation before saturation;
catch-up/reconciliation API concurrency no higher than 2 by default; live hide execution not blocked
behind scheduled reconciliation; unresolved samples capped to a small operator list; warning
summaries capped and coalesced by root cause; normal status/report state kept compact enough for
local JSON reads; normal logs rate-limited so repeated API failures do not create log storms; no
busy loops; idle daemon plus TUI must be measured on the deployment host; any budget relaxation must
be documented with evidence and must not delay live hiding or hide non-healthy status. The MVP
resource sample must record CPU percentage, RSS memory, live and recovery/reconciliation queue
depths versus caps, API concurrency, `runtime_status.json`, `command_report.json`, and
`processed_revids.json` size, detached log growth rate, and coalesced-warning counts for at least a
10-minute idle window and one active live/recovery/backoff window. Release is blocked unless queue
pressure becomes degraded before saturation, API concurrency stays at or below the default cap of 2,
status/report files remain below 1 MiB each, repeated-root-cause log growth stays below 10 MiB/hour
or has a documented mitigation, and active samples return to a stable idle baseline without
monotonic growth.
**Compatibility/Migration**: Preserve the current config layout and machine-readable status/report
surfaces additively where possible. Existing `current_day_recheck` settings should continue to load
as the scheduler input for daytime rolling-24h verification until a compatible rename or alias is
introduced. Existing `nightly_sweep` settings remain valid, with optional additive fields if
randomized nightly-hour selection needs more configuration. `runtime_status.json` and
`command_report.json` must continue to load older shapes safely; missing new fields must degrade to
non-healthy or migration-needed diagnostics instead of false healthy status. Add `server-start` as
a new CLI entrypoint; keep `run`, `dry-run`, TUI-managed start, systemd assets, and one-shot
commands available. The detached start path must identify itself as the active launch path in
operator evidence and must not silently replace systemd/TUI assumptions. If a new operator
workflow, launch path, or machine-readable surface cannot remain compatible, the release must ship
an explicit approval point, migration steps, and fallback or rollback path to the last trusted
workflow before it is treated as production-ready. Add the server build path additively to
`suppressor/Makefile`; the existing `build` and `release` targets remain unchanged, and the new
target prints the rsync-ready artifact path.
**Config Change Review**: The tracked `suppressor/config.toml`, config schema, defaults,
environment variable names, config loading behavior, and deployment-required config sections are
stable operator contracts. This plan does not authorize unreviewed config churn, ad-hoc server
config edits, required-key additions, default changes, or renamed sections as implementation
shortcuts. A config-affecting change is allowed only after the active feature records the concrete
runtime/safety/operator-control motivation, explicit human review evidence, backward-compatible
behavior or migration-needed diagnostic, compatibility fixture for the previous config, exact
migration steps if needed, rollback/fallback to the last trusted config, and target-server launch
verification. The 2026-05-06 target-host failure with `missing field realtime` is therefore a
blocked config-compatibility gate: do not patch the server config in the background; either prove
the tracked config baseline is the reviewed deployment contract and migrate it explicitly, or
implement a reviewed backward-compatible loader or migration-needed diagnostic that fails safely
without claiming healthy daemon status.
**Constraints**: Keep scope limited to be.wiki public RevDel for `user|comment`; do not log
sensitive article text, hidden content, tokens, cookies, or credentials; do not rely on manual
reload or nightly reconciliation as the primary live-protection path; do not add extra OS services
or public network surfaces for this feature; keep operator labels plain-language and directly
actionable; render safe revision identifiers as clickable URLs or equivalent browser-openable
targets; report lag truthfully with sub-second detail when the value is under one second; detached
server start must not log secrets, must not fabricate config or auth material, must not leave a
child attached to the operator's terminal, and must not report success until PID and runtime-status
evidence are trustworthy
**Architecture Constraints**: Preserve one deployable daemon/TUI package, but keep internals
microservice-like: stream ingestion, cache refresh, catch-up, verification scheduling, MediaWiki
transport, worker execution, runtime state, command reports, and TUI rendering communicate through
explicit structs, enums, and bounded channels. The long-running daemon remains the only writer of
daemon realtime truth. One-shot commands may emit bounded report surfaces but must not overwrite the
daemon-owned runtime status surface
**Minimalism Constraints**: Prefer additive changes to existing modules and state files. Avoid new
dependencies, new always-on background loops, new persistent artifacts, or large refactors unless
they directly improve correctness, compatibility, observability, or bounded resource behavior for
this incident
**Scale/Scope**: Approximately 1.4k watched titles, one live recentchange stream, one local
operator, one daemon process, bursty recentchange input, and no new public network service

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Gate status**: PASS before Phase 0. PASS after Phase 1 design.

- Separate Tools First: PASS. The work stays inside `suppressor`, which already owns sensitive-page
  suppression.
- Explicit Boundaries, Minimal Coupling: PASS. The plan keeps stream, cache, recovery, scheduler,
  worker, status persistence, one-shot commands, and TUI contracts explicit within one binary.
- Narrow, Risk-Based Scope: PASS. The feature restores trustworthy live suppression and operator
  verification for be.wiki only; it does not broaden into general moderation or remote operations.
- Deterministic Documentation, Safe Writes, And Honest Status: PASS. Feature artifacts are updated
  in place. The plan explicitly forbids silent status-surface drift and requires authoritative
  daemon truth plus compatibility diagnostics.
- Stable Config, Compatibility, Non-Destructive Change, And Explicit Approval: PASS with required
  implementation follow-through. The design is compatibility-first, additive where practical, and
  names migration, rollback or fallback, and the human approval checkpoint for incompatible
  operator surfaces, launch-path assumptions, or config-affecting changes. No config change may be
  treated as production-valid without recorded motivation, explicit human review, compatibility or
  migration evidence, target-server verification, and rollback/fallback notes.
- Spec Kit First For Non-Trivial Work: PASS. This plan follows the updated `spec.md`; `tasks.md`
  must be regenerated from this plan before implementation continues.
- Resource Economy, Robustness, And Durable Lessons: PASS. The plan includes bounded state,
  concurrency, logging, and low-spec verification without relaxing latency or recovery goals.
- Active Human-Safety Freeze For Suppressor MVP: PASS. The active pointer is
  `specs/001-real-time-suppression/`, the work remains inside `suppressor/` and direct feature
  artifacts, and the plan defers unrelated cleanup until the server-runnable daemon MVP is proven.

**Document impact**:

- Update [suppressor/Makefile](/home/plagamed/Documents/wiki/scripts/suppressor/Makefile) with an
  additive `build-server` target that runs
  `cargo zigbuild --release --target aarch64-unknown-linux-musl` and prints the rsync-ready binary
  path.
- Update [suppressor/README.md](/home/plagamed/Documents/wiki/scripts/suppressor/README.md) for
  live protection semantics, dry-run meaning, emergency catch-up meaning, and the operator entry
  points that are actually authoritative.
- Update
  [suppressor/docs/operations.md](/home/plagamed/Documents/wiki/scripts/suppressor/docs/operations.md)
  for the new primary status vocabulary, one-command `server-start` background launch path,
  last-successful-hide recovery anchor, rolling last-24h verification, randomized nightly full
  recheck, config-review evidence, and compatibility or migration approval workflow.
- Update
  [suppressor/docs/runtime-boundaries.md](/home/plagamed/Documents/wiki/scripts/suppressor/docs/runtime-boundaries.md)
  for the daemon-owned runtime surface, command-report isolation, status compatibility loading, and
  any additive scheduler or state fields.
- Update
  [suppressor/docs/implementation.md](/home/plagamed/Documents/wiki/scripts/suppressor/docs/implementation.md)
  with the internal service boundaries, recovery-anchor rules, scheduler semantics, and TUI
  information architecture decisions.
- Update
  [suppressor/docs/testing-strategy.md](/home/plagamed/Documents/wiki/scripts/suppressor/docs/testing-strategy.md)
  with scheduler, compatibility, last-24h preset, revision-link, and low-spec verification cases.
- No change is currently expected for `.specify/doc-registry.json`; constitution v1.8.0 and
  `specs/000-repo-governance/` already record the human-reviewed config-stability rule that this
  plan applies to the active suppressor MVP.
- If the compatibility or migration-warning pattern produces reusable repo-wide guidance beyond
  `suppressor`, capture that generalized lesson in
  [specs/000-repo-governance/research.md](/home/plagamed/Documents/wiki/scripts/specs/000-repo-governance/research.md)
  during close-out instead of leaving it feature-local only.
- Final close-out must still run `python3 tools/doc_workflow.py all`.
- No `questions.md` is required for this planning update because the human owner has already
  supplied the config-stability rule and it is encoded in constitution v1.8.0. Any future
  config-affecting implementation proposal that lacks explicit human review must be blocked and
  moved to a feature-local question or review item before code or server config changes.

## Project Structure

### Documentation (this feature)

```text
specs/001-real-time-suppression/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   ├── operator-safety.md
│   ├── realtime.md
│   ├── recovery.md
│   ├── release-readiness.md
│   ├── requirements.md
│   └── resource-economy.md
├── contracts/
│   ├── operator-commands.md
│   └── runtime-status.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
suppressor/
├── Cargo.toml
├── Makefile
├── config.toml
├── README.md
├── docs/
│   ├── implementation.md
│   ├── operations.md
│   ├── runtime-boundaries.md
│   └── testing-strategy.md
├── src/
│   ├── app.rs
│   ├── auth.rs
│   ├── cache.rs
│   ├── cache/
│   │   ├── model.rs
│   │   ├── source.rs
│   │   └── store.rs
│   ├── catchup.rs
│   ├── cli.rs
│   ├── commands.rs
│   ├── config.rs
│   ├── daemon.rs
│   ├── effective_config.rs
│   ├── main.rs
│   ├── metrics.rs
│   ├── mw_api.rs
│   ├── recentchange.rs
│   ├── reconcile.rs
│   ├── runtime.rs
│   ├── scheduler.rs
│   ├── signal_control.rs
│   ├── signals.rs
│   ├── state.rs
│   ├── stream.rs
│   ├── titles.rs
│   ├── tui.rs
│   ├── tui_process.rs
│   ├── tui_status.rs
│   ├── tui_view.rs
│   └── worker.rs
├── tests/
│   ├── api_integration.rs
│   └── config_and_state.rs
└── systemd/
    └── suppressor.service
```

**Structure Decision**: Keep the work inside the existing `suppressor/` crate. Do not add a new
service, new top-level package, or separate status daemon. Use the existing modules, but tighten
their ownership boundaries and status/report contracts so the TUI and recovery logic no longer
share ambiguous state.

### Internal Service Boundaries

- `stream.rs`: EventStreams ingestion, reconnect handling, resume cursor handling, stream-freshness
  evidence, and handoff of candidate watched-page edits.
- `cache.rs` and `cache/`: suppression-list fetch, parse, redirect expansion, cache diff, and
  source-triggered watched-title delta identification.
- `catchup.rs`: gap recovery, rolling last-24h verification, accident-window coverage, bounded
  unresolved sampling, and recovery summary aggregation.
- `scheduler.rs` and `reconcile.rs`: randomized daytime rolling-24h verification scheduling,
  randomized nightly full recheck scheduling, and full watched-set reconciliation control.
- `mw_api.rs`: MediaWiki timestamp serialization, revision lookup, rate-limit classification,
  retry-after parsing, revision URL construction, and safe failure snapshots.
- `worker.rs`: RevDel execution, transient retry, terminal blocked-state handling, and last
  successful hide recording.
- `runtime.rs` and `state.rs`: daemon-owned realtime truth, compatibility loading, recovery anchor
  persistence, command-report isolation, bounded resource snapshots, and explicit status-state
  transitions.
- `commands.rs`: one-shot operator actions and bounded command reports that never overwrite daemon
  realtime truth.
- `commands.rs` plus a small launch helper if needed: additive `server-start` orchestration,
  including local setup checks, duplicate/stale PID handling, detached child spawn, log redirection,
  startup wait, and the non-sensitive launch receipt printed to the operator.
- `tui_status.rs`, `tui_view.rs`, `tui.rs`, and `tui_process.rs`: operator-first status assembly,
  action launching, daemon-vs-command log separation, and primary vs secondary TUI rendering.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified.

## Implementation Phases

### Phase -1 - MVP Stabilization Reset

- Treat the current checked-off task list as provisional until the daemon is verified through the
  actual launch path. A checked task is not release evidence by itself.
- Stop broad TUI/layout polish and unrelated docs/workflow work. Only keep UI changes that make
  daemon health, latest hide, backoff, reconciliation, or nightly fallback truth visible.
- Add a `suppressor/Makefile` server build target for
  `cargo zigbuild --release --target aarch64-unknown-linux-musl`, printing
  `target/aarch64-unknown-linux-musl/release/suppressor` for rsync/deploy.
- Add a `server-start` CLI command so the rsynced binary can prepare local runtime paths, start the
  daemon detached from the SSH terminal, print PID/status/log evidence, and return only after the
  daemon-owned runtime surface proves the background process is alive.
- Revalidate the live path first: recentchange detection, watched-page match, queue handoff,
  RevDel execution or dry-run outcome, `last_successful_hide_at`, and status update.
- Revalidate shared throttle/backoff next so catch-up, source refresh, daytime verification,
  nightly full recheck, and one-shot commands cannot starve live hiding or make the daemon look
  healthy while protection is blocked.
- Revalidate automatic reconciliation and nightly fallback with exact scope labels and bounded work:
  rolling last 24 hours during the day, full watched-set recheck at night.
- Run the shortest meaningful test gate first, then the actual server build and launch-path smoke
  check. Full benchmarks and broad docs close-out remain after the daemon MVP is stable.
- Treat any T037/T038 evidence recorded before later Phase 2, US1, or US2 daemon-critical edits as
  a useful local snapshot only. Final T037/T038 checkmarks require rerunning the serial suppressor
  test gate and `make -C suppressor build-server` after those edits are complete.

### Phase 0 - Compatibility Baseline And Actual Runtime Grounding

- Confirm the authoritative runtime in current deployment is still the TUI-managed child daemon for
  the user’s host, then add the detached `server-start` path as an explicit server deployment route
  while preserving support for the optional `systemd` path without assuming it is the default
  verification route.
- Record the currently shipped config, runtime-status, command-report, and PID-file shapes as the
  compatibility baseline for additive changes and migration fixtures.
- Record the config baseline as a human-reviewed contract before any further config-affecting code
  or docs work: tracked config file, schema sections, defaults, environment variable names, loading
  aliases, deployment-required sections, and any target-host divergence. The target-host
  `missing field realtime` failure is evidence of divergence and blocks T039 until a reviewed
  compatibility or migration path is chosen.
- Refuse ad-hoc server config edits as a workaround. A server config migration is allowed only when
  the evidence names the motivation, reviewer, exact changed fields, backup/rollback path, and
  post-change `server-start` verification.
- Confirm how runtime truth is cross-checked against the live process and launched binary so a
  stale PID file or stale `runtime_status.json` cannot masquerade as current protection evidence.
- Confirm which existing state fields already persist `last_successful_hide_at`,
  `latest_recovery_summary`, compatibility notices, and command-report isolation so the design adds
  fields rather than replacing the surface wholesale.
- Identify the smallest required set of TUI rows, command outputs, and machine-readable fields that
  answer operator questions before showing secondary diagnostics.

### Phase 1 - Recovery Anchor And Scheduler Semantics

- Replace bounded recent-window recovery as the primary automatic recovery anchor with
  `last_successful_hide_at`, while preserving a documented older trusted fallback if that timestamp
  is absent or unreadable.
- Keep repeated reconnect noise from triggering full startup recovery. Full watched-set recovery
  remains reserved for true daemon bootstrap, verified gap recovery, explicit operator action, or
  randomized nightly full recheck.
- Reinterpret or alias the existing daytime scheduler so it performs randomized rolling last-24h
  verification runs rather than current-day-from-midnight checks.
- Extend nightly scheduling so a full watched-set recheck happens at a randomized night hour without
  invalidating existing configs that currently provide a single start time.
- Make every recovery or verification run record its exact covered window or scope and expose that
  window to the operator surface.
- Define how full watched-set freshness is measured from checkpoints or additive runtime fields:
  at minimum oldest full-check age, oldest sample title, stale-page count against the nightly
  target, and the latest failed daytime or nightly verification result.

### Phase 2 - Operator-First Runtime Contract And TUI Layout

- Preserve the daemon-owned `runtime_status.json` surface, but extend it additively with the status
  objects needed for operator-first rendering: uptime, current task, recovery window, last
  successful hide, latest actionable issue, recent offline/stalled interval, revision URLs, and
  reconciliation freshness evidence.
- Remove raw resume cursors, internal counters, and bookkeeping rows from the primary TUI status
  view. They may remain available as secondary diagnostics or machine-readable fields.
- Distinguish stream freshness from live hide effectiveness so fresh recentchange input cannot mask
  a failed or unresolved live suppression path.
- Keep failed scheduled verification and stale full watched-set coverage visible as actionable
  degraded-trust evidence until a later successful verification or full recheck clears them; a
  stream reopen alone must not clear that state.
- Report lag as a wall-clock duration that keeps sub-second precision when the value is below one
  second, and use bounded API freshness probing only when the stream is silent enough that freshness
  is ambiguous.
- Ensure the TUI latest log view follows rendered rows correctly and labels one-shot command output
  separately from daemon output.

### Phase 3 - Command Surface Cleanup And Useful Presets

- Keep command reports separate from daemon realtime truth, with bounded `command_report.json`
  output and stdout summaries.
- Make `Emergency catch-up` useful by clearly documenting and implementing its default scope: use
  the active recovery anchor window when available, otherwise a bounded recent window.
- Add a clearly labeled operator-visible `Last 24 hours` coverage preset that shows the exact
  rolling window and does not require the operator to supply timestamps.
- Rename or relabel ambiguous TUI actions in plain language while preserving CLI compatibility where
  practical: for example `Reload watched pages` instead of an unexplained reload signal, and
  `Refresh status` only as a local reread of persisted files rather than a recovery action.
- Make revision identifiers in operator surfaces render as safe clickable URLs or equivalent direct
  browser-openable targets.

### Phase 4 - Verification, Docs, And Approval Evidence

- Add regression tests for last-successful-hide recovery anchoring, rolling last-24h scheduling,
  randomized nightly full recheck selection, compatibility loading of older state shapes, command
  isolation, plain-language TUI status rows, revision-link rendering, lag precision, and failed
  scheduled-verification truth.
- Add controlled tests for repeated throttle behavior, recovery convergence, source-triggered catch
  up under backoff, the `Last 24 hours` preset, and checkpoint-freshness summaries with stale-page
  coverage age.
- Run suppressor tests, docs workflow, and controlled benchmark checks. Restart the real deployment
  path in use and verify the TUI plus runtime surfaces reflect the new fields and layout.
- Build the server artifact with the Makefile wrapper for
  `cargo zigbuild --release --target aarch64-unknown-linux-musl`, verify the binary exists at
  `target/aarch64-unknown-linux-musl/release/suppressor`, and record the rsync/deploy path in the
  operator quickstart.
- After rsync deployment, verify `./suppressor --config ./config.toml server-start` prepares the
  runtime paths, starts the daemon detached from the SSH terminal, prints PID/status/log evidence,
  survives terminal logout, and fails safely for missing config/secrets, stale PID, duplicate live
  daemon, unwritable state/log paths, or runtime-status timeout.
- Before T040 server launch evidence is accepted, verify the config review gate: `server-start` and
  `print-effective-config` must either load the reviewed deployment config without secrets or fail
  with an operator-visible config/migration-needed diagnostic. No launch evidence counts if the
  config was edited in the background, contains unreviewed required sections, or lacks documented
  rollback/fallback to the last trusted config.
- Before release trust is claimed for any incompatible surface change, produce explicit evidence of:
  the compatibility verdict, required human approval checkpoint, required operator migration steps,
  and the fallback or rollback path to the last trusted workflow.
