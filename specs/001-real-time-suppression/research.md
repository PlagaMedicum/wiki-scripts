---
docmeta:
  status: draft
  review: feature-local
  purpose: Design research decisions for real-time suppression recovery.
  source: speckit-plan on 2026-04-28
---

# Research: Real-Time Suppression Recovery


## Decision: Keep EventStreams as the primary live input, but add bounded API catch-up as a first-class recovery path

**Rationale**: The existing daemon already consumes Wikimedia recentchange EventStreams and can react fastest when that stream is healthy. The incident shows that a running process can still miss or delay live hiding, so the plan needs a bounded catch-up path that does not depend on nightly reconciliation timing. A recent bounded query over watched pages/recent changes can recover startup, reconnect, and stale-stream gaps while preserving the live stream as the fastest path.

**Alternatives considered**:

- Use nightly/current-day reconciliation as the only fallback. Rejected because the configured current-day interval is hours, not seconds, and the user observed a 24-minute exposure.
- Poll every watched page continuously. Rejected as too expensive and slower than the live feed for normal operation.
- Replace EventStreams entirely. Rejected because the stream remains the right low-latency source when healthy.

## Decision: Treat silent stream starvation as the primary suspected fault until controlled tests disprove it

**Rationale**: The current live loop waits on `stream.next().await` and reconnects only when the stream yields an explicit error or closes. That means a silent or wedged connection can leave the process alive with no new matched revisions handled. The current runtime status and TUI show daemon/reconciliation state and `last_event_id`, but not realtime freshness, last match, or last successful hide. That combination matches the observed incident much better than a simple daemon crash.

**Alternatives considered**:

- Assume the incident is only stale cache or watched-title mismatch. Rejected because the operator reported manual refreshes and a running daemon, while the system still did not react within 24 minutes.
- Assume hourly current-day reconciliation is sufficient mitigation. Rejected because the configured interval is far too slow for the required live response.

## Decision: Treat realtime health as a separate persisted status contract

**Rationale**: Current status can show "daemon running" and reconciliation progress while the realtime path is not obviously fresh. A separate realtime status section lets the TUI distinguish running-and-hiding, catching up, stale, unhealthy, and blocked states. Persisting it in `runtime_status.json` keeps the TUI simple and gives the operator a stable local state file for diagnostics.

**Alternatives considered**:

- Infer health from `last_event_id.txt`. Rejected because an event ID alone does not show freshness, matching, queueing, success, or failure.
- Rely on raw logs. Rejected because the operator needs immediate status in the TUI without reading log history.

## Decision: Refactor live-event handling into testable units before optimizing

**Rationale**: The urgent bug is in a safety-sensitive path. Extracting recentchange parsing, wiki filtering, watched-title matching, candidate dispatch, and outcome recording into testable functions makes it possible to prove that a controlled eligible event queues a hide immediately without a live EventSource dependency.

**Alternatives considered**:

- Patch only the visible EventSource loop. Rejected because it would not cover title matching, duplicate suppression, worker enqueue, or status updates.
- Add only manual commands. Rejected because manual action does not satisfy the sub-second automatic requirement.

## Decision: Use bounded freshness thresholds and watchdog recovery

**Rationale**: An open event stream can be ineffective if it stalls, disconnects without a useful error, or resumes with a gap. The daemon should update `last_observed_at` for relevant events, classify stale realtime state after the configured target window, and trigger bounded catch-up before reporting healthy again. This directly addresses the current code path, which otherwise waits indefinitely for the next stream item.

**Alternatives considered**:

- Wait only for EventSource errors. Rejected because a silent stream or stuck loop may not produce an immediate error.
- Mark stale only after minutes. Rejected because the operator requires near-immediate hiding and an unhealthy signal within seconds.

## Decision: Do not treat current-day reconciliation or manual cache reload as realtime recovery

**Rationale**: The current config schedules current-day reconciliation on an hour-scale random interval, and the manual reload signal only refreshes the suppression-list cache. Neither path is designed to satisfy the realtime hide SLO, and relying on them would hide the distinction between live protection and slower safety-net workflows.

**Alternatives considered**:

- Shorten the current-day interval and treat it as the live fallback. Rejected because it still couples recovery to page sweeps rather than direct live-event freshness, and it increases load while remaining slower than stream-driven hiding.
- Ask the operator to use cache reload as the first response. Rejected because it does not directly process newly published sensitive edits.

## Decision: Record revision-level outcomes, not just processed successes

**Rationale**: `processed_revids.json` currently represents successful processing but does not account for skipped, failed, retrying, unresolved, or already-hidden outcomes. The feature requires every observed watched-page edit to have a final or current outcome, especially for accident-window coverage.

