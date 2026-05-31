---
docmeta:
  status: draft
  review: feature-local
  purpose: Implementation plan for restoring urgent real-time suppressor hiding.
  source:
  - speckit-plan on 2026-04-29
  - speckit-plan stabilization update on 2026-05-05
  - speckit-plan config-stability update on 2026-05-06
  - speckit-plan human-review queue update on 2026-05-06
  - user approval on 2026-05-07
  - operator-provided live-hide incident evidence with sensitive identifiers redacted
  - speckit-plan server-running launch-path mismatch update on 2026-05-07
  - speckit-plan live-priority parallel execution update on 2026-05-09
  - speckit-plan live-latency clarification update on 2026-05-09
  - speckit-plan KISS/catch-up simplification update on 2026-05-10
  - speckit-plan rsynced crash evidence update on 2026-05-13
  - speckit-plan rsynced old-command deployment evidence update on 2026-05-14
---

# Implementation Plan: Real-Time Suppression Recovery


## Summary

Restore `suppressor` as a trustworthy real-time protection daemon for be.wikipedia.org sensitive
pages. The remaining work is not only faster hiding; it is also truthful recovery and truthful
operator evidence. Recovery must anchor on the last recorded successful hide, and the operator
surface must clearly show whether protection is working now, what recovery or verification is
active, what the last meaningful hide was, and what problem requires action. During the current
emergency live-only production phase, automatic daytime and nightly verification are not part of
the target-host trust gate: production runs with `daytime_verification.enabled=false` and
`nightly_sweep.enabled=false` until live-hide soak passes. Manual `Last 24 hours`, full recheck,
and emergency catch-up commands remain available as bounded operator tools. The implementation
should preserve the current single local daemon plus TUI deployment, keep status and command
surfaces backward-compatible where practical, and emit explicit migration or fallback guidance when
compatibility cannot be preserved.

Constitution v1.10.0 puts this feature under an active human-safety freeze, makes config surfaces
human-reviewed operator contracts, forbids tracked real sensitive-edit incident identifiers, and
adds a mandatory KISS/intent-first gate. The concrete human intent is now: make the existing
suppressor fast, simple, and trustworthy for recent live edits, without hiding slow behavior behind
more status text or broad architecture. The current plan is therefore a simplification reset: defer
unrelated work, broad refactors, cosmetic TUI polish, new services, and nonessential optimization
until the minimal server-runnable daemon MVP is proven. The critical path is automatic live hiding,
fast candidate-first recovery, bounded reconciliation/nightly fallback, shared throttle/backoff
safety, truthful compact non-healthy status, actual-launch-path verification, a repeatable aarch64
Linux musl release build ready for `rsync` to the server, and a one-command detached server-start
path from the deployed binary. Config churn is not part of this MVP path: any config file, schema,
default, environment-variable, loading-semantic, or deployment-required-section change must be
motivated, explicitly human-reviewed, compatibility-tested, and rollback-safe before it can support
production trust. Human review needed for the active target-host config gate must be visible in
feature-local `questions.md` and `review-queue.md`; chat-only approval or scattered release
evidence is not sufficient to unblock T040.

The operator-provided screenshot is fresh failed T041 evidence: a watched sensitive page still
showed an available public hide action after a live edit by an operator-controlled account. Concrete
page, account, revision, diff URL, comment, screenshot, and log identifiers must stay out of tracked
repository docs, tests, contracts, examples, fixtures, and code comments. This resets the immediate
critical path. Do not spend the next implementation pass on broad evidence, resource
sampling, docs tooling, TUI polish, or new config policy. First preserve protection with manual hide
or emergency catch-up if an exposed revision is known, then diagnose and fix the live path at the
smallest boundary: event observed, watched-title match, processed-revision skip, queue handoff,
RevDel/auth result, or stale/wrong daemon binary. T040 launch evidence remains useful only as the
minimal server status needed to debug the live path; it must not delay the T041 live-hide hotfix
when public watched edits are visibly unhidden.

After the server was made to run again, the latest operator screenshot is useful but negative T040
evidence: a live process exists, yet the primary status remains non-healthy because launch-path,
PID-file, runtime-status, detached-log, and live-process evidence do not agree. That state may still
be preserving some protection, so do not stop it only to make evidence cleaner. It does not unblock
deployment trust. The next plan step is to either tie the current process to a valid `server-start`
receipt and fresh daemon-owned `runtime_status.json`, perform a safe fresh `server-start` after
protecting any exposed edit and avoiding duplicate-daemon risk, or fall back to the last trusted
launch workflow. T052 live or dry-run smoke and T042 resource sampling remain blocked until this
launch-path mismatch is resolved or explicitly accepted as a human go/no-go exception.