**Alternatives considered**:

- Continue using only the processed ring. Rejected because it cannot report unresolved exposure or distinguish why a revision was not hidden.
- Store full revision content or comments. Rejected because logs and state must avoid sensitive payloads.

## Decision: Add operator-visible emergency catch-up and accident-window verification

**Rationale**: The operator needs a fast way to verify recent exposure after an incident and after rights/session disruptions. A command/TUI action that checks a bounded window and reports counts plus unresolved revision identifiers gives operational confidence without making the nightly workflow carry urgent recovery semantics.

**Alternatives considered**:

- Ask operators to manually inspect Special:RecentChanges. Rejected because it is slow and easy to miss watched-page edits.
- Hard-code the current accident window. Rejected because the same mechanism should handle future downtime windows.

## Decision: Use existing latency metrics as the base for benchmark evidence

**Rationale**: The worker already records queue submission latency and immediate hide latency. Extending that with a full event-observed-to-hide timing path and a small controlled manual publish-to-hide run gives both repeatable automated evidence and operator-meaningful wall-clock evidence. This is stronger than relying only on ad hoc observation.

**Alternatives considered**:

- Use only manual stopwatch-style validation. Rejected because it is not enough for regression detection or repeated comparison.
- Add a separate benchmark service. Rejected because the existing daemon metrics and controlled tests are sufficient for this feature's scope.

## Decision: Keep scope inside the existing daemon/TUI deployment

**Rationale**: The constitution marks `suppressor` as narrow, speed-sensitive, and safety-sensitive. The current local daemon plus local TUI can satisfy the feature without new public services or multi-operator coordination.

**Alternatives considered**:

- Add a separate monitoring service. Rejected for this urgent fix because it increases deployment and failure-surface complexity.
- Add a public dashboard. Rejected as outside current scope and unnecessary for one local operator.

## Decision: Use microservice-like internal boundaries, not extra deployed services

**Rationale**: The operator wants a good microservices architecture, but this repo's governance and the suppressor's low-spec deployment model favor one local daemon plus TUI. The right interpretation for this feature is a microservice-style internal architecture: stream ingestion, source refresh, catch-up, MediaWiki API transport, RevDel worker, runtime state, metrics, and TUI rendering stay independently testable and communicate through explicit typed contracts and bounded queues. This gives the maintenance and robustness benefits of service boundaries without adding processes, ports, supervisors, IPC, memory overhead, or deployment failure modes.

**Alternatives considered**:

- Split into multiple OS services. Rejected because it increases runtime overhead and operational complexity for one local operator and conflicts with the current narrow deployment model.
- Keep broad shared mutable state and patch locally. Rejected because it is exactly the kind of coupling that hides live-path failures.
- Introduce a public monitoring service or dashboard. Rejected as outside scope and too expensive for the current safety fix.

## Decision: Treat resource economy as a release constraint

**Rationale**: The daemon should run on the lowest reasonable local hardware without trading away realtime suppression. The design therefore prefers bounded channels, compact rolling state, low default catch-up concurrency, coalesced logs, no busy polling, and API calls scoped to deltas or bounded windows. Release evidence should record idle and active CPU/memory for daemon plus TUI, because a performance-sensitive safety service can fail operationally if it assumes a powerful workstation.

**Alternatives considered**:

- Optimize only after feature correctness. Rejected because catch-up, warning floods, and unbounded state can become correctness problems on low-spec machines.
- Maximize concurrency to finish catch-up fastest. Rejected because it risks API pressure, memory growth, and poor behavior during outage loops.
- Disable recovery work to save resources. Rejected because robustness and realtime safety are non-negotiable; economy must come from bounded design, not missing recovery.

## Decision: Prefer small targeted code over new framework layers

**Rationale**: The fastest robust fix is not a broad refactor. The existing crate already has workable modules for stream, cache, API, catch-up, runtime, worker, and TUI. The remediation should add narrow typed helpers, state fields, and tests where needed, while avoiding new dependencies and generalized frameworks unless they replace a fragile local implementation with a safer or cheaper primitive.

**Alternatives considered**:

- Introduce a full service framework or actor system. Rejected because it adds overhead and migration risk for little benefit in a single local daemon.
- Continue using ad hoc strings across boundaries. Rejected where stable status/error contracts matter.
- Refactor unrelated modules for style. Rejected because this is a safety incident and scope must stay narrow.

## Decision: Preserve lessons as tests, docs, and targeted comments

**Rationale**: The incident exposed specific failure modes: invalid MediaWiki timestamp formatting, refresh-only source hooks, non-actionable `api-error` status, warning floods, and insufficient benchmark evidence. These should not remain only in chat or temporary feature notes. Durable lessons belong in regression tests, operator docs, implementation/runtime docs, and short comments where the local rule is surprising.

**Alternatives considered**:

- Keep lessons only in feature planning artifacts. Rejected because feature-local docs may later be removed after close-out.
- Add broad explanatory comments everywhere. Rejected because comments should be used only where they prevent a repeat bug or clarify a non-obvious protocol rule.
- Rely on commit history only. Rejected because operators and future maintainers need direct docs and tests.

## Decision: Serialize MediaWiki API timestamps without fractional precision

**Rationale**: Runtime analysis on 2026-04-25 showed bounded catch-up sending `rvstart` values with fractional nanoseconds, which MediaWiki rejects with `badtimestamp`. Recovery paths depend on timestamp parameters, so the daemon needs one shared serializer for MediaWiki API timestamps. The chosen shape is UTC second precision with no fractional component, suitable for `rvstart`, coverage windows, and similar API parameters.

**Alternatives considered**:

- Continue using `DateTime::to_rfc3339()`. Rejected because it can include fractional nanoseconds and has already failed against production.
- Format each API call locally. Rejected because one missed call site would reintroduce catch-up failure.
- Accept `badtimestamp` as a normal unresolved outcome. Rejected because it turns every page into a false unresolved exposure and floods the operator surface.

## Decision: Source-list edits trigger immediate bounded catch-up, not only cache refresh

**Rationale**: The current live hook sees edits to `Удзельнік:Wizardist/SuppressionList`, refreshes the cache, and returns. That updates the watched set eventually, but it does not inspect edits that already happened on pages newly added to the list. The fix should treat a successful source-list refresh as a recovery trigger: compute the newly added watched titles and run a bounded catch-up over those titles immediately. The same recovery semantics should apply when `Вікіпедыя:Запыты да схавальнікаў` changes and the configured window may contain newly requested pages.

**Alternatives considered**:

- Wait for the next live edit on each newly added page. Rejected because the exposed revision may already exist and require immediate hiding.
- Wait for current-day reconciliation. Rejected because its cadence is intentionally slower and cannot satisfy the live safety requirement.
- Always run a full catch-up over all watched pages after every source-list edit. Rejected as avoidable load; default should prioritize the delta while allowing a wider operator-triggered catch-up.

## Decision: Persist classified API failure evidence without sensitive payloads

**Rationale**: The TUI currently shows classified failures, but the remaining runtime issue is a flood of `HTTP 429` non-JSON responses during catch-up and now also on the live path. Operators need to distinguish `badtimestamp`, JSON API errors, HTTP status failures, non-JSON responses, decode failures, auth/session blockers, and transient network or throttle errors. The persisted evidence should include compact error class, API code, HTTP status, content type, retryability, `Retry-After` when present, affected action, and a redacted short message, but not full response bodies, comments, hidden text, credentials, tokens, or cookies.

**Alternatives considered**:

- Persist raw API responses. Rejected because responses may include sensitive or high-volume payloads.
- Keep only `api-error`. Rejected because it is not actionable enough to diagnose live hiding failures.
- Log detailed errors only to stdout. Rejected because the TUI and state file are the operator's primary incident surface.

## Decision: Coalesce repeated catch-up warnings into summaries

**Rationale**: One root-cause failure can affect every watched page, producing thousands of nearly identical warnings in the terminal. The daemon should classify the first failure, count repeated failures by class, preserve a small sample of titles, and render a summary such as `1427 page queries failed: non-json-response`. When the repeated cause is a throttle signal such as `HTTP 429`, recovery should also stop or pause early instead of filling unresolved state with the same transient cause. This keeps the operator surface readable while preserving enough detail for diagnosis.

**Alternatives considered**:

- Suppress warnings entirely. Rejected because failures must remain visible.
- Keep one warning per page. Rejected because the warning flood hides the actual issue and makes the TUI hard to use.
- Log only after catch-up finishes. Rejected because a long catch-up still needs progress and early failure visibility.

## Decision: Treat rate limiting as a first-class recovery contract

**Rationale**: The first remediation slice fixed the timestamp bug, but current runtime evidence still shows repeated `fetch-revisions` failures classified as `non-json-response` with `HTTP 429`, and the same class now appears on a failed live hide attempt. That means catch-up, reconciliation, and live-path revision queries must understand throttling as a normal degraded-protection state: capture `Retry-After`, expose backoff-until status, prefer recent work, and stop or pause recovery before one throttle event becomes thousands of repeated unresolved items.