The 2026-05-13 rsynced server bundle changes the server diagnosis. The target-host config now has
the reviewed `[realtime]` section, and reconstructed `server-start` PID/status/log evidence points
to one running daemon, so the earlier missing-config failure is not the active crash signature and
T040 can be treated as mostly aligned once logout-survival evidence is confirmed. The active server
state is still not release-ready: runtime status is `unhealthy`, the deployed binary lacks the
current live/background lane and latency fields, and the logs show two remaining MVP crash modes.
A live RevDel permission failure was classified and then followed by a deliberate process exit; an
earlier realtime stream task stopped after failing to persist the stream cursor state. Those two
crash signatures are now fixed locally and covered by targeted tests, but the 2026-05-14 rsynced
bundle collected after updating the binary and relaunching with the old command still lacks the
current lane, latency, and candidate-first recovery evidence. Treat the active blocker as
target-host deployment identity: before T052, the daemon started on the server must be tied to the
exact rebuilt artifact and must write the current status shape from that same run.

The 2026-05-09 latency refinement makes live work isolation concrete: reconciliation, catch-up,
scheduled verification, and one-shot command work must no longer share a single FIFO execution path
that can sit in front of newly observed live edits. Keep one daemon process, but split the internal
execution model into at least two bounded lanes: a live-hide lane for recentchange edits and a
background lane for reconciliation, recovery, verification, and reports. Live observed edits must
enqueue or visibly degrade without waiting behind background batches, use short action deadlines,
persist each state transition atomically, and report observed-to-queue, queue-to-submit,
submit-to-complete, and observed-to-hidden timings in tests and release evidence. The 2026-05-09
clarification sets no fixed internal millisecond handoff SLA for the MVP: live handling should be as
fast as practical, and reconciliation or nightly work may slow it only if recent edits still react
instead of waiting for background drain. Background lanes may use bounded concurrency, but their
transactions must not hold live queue, status, or processed-revision locks across network calls.

The 2026-05-10 local run exposed the next concrete overcomplication: startup catch-up used the
last successful hide as a multi-day anchor, then scanned the whole watched set serially even though
only a small number of edits in the window needed action and all were already covered. That is not
acceptable for a 1.4k-title watch set. The next implementation plan must make recovery
candidate-first: query recent changes or another narrow candidate source for the selected window,
filter candidates by the watched-title cache, then verify or hide only those revisions. A full
watched-set pass remains valid only for explicit nightly/full recheck, a verified fallback when
candidate discovery is unavailable, or an operator-requested full check. Startup may report
background full verification as slower work, but it must not keep recent live edits waiting and it
must not flood the primary TUI with internal scan details.

2026-05-14 local hotfix implementation note: the active source tree now uses MediaWiki
`recentchanges` polling as the authoritative live detector for the MVP daemon. Retained
EventStreams code is no longer the healthy-state truth path in the running daemon and may remain
only as dormant observer/fallback implementation detail until target-host smoke proves the rebuilt
binary.

## Active Emergency Scope And Guardrails

This active feature is intentionally narrower than the historical implementation record below.
Treat the current `001` scope as:

- fast automatic hiding of new watched sensitive-page edits
- bounded catch-up from the last trusted hide anchor after downtime or failure
- randomized daytime last-24-hours rechecks and nightly full rechecks
- truthful degraded or blocked runtime status
- exact deployment proof for the running target-host binary

The following are explicitly out of scope until target-host smoke passes on the rebuilt daemon:

- TUI polish beyond truthful protection state
- broad reporting or diagnostic-surface growth
- repo-wide Spec Kit template or docs-workflow repair
- inactive-feature work such as `002-fix-git-commit`
- speculative architecture changes not needed for live protection

Authoritative truth order for this feature:

1. `spec.md`
2. `plan.md`
3. `tasks.md`
4. operator docs in `quickstart.md` and `suppressor/docs/operations.md`

`review-queue.md` and `questions.md` are operator decision logs, not a second plan. Historical
phase detail remains below as evidence for why particular tasks exist, but it must not be used to
re-expand the current scope without explicit user approval.

## Current Trust Gate

The current emergency gate is small and hard:

1. prove the exact binary that is running on the target host
2. prove the same PID owns fresh daemon status after logout survival
3. prove the daemon is current or within bounded lag under active edits
4. prove a new watched edit hides quickly
5. prove blocked, throttled, auth-session, and persistence failures remain visible without daemon
   exit

A stale replayed hide while the daemon remains hours behind is a failed smoke result, not partial
success. The remaining active trust path is T040, T041, and T052. T042 resource sampling is
follow-up evidence only after those gates pass on the current binary.