**Alternatives considered**:

- Treat `429` as another generic retryable network error. Rejected because the daemon needs explicit operator-visible backoff behavior and shared coordination across recovery paths.
- Keep scanning all watched pages and mark every rate-limited page unresolved. Rejected because it wastes API budget, expands durable state, and hides the true root cause.
- Disable catch-up under any throttle event. Rejected because bounded retry or resume is still required for robustness.

## Decision: Keep durable unresolved evidence compact and sampled

**Rationale**: The constitution requires compact durable state and low-spec viability. Full unresolved item retention is useful only until it starts crowding out the actual diagnosis. The daemon should preserve total counts, aggregate warning summaries, and a bounded sample of unresolved items or titles, with clear stop-early reasons when the remaining unchecked set is omitted from detail.

**Alternatives considered**:

- Persist every unresolved item forever. Rejected because repeated recovery failures can make state files large and slow without adding proportional operator value.
- Drop unresolved details entirely. Rejected because operators still need a safe sample and aggregate counts to judge severity and follow up.

## Decision: Require explicit managed-daemon restart verification before release claims

**Rationale**: This incident is operator-facing, and local green tests do not prove the managed daemon or TUI is using the new binary or new status schema. Release evidence must include restarting the actual managed process, rechecking journal or status surfaces, and confirming the live TUI reflects the expected realtime and recovery fields.

**Alternatives considered**:

- Rely on local tests and dry-run output only. Rejected because stale services or pid files can make operators see older behavior.
- Require full production benchmarking before every code change. Rejected as too heavy for each iteration; the mandatory step is restart plus live status verification, with broader benchmark runs at release checkpoints.

## Decision: Reserve `runtime_status.json` for the daemon's own realtime truth

**Rationale**: Current TUI behavior can launch one-shot commands such as emergency catch-up or coverage report, and those commands bootstrap a fresh `AppRuntime`. If they write the same `runtime_status.json` as the long-running daemon, the status pane can show a mixture of daemon state and manual-command state. That violates the requirement for honest realtime status and makes `catching-up` look more common than the daemon itself believes. The daemon-owned runtime file must stay authoritative for realtime health; one-shot commands should emit stdout summaries and, if needed later, write to a separate bounded report surface.

**Alternatives considered**:

- Keep one shared runtime status file for daemon and one-shot commands. Rejected because operator trust depends on one authoritative realtime source.
- Suppress one-shot command status entirely. Rejected because operators still need visible command progress and completion, just not mixed into daemon realtime health.
- Infer daemon truth from logs when the runtime file is contaminated. Rejected because the TUI and local state should remain directly actionable.

## Decision: Preserve operator-surface compatibility or emit explicit migration diagnostics

**Rationale**: The updated feature spec now requires operator-facing machine-readable status/report surfaces and launch-path assumptions to remain backward-compatible where reasonable, or to fail safely with an explicit migration-needed diagnostic. The immediate reason is practical: recent work changed runtime JSON and operator expectations quickly enough that the previous setup could become invalid without a clear warning, and host checks now show that the real live path is a TUI-managed child process rather than the previously assumed systemd unit. Operators should not have to infer from broken JSON, stale pid files, or an empty journal that the authoritative diagnostics path changed. The preferred design is therefore compatibility first, with a compact machine-readable compatibility notice when an older state artifact, report reader, or launch-path assumption is no longer trustworthy.

**Alternatives considered**:

- Allow silent JSON, stdout, or launch-path drift across updates. Rejected because it creates false healthy readings and operator confusion at exactly the point the tool is supposed to provide trustworthy incident status.
- Rely on release notes or chat history alone. Rejected because the runtime and command surfaces themselves must remain actionable when an operator is already troubleshooting.
- Add a separate migration service or heavy compatibility layer. Rejected because the existing daemon, command reports, and docs can carry a bounded compatibility notice without new runtime processes or dependencies.

## Decision: Do not trigger full `startup` catch-up on every EventStreams reopen

**Rationale**: Current runtime evidence shows the daemon enters `catching-up` frequently because every `Event::Open` causes a bounded catch-up with trigger `startup`. Stream reopen is normal and does not by itself prove missed edits or daemon restart. Full watched-set catch-up should be reserved for true bootstrap, proven stream gaps, stale-stream recovery, or explicit operator actions; otherwise the daemon wastes API budget and spends time in recovery states that crowd the live path.

**Alternatives considered**:

- Keep the current behavior and accept frequent catch-up. Rejected because it delays recovery completion, confuses operators, and already misses the 2-minute recovery target.
- Disable reopen catch-up entirely. Rejected because genuine resume gaps and stale recovery still need bounded backfill.
- Always rely on freshness probing without catch-up. Rejected because probing alone cannot close real missed-edit windows.

## Decision: Treat zero-first-view prevention as out of scope for the current EventStreams architecture

**Rationale**: The current daemon reacts to RecentChanges after MediaWiki has already published an edit. Local evidence can still show good post-observation latency, but that cannot guarantee a human will never see the edit in history or recent changes before suppressor acts. The plan should therefore optimize and measure publish-to-detect, detect-to-queue, and detect-to-hide latency, while documenting that true zero-first-view prevention would require a broader in-wiki prevention or moderation hook outside the current single-daemon scope.

**Alternatives considered**:

- Promise that the daemon can always prevent the first human view. Rejected because it is not technically defensible for an external post-publication consumer.
- Ignore the operator expectation. Rejected because the limitation affects release claims and operator trust.
- Broaden this feature immediately into in-wiki pre-publication blocking. Rejected because it changes product scope, deployment model, and likely governance requirements.

## Decision: Separate daemon logs from one-shot command logs and make TUI latest-follow row-accurate

**Rationale**: Current TUI evidence can show delayed latest lines because the log viewport scrolls by logical input lines while the widget wraps long lines. The same pane also mixes daemon stdout/stderr with background command output, which makes a manual emergency catch-up look like daemon activity. The plan should keep daemon logs and operator command logs visibly labeled or separated, and the latest-follow behavior should track rendered rows or disable wrap for the log pane so the newest lines are actually visible when `latest` is selected.

**Alternatives considered**:

- Keep one mixed log pane and rely on prefixes alone. Rejected because the operator already misread one-shot command output as daemon runtime behavior.
- Keep wrapping and accept a few hidden latest lines. Rejected because it breaks the meaning of `Live Output [latest]`.
- Drop command logs from the TUI entirely. Rejected because one-shot commands still need operator feedback.

## Decision: Verify deployment evidence against the actual launch path, not an assumed systemd unit

**Rationale**: Host checks showed no installed `suppressor.service` unit and no useful journal entries under that unit name. The live process path on 2026-04-28 was `make tui`, which launched `target/debug/suppressor --config ./config.toml tui` and then a child `... run` daemon. In this setup, the real evidence path is the daemon process actually launched by the supervisor/TUI plus its state files and labeled stdout/stderr. Planning and docs should therefore distinguish “systemd-managed daemon” from “TUI-managed child process” and require verification against whichever launch path is truly in use.

**Alternatives considered**:

- Keep assuming `journalctl -u suppressor.service` is always authoritative. Rejected because it currently returns no useful evidence.
- Drop journal verification entirely. Rejected because it remains useful when the daemon is actually installed as a service.
- Treat state files alone as enough production evidence. Rejected because process identity and launch path still matter.

## Decision: Separate stream freshness from live hide effectiveness and force state convergence

**Rationale**: April 28 runtime evidence showed fresh target-wiki events still arriving with `current_lag_seconds=0`, while the latest live outcome remained failed and the daemon still reported `catching-up` even after `catchup_active=false` and backoff had cleared. Fresh stream input alone is not proof that live protection is effective. The runtime contract therefore needs to treat stream freshness, active recovery, and live hide effectiveness as separate signals, and the state machine must converge out of `catching-up` once recovery is no longer active.

**Alternatives considered**:

- Infer overall health from fresh stream events alone. Rejected because a fresh stream can coexist with a broken live suppression path.
- Leave `catching-up` active until a later manual refresh. Rejected because it makes the operator surface dishonest and hides whether the daemon is actually degraded or recovered.
- Add a second independent always-on daemon just for liveness. Rejected because the current single-daemon architecture can represent these signals if the contracts are explicit.

## Decision: Use the bot test page for external benchmark evidence

**Rationale**: The operator explicitly allowed `Удзельнік:Plaga med Bot/suppressor/tests` for manual and automated tests and benchmarks. This provides a safe production wiki surface for publish-to-hide timing evidence without using sensitive articles. Every automated edit to that page must be marked as a bot edit, and benchmark content/summaries must be clearly test-only.

**Alternatives considered**:

- Benchmark only with synthetic events. Rejected because it cannot prove end-to-end MediaWiki edit, stream, API, and RevDel behavior.
- Use arbitrary watched sensitive pages. Rejected because tests should avoid real sensitive subjects.
- Mutate `Удзельнік:Wizardist/SuppressionList` for every benchmark. Rejected because routine benchmarks should not churn the production source list; source-list behavior should be tested explicitly and separately.