## Technical Context

**Language/Version**: Rust edition 2024 in the existing `suppressor` crate
**Primary Dependencies**: `tokio`, `reqwest`, `reqwest-eventsource`, `serde`, `serde_json`,
`chrono`, `rand`, `tracing`, `metrics`, `clap`, `ratatui`, `crossterm`, `wiremock`; do not add a
new queueing service or database for this refinement unless later benchmark evidence proves the
single-process Tokio design cannot meet SC-001
**Storage**: Local JSON/text state under `suppressor/state/`, including
`runtime_status.json`, `command_report.json`, `processed_revids.json`,
`nightly_sweep_progress.json`, `last_event_id.txt`, `daemon.pid`, server-start log evidence, and
the suppression-list cache
**Testing**: MVP gate uses `rtk cargo test --manifest-path suppressor/Cargo.toml --
--test-threads=1`, targeted tests for shared throttle/backoff, runtime-status truth, daemon-vs-
command isolation, scheduler/reconciliation visibility, and a dry-run or controlled live
launch-path smoke check. The latency refinement adds deterministic lane-isolation tests: hold the
background reconciliation lane on synthetic work, inject a synthetic watched live edit, and assert
the live lane records observed-to-queue, queue-to-submit, and observed-to-hidden timings without
waiting for the background lane to drain. Tests must also cover queue saturation, action deadline,
retry deferral, atomic processed/status transaction ordering, and p95/p99 reporting from a bounded
sample set. Full `rtk cargo test --manifest-path suppressor/Cargo.toml`, controlled benchmark
checks against the configured bot test page, and the repo docs gate remain release evidence but
must not displace the live daemon stabilization path. Test and server-build evidence is fresh only
for the source tree that produced it: any later daemon-critical edit to `suppressor/src/`,
`suppressor/tests/`, `suppressor/Cargo.toml`, `suppressor/Cargo.lock`, `suppressor/Makefile`, or
build/deployment code invalidates the prior T037/T038 evidence. T037 and T038 must be rerun after
Phase 2, US1, and US2 have changed daemon-critical paths before their checkmarks can count as final
MVP gate evidence. The next implementation test slice must include a regression for a synthetic
watched sensitive page edited by a synthetic operator-account actor, proving that operator-account
eligible edits are not filtered, not silently marked processed, and either queue a live RevDel
action or record an explicit failed live-hide outcome. It must also include regressions for a
synthetic RevDel permission/auth failure that records blocked protection without exiting the
process, and for a stream cursor/state write failure that leaves an actionable degraded status and
restarts or retries stream monitoring instead of permanently losing the realtime task.
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
5 seconds under normal availability; no separate fixed internal live-worker handoff SLA is required
for this MVP, but newly observed live edits must react as fast as practical, must not wait for
reconciliation, catch-up, or nightly work to drain, and must record p50/p95/p99 timings for
observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden; stale or ineffective
protection surfaced within 10 seconds; recovery from missed edits since the last successful hide
completed or reported unresolved within 2 minutes for gaps up to 30 minutes; at least one
randomized daytime rolling-24h verification and one randomized nightly full recheck recorded per
uninterrupted 24-hour daemon period; failed scheduled verification or stale full watched-set
coverage surfaced to the operator within 10 seconds of status inspection
**Resource Goals**: MVP defaults must keep live hiding isolated from slower work. Initial release
budgets: live hide queue bounded to a configured cap with visible degradation before saturation;
background reconciliation/recovery queue bounded separately; catch-up/reconciliation API
concurrency no higher than 2 by default; live hide execution not blocked behind scheduled
reconciliation; live status and processed-revision transactions short enough that no lock is held
across MediaWiki network calls; unresolved samples capped to a small operator list; warning
summaries capped and coalesced by root cause; normal status/report state kept compact enough for
local JSON reads; normal logs rate-limited so repeated API failures do not create log storms; no
busy loops; idle daemon plus TUI must be measured on the deployment host; any budget relaxation must
be documented with evidence and must not delay live hiding or hide non-healthy status. The MVP
resource sample must record CPU percentage, RSS memory, live and recovery/reconciliation queue
depths versus caps, API concurrency, `runtime_status.json`, `command_report.json`, and
`processed_revids.json` size, detached log growth rate, coalesced-warning counts, and recent
latency p95/p99 for observed-to-queue and observed-to-hidden for at least a 10-minute idle window
and one active live/recovery/backoff window. Release is blocked unless queue pressure becomes
degraded before saturation, API concurrency stays at or below the default cap of 2, status/report
files remain below 1 MiB each, repeated-root-cause log growth stays below 10 MiB/hour or has a
documented mitigation, and active samples return to a stable idle baseline without monotonic growth.
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
target prints the rsync-ready artifact path. A target-host runtime status file that lacks the
additive live/background lane and latency fields is compatible enough to parse, but it is evidence
that the deployed binary is older than the current MVP design; it cannot satisfy lane-readiness,
T052 smoke readiness, or release trust until the rebuilt binary is rsynced, launched, and tied to a
safe artifact identity tuple for that run.
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
evidence are trustworthy; classified RevDel auth or permission failures must not terminate the
daemon process; retained observer cursor and local state persistence failures must surface a
non-healthy actionable issue and retry or reconnect without silently losing live monitoring
**Sensitive Evidence Handling**: Use synthetic watched titles, synthetic actor names, synthetic
revision IDs, synthetic URLs, redacted placeholders, aggregate counts, and outcome classes in
tracked docs, tests, contracts, examples, fixtures, and code comments. Real page titles, actor
names, revision IDs, diff URLs, comments, screenshots, and log excerpts from sensitive-edit
incidents are allowed only in operator-local diagnostics needed to protect exposed edits and must
not be committed.
**Architecture Constraints**: Preserve one deployable daemon/TUI package, but keep internals
microservice-like: stream ingestion, cache refresh, catch-up, verification scheduling, MediaWiki
transport, worker execution, runtime state, command reports, and TUI rendering communicate through
explicit structs, enums, and bounded channels. The long-running daemon remains the only writer of
daemon realtime truth. One-shot commands may emit bounded report surfaces but must not overwrite the
daemon-owned runtime status surface. The internal execution model must have explicit live and
background lanes rather than one shared FIFO for all RevDel work; background lane concurrency must
be semaphore-bounded and live lane actions must be admitted or rejected with a visible degraded
state before they can wait behind reconciliation batches.
**Intent Restatement**: The operator wants a small, clean, fast suppressor that reacts to recent
watched edits immediately, keeps slower reconciliation in the background, and shows only the status
needed to trust protection now. Out of scope: a new service, a generic moderation framework, a
database migration, broad UI polish, or another layer of status text that does not reduce delay.
**Minimalism Constraints**: Prefer the smallest direct code path that removes delay. Reuse existing
MediaWiki API transport, runtime status, and JSON state; add named constants and narrow helper
types only when they remove duplication or clarify ownership. Avoid new dependencies, new always-on
background loops, new persistent artifacts, generic frameworks, and large refactors. Existing large
modules may be split only around real responsibilities needed for this fix: candidate discovery,
lane dispatch, state transactions, and compact status rendering.
**Scale/Scope**: Approximately 1.4k watched titles, one live recentchange stream, one local
operator, one daemon process, bursty recentchange input, and no new public network service
**Review/Approval Workflow**: Active feature-scoped human answers and review actions live in
`specs/001-real-time-suppression/questions.md` and
`specs/001-real-time-suppression/review-queue.md`. Q001 was answered on 2026-05-07: approve path 1,
target-host config migration to the reviewed tracked baseline. That approval remains valid and does
not need to be reopened for code-only crash-resilience or live-hide fixes. The rsynced
2026-05-13 server evidence mostly resolves the earlier T040 launch-path mismatch: config has
`[realtime]`, the daemon was started through `server-start`, and PID/status/log evidence points to
one running process. T040 still needs logout-survival confirmation and concise non-secret evidence
recording. T052 remains blocked because the running daemon is unhealthy and the latest rsynced
bundle still does not prove the rebuilt crash-resilient binary is the one writing runtime status:
the target-host status lacks current lane/latency fields and still shows legacy recovery shape. Full
resource evidence can follow after the rebuilt lane-aware binary is deployed, its identity is
recorded safely, and live hiding is proven.

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
  daemon truth plus compatibility diagnostics. Active human approval now has a feature-local queue
  instead of being hidden only in chat history or scattered release evidence.
- Stable Config, Compatibility, Non-Destructive Change, And Explicit Approval: PASS with required
  implementation follow-through. The design is compatibility-first, additive where practical, and
  names migration, rollback or fallback, and the human approval checkpoint for incompatible
  operator surfaces, launch-path assumptions, or config-affecting changes. No config change may be
  treated as production-valid without recorded motivation, explicit human review, compatibility or
  migration evidence, target-server verification, and rollback/fallback notes.
- Spec Kit First For Non-Trivial Work: PASS. This plan follows the updated `spec.md`; `tasks.md`
  must be regenerated from this plan before implementation continues.
- Resource Economy, Robustness, And Durable Lessons: PASS. The plan includes bounded state,
  explicit live/background concurrency lanes, short local transactions, logging, and low-spec
  verification without relaxing latency or recovery goals.
- Active Human-Safety Freeze For Suppressor MVP: PASS. The active pointer is
  `specs/001-real-time-suppression/`, the work remains inside `suppressor/` and direct feature
  artifacts, and the plan defers unrelated cleanup until the server-runnable daemon MVP is proven.
  The active live-hide incident strengthens the freeze: implementation must move to the smallest
  live-hide hotfix path before nonessential evidence or polish.
- Public-Repo Privacy For Sensitive Edit Evidence: PASS. The plan treats the screenshot as
  redacted operator evidence and forbids real page, actor, revision, diff, comment, screenshot, or
  log identifiers in tracked docs, tests, contracts, examples, fixtures, and code comments.
- KISS, Intent First, And Small Code: PASS with required follow-through. The plan restates the
  operator's intent, rejects new services/databases/frameworks, and directs implementation to the
  smallest measurable fixes: candidate-first recovery, live/background lane isolation, short state
  transactions, and compact primary TUI rendering. Any broad refactor must be justified in
  Complexity Tracking before implementation continues.

**Document impact**:

- Update [suppressor/Makefile](../../suppressor/Makefile) with an
  additive `build-server` target that runs
  `cargo zigbuild --release --target aarch64-unknown-linux-musl` and prints the rsync-ready binary
  path.
- Update [suppressor/README.md](../../suppressor/README.md) for
  live protection semantics, dry-run meaning, emergency catch-up meaning, and the operator entry
  points that are actually authoritative.
- Update
  [suppressor/docs/operations.md](../../suppressor/docs/operations.md)
  for the new primary status vocabulary, one-command `server-start` background launch path,
  last-successful-hide recovery anchor, rolling last-24h verification, randomized nightly full
  recheck, config-review evidence, and compatibility or migration approval workflow.
- Update
  [suppressor/docs/runtime-boundaries.md](../../suppressor/docs/runtime-boundaries.md)
  for the daemon-owned runtime surface, command-report isolation, status compatibility loading, and
  any additive scheduler or state fields.
- Update
  [suppressor/docs/implementation.md](../../suppressor/docs/implementation.md)
  with the internal service boundaries, live/background execution lanes, short suppression
  transactions, recovery-anchor rules, scheduler semantics, and TUI information architecture
  decisions.
- Update
  [suppressor/docs/testing-strategy.md](../../suppressor/docs/testing-strategy.md)
  with scheduler, compatibility, last-24h preset, revision-link, live-priority timing, and low-spec
  verification cases.
- Add `questions.md` and `review-queue.md` in this feature so the human owner has one convenient
  place to see and answer the approval question that blocks T040.
- No change is currently expected for `.specify/doc-registry.json` for feature-local queue files;
  the constitution and `specs/000-repo-governance/` already record the human-reviewed
  config-stability rule that this plan applies to the active suppressor MVP.
- Constitution v1.10.0 adds public-repo privacy plus KISS/intent-first rules. This feature's
  tracked docs, tests, contracts, examples, fixtures, and code comments must keep using synthetic or
  redacted incident identifiers, and further implementation must keep the smallest working design
  ahead of secondary polish.
- If the compatibility or migration-warning pattern produces reusable repo-wide guidance beyond
  `suppressor`, capture that generalized lesson in
  [specs/000-repo-governance/research.md](../000-repo-governance/research.md)
  during close-out instead of leaving it feature-local only.
- Final close-out must still run `python3 tools/doc_workflow.py all`.
- `questions.md` and `review-queue.md` record Q001 as answered: path 1 target-host config migration
  is approved. Do not revisit config policy before T040 unless the server evidence fails.

## Project Structure

### Documentation (this feature)

```text
specs/001-real-time-suppression/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── questions.md
├── review-queue.md
├── checklists/
│   ├── config-stability.md
│   ├── deployment-evidence.md
│   ├── mvp-evidence.md
│   ├── mvp-stability.md
│   ├── operator-safety.md
│   ├── realtime.md
│   ├── recovery.md
│   ├── runtime-truth.md
│   ├── server-start.md
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

- `stream.rs`: recentchanges polling, overlap dedupe, retained observer compatibility, freshness
  evidence, and handoff of candidate watched-page edits.
- `cache.rs` and `cache/`: suppression-list fetch, parse, redirect expansion, cache diff, and
  source-triggered watched-title delta identification.
- `catchup.rs`: candidate-first gap recovery, rolling last-24h verification, accident-window
  coverage, bounded unresolved sampling, and recovery summary aggregation. Catch-up first discovers
  candidate revisions for the selected window, filters them against the watched-title cache, and
  dispatches only matching work through the background lane. It must not perform a serial
  full-watched-set scan on ordinary startup when candidate discovery can prove the relevant set, and
  it must not hold live locks while waiting for page scans or worker completion.
- `scheduler.rs` and `reconcile.rs`: randomized daytime rolling-24h verification scheduling,
  randomized nightly full recheck scheduling, and full watched-set reconciliation control.
  Reconciliation runs in a bounded background lane with explicit queue depth, in-flight count, and
  backoff status that cannot block live recentchange submission.
- `mw_api.rs`: MediaWiki timestamp serialization, revision lookup, rate-limit classification,
  retry-after parsing, revision URL construction, and safe failure snapshots.
- `worker.rs`: RevDel execution, transient retry, terminal blocked-state handling, and last
  successful hide recording. Worker ownership splits into a live worker or live-priority executor
  and one or more bounded background workers; live actions use short deadlines and deferred retry
  records so one slow API request cannot hold newer live edits.
- `runtime.rs` and `state.rs`: daemon-owned realtime truth, compatibility loading, recovery anchor
  persistence, command-report isolation, bounded resource snapshots, lane-depth snapshots, latency
  percentiles, and explicit status-state transitions. Runtime updates for queue, submit, complete,
  and processed-revision insertion must be treated as short atomic transactions: update in-memory
  state, persist the relevant JSON surface, then release locks before network or long-running work.
- `commands.rs`: one-shot operator actions and bounded command reports that never overwrite daemon
  realtime truth.
- `commands.rs` plus a small launch helper if needed: additive `server-start` orchestration,
  including local setup checks, duplicate/stale PID handling, detached child spawn, log redirection,
  startup wait, and the non-sensitive launch receipt printed to the operator.
- `tui_status.rs`, `tui_view.rs`, `tui.rs`, and `tui_process.rs`: operator-first status assembly,
  action launching, daemon-vs-command log separation, and primary vs secondary TUI rendering.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No new constitution violations are accepted. Existing oversized runtime/status/catch-up modules are
recognized implementation debt for this feature, but the approved remediation is narrow: split or
extract only where it directly supports candidate discovery, live/background lane dispatch, short
state transactions, or compact primary status rendering.

## Implementation Phases

### Phase -1 - KISS Stabilization Reset

- Treat the operator-provided screenshot as an active live-hide incident. If an exposed revision ID is
  available, the operator should hide it manually or run emergency catch-up before waiting for a code
  fix. Evidence collection must not leave public watched edits exposed longer and must not copy real
  incident identifiers into tracked repository files.
- Treat the current checked-off task list as provisional until the daemon is verified through the
  actual launch path. A checked task is not release evidence by itself.
- Stop broad TUI/layout polish and unrelated docs/workflow work. Only keep UI changes that make
  daemon health, latest hide, active background work, backoff, reconciliation, or nightly fallback
  truth visible in a smaller primary view.
- Treat the 2026-05-10 local catch-up delay as a design bug, not an operator configuration problem:
  a multi-day startup anchor must not automatically become a serial full-watched-set scan when a
  narrow candidate query can identify the relevant edits.
- Add a `suppressor/Makefile` server build target for
  `cargo zigbuild --release --target aarch64-unknown-linux-musl`, printing
  `target/aarch64-unknown-linux-musl/release/suppressor` for rsync/deploy.
- Add a `server-start` CLI command so the rsynced binary can prepare local runtime paths, start the
  daemon detached from the SSH terminal, print PID/status/log evidence, and return only after the
  daemon-owned runtime surface proves the background process is alive.
- Revalidate and fix the live path first: recentchange detection, watched-page match, processed-ring
  skip, queue handoff, RevDel execution or dry-run outcome, `last_successful_hide_at`, and status
  update. The failing page is known to be watched in the cached source list, so a "not watched" result
  is a cache/staleness bug unless the server cache differs from the reviewed baseline.
- Revalidate shared throttle/backoff next so catch-up, source refresh, daytime verification,
  nightly full recheck, and one-shot commands cannot starve live hiding or make the daemon look
  healthy while protection is blocked.
- Revalidate automatic reconciliation and nightly fallback with exact scope labels and bounded work:
  rolling last 24 hours during the day, full watched-set recheck at night.
- Revalidate startup catch-up with aggregate timing evidence: recent candidate discovery must
  complete quickly for ordinary windows, live edits must stay responsive while full verification
  continues in the background, and any fallback full scan must state why candidate discovery was not
  sufficient.
- Fix the rsynced crash signatures before target-host smoke: classified RevDel permission/auth
  failures must block or degrade protection without exiting, and stream cursor/state persistence
  failures must not permanently stop the realtime stream task.
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
  `missing field realtime` failure is evidence of divergence. T039 records that block; Q001 now
  approves path 1. The 2026-05-13 rsynced server bundle shows the target config has the reviewed
  `[realtime]` section and that the live daemon is tied to `server-start` PID/status/log evidence.
  Treat this as mostly aligned T040 launch evidence, pending logout-survival confirmation and concise
  non-secret recording. Do not treat it as T052 readiness because the status is unhealthy and the
  deployed binary lacks current lane/latency fields.
- Refuse ad-hoc server config edits as a workaround. A server config migration is allowed only when
  the evidence names the motivation, reviewer, exact changed fields, backup/rollback path, and
  post-change `server-start` verification.
- Treat `review-queue.md` as the operator-facing approval index for this gate. If docs tooling does
  not surface feature-local `approval_needed` rows yet, encode the required approval as
  `answer_needed` so `python3 tools/doc_workflow.py status` still shows the pending human action.
- Confirm how runtime truth is cross-checked against the live process and launched binary so a
  stale PID file or stale `runtime_status.json` cannot masquerade as current protection evidence.
- Before T052, record a safe artifact identity tuple for the binary launched by `server-start`
  (resolved path plus size/mtime or another reviewed non-secret fingerprint) and tie it to the same
  PID, receipt, and `runtime_status.json` writer.
- When a live process exists but launch path, PID file, runtime status, and detached log evidence do
  not agree, status MUST remain non-healthy or migration-required. Such a process may be left
  running while it protects edits, but it cannot satisfy T040, T052, resource sampling, or release
  trust by implication.
- When launch evidence does agree but the runtime status lacks current lane/latency fields or shows
  `unhealthy`, treat launch trust and smoke readiness separately: T040 may be close to complete, but
  T052 and release trust remain blocked until the rebuilt binary runs, the current status shape is
  visible, and the crash-resilience fixes are verified on the target host.
- For the active live-hide incident, capture only non-secret server facts needed to classify the
  boundary: running PID/binary, current `runtime_status.json` freshness, last observed event,
  last matching title/revision, latest outcome, latest actionable issue, queue depth, processed-ring
  presence for the visible revision if known, and whether the page title is in the server cache.
  Local repo state from earlier runs is stale and must not be used as proof about the current server
  daemon.
- Confirm which existing state fields already persist `last_successful_hide_at`,
  `latest_recovery_summary`, compatibility notices, and command-report isolation so the design adds
  fields rather than replacing the surface wholesale.
- Identify the smallest required set of TUI rows, command outputs, and machine-readable fields that
  answer operator questions before showing secondary diagnostics.

### Phase 1 - Recovery Anchor And Scheduler Semantics

- Replace bounded recent-window recovery as the primary automatic recovery anchor with
  `last_successful_hide_at`, while preserving a documented older trusted fallback if that timestamp
  is absent or unreadable.
- Add a candidate-discovery step before per-title revision scans for startup, polling-gap or
  retained-observer-gap recovery, manual
  emergency, and ordinary anchor-based recovery. The preferred path is one bounded recentchanges
  window query, filtered by normalized watched titles, followed by per-revision verification/hide
  only for candidate watched revisions.
- Bound large recovery windows by chunking candidate queries and recording progress. Large windows
  may run slower in the background, but the daemon must open the live lane first and must keep live
  recent edits independent from the recovery scan.
- Fall back to per-title watched-set scanning only when candidate discovery is unavailable,
  incomplete for the selected window, or explicitly requested as full verification. The fallback
  reason must be visible in runtime status and tests.
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
- Make the primary TUI deliberately small. The first screen should fit the compact operator answer:
  protection state, current work, lag, last successful hide, latest issue, and full-check freshness
  only when it affects trust. Internal counters, raw checkpoint counts, and command-report details
  belong in diagnostics or command output.
- Make the log pane honest. It may follow the newest in-memory session output, but it must label
  that scope clearly and must not imply that it is a persistent daemon log tail unless it actually
  reads the detached/current daemon log file.
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

### Phase 2a - Live-Priority Parallel Execution And Timing Evidence

- Replace the current single shared RevDel FIFO with explicit bounded live and background execution
  lanes inside the existing daemon. The live lane owns recentchange-triggered hides; the background
  lane owns catch-up, rolling verification, full recheck, reconciliation, manual coverage, and
  one-shot command work.
- Run the live lane independently from reconciliation. Background jobs may keep a bounded
  concurrency of at most the existing default API cap of 2 unless a reviewed config decision later
  changes that cap; live jobs must not wait for a background page scan or reconciliation batch to
  release the only worker.
- Add a small dispatcher transaction boundary for every suppression action: acquire per-revision
  duplicate protection, record queued status and queue depth, enqueue into the correct lane, release
  locks, submit the MediaWiki API call, then atomically record completion and processed-revision
  state. No transaction may hold runtime-status, processed-ring, or queue locks across network I/O.
- Use short live action deadlines and deferred retry records. If a live RevDel attempt times out,
  rate-limits, or exhausts immediate live attempt capacity, record degraded protection and schedule
  retry or recovery without blocking newer live edits behind the same sleep.
- Add lane-aware status fields: live queue depth/cap, live in-flight count, background queue
  depth/cap, background in-flight count, latest lane saturation event, and recent p50/p95/p99
  timings for observed-to-queue, queue-to-submit, submit-to-complete, and observed-to-hidden.
- Add deterministic timing tests with synthetic clocks or controlled delays: while background
  reconciliation is intentionally blocked, a synthetic watched live edit must still queue, submit,
  and record timing before the background blocker is released. The test evidence must fail if live
  work waits for reconciliation to drain; any test timeout is a hang guard, not a product handoff
  SLA.
- Add burst tests for at least 10 synthetic eligible watched edits, verifying bounded live queue
  behavior, duplicate protection, transaction ordering, final outcomes, and p95/p99 reporting.
- Keep this phase code-only unless a later human-reviewed config decision is needed. The first
  implementation should use constants or existing config values for lane capacities where possible
  and surface any non-compatible config need as a separate Q/RQ item before relying on it.

### Phase 2b - Crash-Resilient Runtime Policy

- Replace process exit on classified RevDel auth or permission failure with a blocked or unhealthy
  protection state. The failed action should record a compact non-sensitive actionable issue and
  stop claiming live-hide success, but the daemon must stay alive to keep status fresh, observe
  later events, and allow recovery or operator action after rights/session repair.
- Treat fatality at the action level, not the process level. A permission-denied live action may
  pause further hide submission or enter shared backoff until operator intervention, but it must not
  kill the only daemon process or erase evidence needed to diagnose the outage.
- Make retained observer cursor and local state persistence robust. Create expected parent
  directories before cursor writes where appropriate; if a write or atomic rename still fails,
  record a `state-persistence` or retained-observer actionable issue, keep runtime status
  non-healthy, and retry or reopen the retained observer with bounded backoff instead of letting
  the spawned compatibility task disappear.
- Add focused tests for the two server-observed signatures: a synthetic RevDel permission failure
  leaves the process alive with blocked status, and a synthetic `last_event_id` persistence failure
  produces degraded status plus a retry/reconnect path.
- Keep raw target-host logs out of tracked files. Use only aggregate counts, timestamps, and
  sanitized outcome classes in tests and release evidence.

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
- Add the emergency live-hide regression before other broad tests: a synthetic recentchange for a
  synthetic watched sensitive title by a synthetic operator-account actor must dispatch as
  `LiveWatchedRevision`, update `last_matching_*`, queue a live RevDel action when the revision is
  not already processed, and record an explicit failed live-hide outcome if RevDel/auth fails.
  Operator-account edits must not be silently skipped.
- Add controlled tests for repeated throttle behavior, recovery convergence, source-triggered catch
  up under backoff, the `Last 24 hours` preset, and checkpoint-freshness summaries with stale-page
  coverage age.
- Add live-priority performance tests from Phase 2a to the release gate: background reconciliation
  blocked while live edit proceeds, live action timeout/deferred retry, queue saturation degraded
  status, 10-edit burst timing, and p95/p99 calculation from recent runtime samples.
- Add crash-resilience tests from Phase 2b to the release gate: no process exit on classified
  RevDel auth or permission failure, blocked or unhealthy status remains fresh, and stream cursor
  persistence failure cannot permanently kill realtime monitoring.
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
- Before checking T040, record the approved path 1 evidence: backup or operator statement that the
  server config was updated, non-secret `server-start` receipt, PID/runtime/log paths, daemon-owned
  status freshness, and terminal logout survival. Keep this evidence concise. If the current
  server-running status reports a launch-path or PID mismatch, record it as a T040 blocker and
  resolve it before T052; do not convert it into launch success by inference. If rsynced evidence
  shows PID/status/log alignment but the runtime status lacks current lane/latency fields, treat
  T040 and T052 separately: finish logout-survival evidence for T040, then rebuild, rsync, relaunch,
  and smoke-test the current binary before T052.
- Before release trust is claimed for any incompatible surface change, produce explicit evidence of:
  the compatibility verdict, required human approval checkpoint, required operator migration steps,
  and the fallback or rollback path to the last trusted workflow.
