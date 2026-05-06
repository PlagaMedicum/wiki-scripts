---
docmeta:
  status: draft
  review: feature-local
  purpose: Feature specification for restoring urgent real-time suppressor hiding.
  source:
  - user request on 2026-04-24
  - user request on 2026-04-28
  - user request on 2026-04-29
  - user request on 2026-05-05
  - user request on 2026-05-05 for one-command detached server start
---

# Feature Specification: Real-Time Suppression Recovery


## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hide New Sensitive Edits Immediately (Priority: P1)

As the suppressor operator, I need eligible edits on watched sensitive pages to be hidden automatically as soon as they appear, without relying on manual refreshes, so exposed sensitive changes do not remain visible in recent changes.

**Why this priority**: This is the active incident. The operator observed a new edit on a sensitive article still visible after about 24 minutes while the daemon was shown as running, which defeats the suppressor's primary safety purpose.

**Independent Test**: With the suppressor running and a test eligible edit appearing on a watched sensitive page, the edit becomes hidden without any manual operator action and the operator can verify the suppression from the wiki and the operator console.

**Acceptance Scenarios**:

1. **Given** the suppressor is running with current rights and the page is in the watched sensitive-page set, **When** a new eligible edit is published, **Then** the edit is hidden automatically within the real-time target and the operator console records the action.
2. **Given** the operator does not press manual refresh or cache reload, **When** multiple eligible edits arrive on watched sensitive pages, **Then** each eligible edit is handled by the background process without waiting for the nightly workflow.
3. **Given** an edit is not eligible for hiding under the configured policy, **When** it appears on a watched page, **Then** the suppressor leaves it visible and records why no hiding action was taken.

---

### User Story 2 - Detect And Recover From Real-Time Stalls (Priority: P2)

As the suppressor operator, I need the operator console to show whether real-time monitoring is fresh, delayed, or stalled, and I need the daemon to recover automatically where possible, so a running process cannot silently stop hiding new edits.

**Why this priority**: The screenshot shows a running daemon with old last-event state and completed reconciliation while recent visible edits remain unhidden. A "running" label is not enough if the real-time path is stale.

**Independent Test**: Simulate a real-time feed stall or gap while eligible edits are published; the operator console reports stale monitoring promptly, the daemon attempts recovery, and eligible missed edits are caught up.

**Acceptance Scenarios**:

1. **Given** the suppressor has not observed recent change activity for longer than the freshness threshold while wiki activity continues, **When** the operator views status, **Then** the console clearly reports stale real-time monitoring and the current lag.
2. **Given** the real-time stream disconnects, stalls, or resumes with a gap, **When** the daemon recovers, **Then** it catches up on eligible missed edits before reporting the real-time path as healthy again.
3. **Given** a suppression attempt fails because of rights, session, rate, network, or wiki-side errors, **When** the daemon continues running, **Then** the operator sees a clear actionable notice and the edit remains queued for retry or manual review.
4. **Given** fresh target-wiki events continue to arrive but the latest eligible live suppression attempt is failed, throttled, blocked, or unresolved, **When** the operator views status, **Then** the console reports degraded protection rather than a healthy real-time state.
5. **Given** the operator runs an emergency catch-up or coverage report while the daemon is already running, **When** the operator views status and command output, **Then** daemon-owned real-time status remains authoritative and the command output is clearly distinguishable from daemon evidence.
6. **Given** the stream reopens without a real missed-change gap or only reconnect noise occurred, **When** monitoring resumes, **Then** the daemon does not relabel the event as startup recovery and does not remain in a recovery state after recovery has ended.
7. **Given** an updated version changes a previously documented operator status surface, report surface, or authoritative launch path, **When** the operator prepares to run that version, **Then** the release evidence clearly states whether the previous setup remains valid and, if not, the required migration or verification steps before the new version is trusted.
8. **Given** the suppressor was offline or failed for a period, **When** automatic recovery starts, **Then** the daemon resumes coverage from the timestamp of the last successful hide recorded before the interruption and does not declare healthy until the missed watched-page exposure since that point is hidden or reported unresolved.
9. **Given** the daemon stays up through the day, **When** a randomized verification run is scheduled, **Then** it rechecks the rolling last 24 hours of watched-page exposure and records that exact verification window for the operator.
10. **Given** the daemon stays up through the night, **When** the nightly fallback run is scheduled, **Then** it performs a full watched-set recheck at a randomized night hour rather than relying only on the daytime rolling window.
11. **Given** an updated version changes the authoritative operator surface, launch path, or status artifact format, **When** the operator reviews release evidence before trusting that version, **Then** the evidence includes the required human approval point, required migration checks, and a clear fallback or rollback path to the last trusted workflow.

---

### User Story 3 - Verify Accident-Window Coverage (Priority: P3)

As the suppressor operator, I need confidence that edits made after the suppressor-rights accident have either been hidden or explicitly reported as unresolved, so the night-time workflow is not treated as complete while sensitive edits are still exposed.

**Why this priority**: The operator already ran a night-time workflow and suspects all or some accident-window changes were hidden, but the immediate incident shows that hidden coverage and current protection both need verification.

**Independent Test**: Run an accident-window coverage check over the configured sensitive-page set and receive a concise report of hidden, already-hidden, skipped, failed, and unresolved edits.

**Acceptance Scenarios**:

1. **Given** the operator starts an accident-window coverage check, **When** the check completes, **Then** every eligible edit in that window is counted as hidden, already hidden, skipped by policy, failed, or unresolved.
2. **Given** unresolved eligible edits remain after the coverage check, **When** the operator views the report, **Then** the report lists the affected page, edit identifier, age, reason, and recommended next action without exposing sensitive content.
3. **Given** the operator needs a routine verification run, **When** they choose the explicit `Last 24 hours` coverage preset, **Then** the command and the operator surface clearly show that the report covers the rolling last 24 hours rather than an arbitrary recent window.

### Edge Cases

- The daemon starts after eligible edits already appeared and must catch up without waiting for the next nightly run.
- The real-time feed reconnects and replays events that were already hidden.
- The watched sensitive-page list changes while the daemon is running.
- The suppressor account loses rights, has an expired session, or is throttled while eligible edits are arriving.
- A page is moved, deleted, protected, or otherwise changes state between edit detection and hiding.
- Multiple eligible edits arrive in a short burst across many watched pages.
- An edit is already hidden manually or by another operator before the suppressor acts.
- The operator console is open but not refreshed while background hiding continues.
- Logs, notices, and reports must avoid storing sensitive article content or hidden text.
- A recent-change event or API result is missing expected metadata such as title, revision ID, actor, timestamp, or comment flags.
- A catch-up window includes pages that moved, disappeared, or left the watched set during the window.
- Retry exhaustion leaves unresolved items after catch-up and requires operator escalation or documented release blocking.
- `Удзельнік:Wizardist/SuppressionList` changes while eligible edits already exist on newly added pages.
- `Вікіпедыя:Запыты да схавальнікаў` changes while the cached source list is unchanged but recent watched-page edits still need immediate verification.
- MediaWiki rejects a timestamp parameter or returns a non-JSON/API-error response during catch-up or RevDel.
- A low-spec host runs the daemon and TUI concurrently while catch-up, logging, and status persistence are active.
- A one-shot diagnostic or reporting action runs while the daemon is healthy, catching up, stale, unhealthy, or blocked and must not replace daemon-owned status truth.
- Fresh target-wiki events continue to arrive while the latest live hide outcome is still failed, throttled, blocked, or unresolved.
- The stream reopens or reconnects without a true missed-change gap and must not be mislabeled as startup recovery.
- Recovery starts after an outage longer than the daytime rolling verification window and must still resume from the last successful hide instead of silently truncating coverage.
- A randomized daytime rolling 24-hour recheck overlaps with a source-triggered recovery, manual catch-up, or nightly full recheck and must stay truthful about which coverage window each action is handling.
- The actual deployment path uses a local supervisor rather than a system service, so operator verification must use the authoritative runtime surface for that path.
- Long wrapped lines appear in a compact terminal and must not push the newest daemon evidence out of view in latest-follow mode.
- An actionable revision ID is shown in the operator surface and must be directly usable as a browser-openable link without needing a separate action.
- The primary operator view contains internal bookkeeping or raw transport artifacts that do not answer whether protection is working, what is happening now, or what needs operator attention.
- An updated version encounters older operator state or status artifacts whose shape reflects the previously documented setup.
- An updated version changes which launch path, supervisor, or diagnostics surface is authoritative for operator verification.
- The operator needs to build the server binary for rsync using the previously proven
  `cargo zigbuild --release --target aarch64-unknown-linux-musl` path.
- The operator has rsynced the server binary to a remote host and needs one command from that
  binary to prepare local runtime paths, start the daemon detached from the SSH terminal, and return
  only after the background daemon has trustworthy PID and status evidence.
- The detached server-start command sees a missing config, missing auth secret, stale PID file,
  existing live daemon, unwritable state directory, or failed health/status wait and must fail
  before presenting the daemon as safely running in the background.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST continuously monitor new changes on watched sensitive pages whenever the suppressor daemon is running.
- **FR-002**: The system MUST automatically hide each newly published eligible edit on a watched sensitive page without requiring manual refresh, cache reload, or nightly reconciliation.
- **FR-003**: The system MUST keep the real-time hiding path active independently from slower reconciliation, coverage, or reporting work.
- **FR-004**: The system MUST determine and record one final outcome for every observed watched-page edit: hidden, already hidden, skipped by policy, failed, retried, or unresolved.
- **FR-005**: The system MUST detect stale, stalled, disconnected, or gapped real-time monitoring and attempt recovery without operator intervention.
- **FR-006**: The system MUST catch up on eligible watched-page edits missed during daemon downtime, feed gaps, restart, or recovery from the timestamp of the last successful hide recorded before the interruption, or from an explicitly documented older trusted recovery anchor if that timestamp is unavailable, before declaring real-time monitoring healthy.
- **FR-007**: The system MUST surface real-time health in the operator console, including current freshness, lag, last observed change, last eligible edit handled, last hiding action, latest actionable error, and enough context to distinguish transport freshness from live hide effectiveness, and the primary operator view MUST use plain-language labels and consistent field naming that answer whether protection is working now, what background work is active, what the last meaningful hide/error was, and how long the daemon has been continuously protecting edits.
- **FR-008**: The system MUST provide an operator-initiated emergency catch-up or verification action that checks recent watched-page edits and reports unresolved exposure.
- **FR-009**: The system MUST provide an accident-window coverage report that separates hidden, already-hidden, skipped, failed, and unresolved edits, and it MUST also provide a clearly labeled operator-visible `Last 24 hours` verification preset so the operator can run or review a rolling 24-hour check without supplying custom timestamps.
- **FR-010**: The system MUST retry transient hiding failures while avoiding duplicate or conflicting actions for edits that are already hidden.
- **FR-011**: The system MUST preserve safety boundaries by hiding only edits that match the watched-page set and the suppressor policy.
- **FR-012**: The system MUST produce audit information sufficient for operational review without exposing sensitive content, hidden text, credentials, tokens, or session secrets.
- **FR-013**: The system MUST make "daemon running but real-time hiding ineffective" visible as an unhealthy or degraded-protection state rather than a normal running state, even when fresh target-wiki events are still arriving.
- **FR-014**: The system MUST support verification with controlled events so regressions in immediate hiding, stall detection, catch-up, and reporting can be tested before production use.
- **FR-015**: The system MUST treat changes to `Удзельнік:Wizardist/SuppressionList` and configured source-adjacent request pages, including `Вікіпедыя:Запыты да схавальнікаў`, as immediate recovery triggers that refresh source state and run bounded catch-up for newly added or recently affected watched pages, or visibly defer that follow-up with a retry point when shared recovery limits prevent immediate execution.
- **FR-016**: The system MUST serialize MediaWiki API timestamp parameters in a MediaWiki-accepted UTC second-precision format and test this behavior against catch-up and coverage queries.
- **FR-017**: The system MUST classify MediaWiki/API/transport failures into compact non-sensitive categories, persist the actionable class/code/status and failure context, and aggregate repeated failures so one root cause cannot flood the TUI or terminal, regardless of whether the failure occurs in live hiding, source refresh, catch-up, or reconciliation.
- **FR-018**: The system MUST keep implementation boundaries microservice-like inside the existing local daemon: stream ingestion, source refresh, catch-up, worker execution, state persistence, and TUI rendering communicate through explicit structs, bounded channels, and small interfaces, without adding extra OS services or public network surfaces for this feature.
- **FR-019**: The system MUST remain economical on low-spec hardware by using bounded queues, bounded catch-up windows, bounded concurrency, compact persisted state, coalesced logging, and no unbounded in-memory revision/title buffers, without lowering latency/recovery targets or dropping documentation evidence.
- **FR-020**: The system MUST preserve implementation lessons in durable code comments, tests, and maintained suppressor docs when they prevent recurrence of this incident, especially timestamp formatting, source-list catch-up, error classification, warning coalescing, and test-page benchmark rules.
- **FR-021**: The system MUST treat the daemon-owned runtime status surface as authoritative for operator real-time health, and one-shot diagnostic, coverage, benchmark, or report actions MUST NOT overwrite or impersonate that daemon-owned state.
- **FR-022**: The system MUST expose whether the latest actionable failure or outcome came from live hiding, recovery catch-up, reconciliation, source refresh, or one-shot operator work so the operator can tell which protection path is degraded.
- **FR-023**: The system MUST leave transient recovery states once catch-up or backoff has ended and MUST report the resulting healthy, unhealthy, reconnecting, or blocked state according to remaining evidence rather than staying in a stale recovery label.
- **FR-024**: The system MUST treat true startup recovery, ordinary reopen, reconnect noise, and gap recovery as distinct operator-visible situations and MUST NOT relabel ordinary reopen noise as startup recovery.
- **FR-025**: The system MUST keep daemon runtime evidence and one-shot command output visibly distinguishable in operator surfaces, and compact/latest views MUST keep the newest daemon evidence visible enough for the operator to trust the current state.
- **FR-026**: The system MUST let operators verify health and recovery through the actual launch path and authoritative diagnostics surface in use, rather than assuming a particular service manager or unit name exists.
- **FR-027**: The system MUST preserve backward-compatible operator-facing machine-readable status and report surfaces for the previously documented setup, or explicitly declare any intentional incompatibility before release readiness is claimed.
- **FR-028**: If an update invalidates a previously documented launch path, persisted state artifact, or operator workflow, the system MUST provide an explicit migration notice, required operator actions, the new authoritative diagnostics path, the required human approval point before trusting the new setup, and a clear fallback or rollback path to the last trusted workflow before the update is treated as production-ready.
- **FR-029**: The system MUST detect incompatible, unreadable, or stale prior operator state or supervisory artifacts and surface a non-healthy or migration-needed diagnostic instead of silently presenting healthy status.
- **FR-030**: While the daemon remains running, the system MUST schedule randomized daytime verification runs that recheck the rolling last 24 hours of watched-page exposure and record the exact covered window and outcome counts in operator-visible status or reports.
- **FR-031**: While the daemon remains running, the system MUST schedule a full watched-set fallback recheck at a randomized night hour and keep that run clearly distinct from the rolling last 24-hour daytime verification.
- **FR-032**: Actionable operator surfaces that show a safe revision identifier for inspection MUST render that identifier as a browser-openable link or equivalent directly usable target without requiring a separate lookup action.
- **FR-033**: The primary operator status view MUST prioritize operator-meaningful evidence over internal counters by clearly showing current protection state, daemon uptime, current background task and progress, last successful hide, current recovery or verification window, latest actionable error, and any recent offline or stalled interval before exposing secondary diagnostic bookkeeping.
- **FR-034**: The suppressor Makefile MUST provide an additive server-build target that runs
  `cargo zigbuild --release --target aarch64-unknown-linux-musl`, leaves existing local build
  targets unchanged, and prints the rsync-ready artifact path
  `target/aarch64-unknown-linux-musl/release/suppressor`.
- **FR-035**: The suppressor binary MUST provide an additive `server-start` CLI command that
  prepares required runtime directories, validates the configured local config and auth environment
  without writing secrets, refuses to start a duplicate live daemon, starts the normal daemon or
  dry-run daemon detached from the invoking terminal, redirects daemon output to a non-sensitive
  operator-visible log path, waits for PID and daemon-owned runtime-status evidence, prints the PID,
  status path, log path, mode, and config path, and exits successfully only when the background
  process remains alive after that verification.

### Key Entities

- **Watched Sensitive Page**: A page whose new eligible edits must be protected by the suppressor. Key attributes include page identity, current listing source, and whether it is active for suppression.
- **Observed Edit**: A newly observed or caught-up change on a watched page. Key attributes include page, edit identifier, timestamp, actor category, eligibility status, and handling outcome.
- **Suppression Action**: A hide attempt or confirmed hide result for an observed edit. Key attributes include target edit, outcome, timing, error reason if any, and retry state.
- **Real-Time Health State**: The operator-visible freshness and effectiveness state of background monitoring. Key attributes include last observed change time, last eligible edit time, current lag, recovery state, latest actionable notice, latest protection outcome, and whether stream freshness and hide effectiveness currently agree.
- **Coverage Window**: A bounded time range used to verify edits after the suppressor-rights accident or after daemon downtime. Key attributes include start, end, checked pages, counted outcomes, and unresolved items.
- **API Failure Snapshot**: A compact non-sensitive classification of a MediaWiki/API/transport failure. Key attributes include failure class, API code, HTTP status, retryability, failure context, safe sample title/revision, and timestamp.
- **Source Refresh Event**: An observed source-list or request-page change plus its refresh and immediate catch-up result. Key attributes include trigger title, trigger revision, old/new source revision, added/removed titles, catch-up scope, outcome, deferred-by-backoff status, retry point, and safe error details.
- **Operator Command Report**: A bounded summary emitted by a one-shot operator action. Key attributes include action type, outcome counts, unresolved totals, safe next action, command provenance, and its separation from daemon-owned real-time status.
- **Benchmark Run**: A controlled verification run on `Удзельнік:Plaga med Bot/suppressor/tests`. Key attributes include run ID, bot-marked edit count, timing samples, percentile summaries, and unresolved benchmark revisions.
- **Deployment Artifact**: The server binary produced for rsync deployment. Key attributes include
  target triple, build command, artifact path, source revision or dirty-state note, and verification
  result without credentials or secrets.
- **Detached Daemon Launch**: A one-command server start attempt from the deployed binary. Key
  attributes include command name, binary path, config path, state directory, PID file, runtime
  status path, log path, live or dry-run mode, started PID, start timestamp, verification result,
  and any stale or duplicate daemon diagnostic without credentials or secrets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under normal wiki availability and account rights, at least 95% of newly published eligible watched-page edits are hidden within 1 second of becoming visible, and 99% are hidden within 5 seconds; release evidence must report p95 and p99 for the controlled realtime path.
- **SC-002**: If real-time monitoring is stale, stalled, disconnected, or ineffective for more than 10 seconds while relevant wiki activity continues, including cases where fresh events continue but the latest live hide outcome is failed, throttled, blocked, or unresolved, the operator console shows a non-healthy state and current lag measured against the latest observed target-wiki event or a bounded API freshness probe when the stream is silent.
- **SC-003**: For daemon restart or real-time recovery gaps up to 30 minutes, eligible watched-page edits missed since the recorded `last_successful_hide_at` timestamp, or since an explicitly documented older trusted fallback anchor when that timestamp is unavailable, are either hidden or reported unresolved within 2 minutes.
- **SC-003a**: Recovery evidence MUST name the selected anchor, covered window start and end, outcome counts, unresolved samples, and whether the anchor was `last_successful_hide_at` or a fallback; the daemon MUST NOT declare healthy until that selected window is hidden or reported unresolved.
- **SC-004**: Accident-window verification accounts for 100% of eligible watched-page edits in the selected window as hidden, already hidden, skipped, failed, or unresolved.
- **SC-005**: The operator can distinguish "running and hiding", "running but catching up", "running but unhealthy", "blocked by rights/session/wiki error", and "one-shot operator command output" from the console without inspecting raw logs.
- **SC-006**: Automated or controlled verification covers immediate hiding, feed stall recovery, missed-edit catch-up, duplicate event handling, a burst of at least 10 controlled eligible events across watched pages, public `user|comment` RevDel safety boundaries, and rights/session failure reporting.
- **SC-007**: When `Удзельнік:Wizardist/SuppressionList` adds a watched title during daemon operation, the daemon refreshes the source state and starts bounded catch-up for newly added titles without waiting for manual reload or scheduled reconciliation.
- **SC-008**: Catch-up and coverage tests prove that MediaWiki timestamp parameters contain no fractional precision and that a mocked `badtimestamp` response is surfaced as a classified non-retryable API failure instead of thousands of per-page warnings.
- **SC-009**: Runtime warning output for a repeated catch-up/API root cause is coalesced into an aggregate summary with counts and safe samples, and the TUI remains readable on a compact terminal.
- **SC-010**: A benchmark run using `Удзельнік:Plaga med Bot/suppressor/tests` creates only bot-marked test edits, accounts for every benchmark revision, and records publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings.
- **SC-011**: Low-spec verification records idle and active resource use for daemon alone and daemon plus TUI, including CPU percentage, RSS memory, live queue depth and cap, catch-up or reconciliation queue depth and cap, API concurrency, runtime-status size, command-report size, processed-revision state size, detached log growth rate, and coalesced-warning counts. MVP release evidence MUST include at least a 10-minute idle sample plus one active live/recovery/backoff sample on the deployment host, and it MUST block release unless API concurrency remains at or below the default cap of 2, queues stay below their configured caps or surface degraded status before saturation, status/report files remain below 1 MiB each, repeated-root-cause log growth stays below 10 MiB/hour or has a documented mitigation, and no measured field shows unbounded growth after the active sample returns idle.
- **SC-012**: Durable suppressor docs and targeted code comments/tests capture the incident lessons, performance evidence, and operational checks needed to prevent recurrence, including timestamp formatting, source-triggered catch-up, API error classification, warning coalescing, and benchmark safety.
- **SC-013**: Once catch-up or backoff ends and no other blocking or recovery condition remains, the operator console leaves the transient recovery state within 10 seconds and shows the resulting healthy, unhealthy, reconnecting, or blocked state.
- **SC-014**: During a one-shot diagnostic, coverage, benchmark, or reporting action, the operator can still identify daemon-owned real-time state, the source of the latest actionable problem, and the newest daemon evidence from the console without manual refresh or raw-log inspection.
- **SC-015**: Release evidence accounts for 100% of intentional operator-surface or launch-path incompatibilities by either proving unchanged behavior against the previously documented setup or listing the required migration actions before production use.
- **SC-016**: When older state artifacts or invalid launch-path assumptions are present, status inspection yields a non-healthy or migration-needed diagnostic within 10 seconds rather than a false healthy state.
- **SC-017**: During each 24-hour period of uninterrupted daemon operation, operator evidence shows at least one randomized daytime rolling last-24-hours verification run and one randomized nightly full recheck, each with its own clearly named coverage window or scope.
- **SC-018**: In operator-visible actionable rows, 100% of safe rendered revision identifiers are directly usable as links, and the `Last 24 hours` preset is visually distinguishable from arbitrary timestamped coverage reports.
- **SC-019**: In the compact primary operator view, an informed operator can determine within 15 seconds whether protection is currently effective, whether recovery or verification is in progress, what the last successful hide was, what the latest actionable problem is, and whether the current version still uses the trusted operator workflow, without reading raw logs or secondary diagnostics.
- **SC-020**: The operator can run `make build-server` from `suppressor/` and receive a successful
  aarch64 Linux musl release binary path suitable as the rsync source for server deployment.
- **SC-021**: After rsyncing the server binary to the target host, the operator can run
  `./suppressor --config ./config.toml server-start`, close the SSH terminal, and within 10 seconds
  verify that the PID remains alive, `runtime_status.json` is daemon-owned and updating, daemon
  output is written to the printed log path, and missing config/secrets or duplicate/stale daemon
  conditions fail with a non-healthy diagnostic instead of creating an orphaned or falsely healthy
  daemon.

## Assumptions

- The suppressor remains scoped to be.wikipedia.org sensitive-page suppression and does not broaden into a general moderation tool.
- The operator account is expected to have the required suppression rights during normal operation; missing rights are treated as an urgent unhealthy condition.
- Manual refresh and cache reload are diagnostic or recovery aids, not prerequisites for hiding newly published edits.
- Nightly reconciliation remains a fallback safety net; real-time hiding is the primary protection path.
- The exact accident window can be supplied during planning or operation; the feature must support checking any bounded recent window rather than hard-coding one date range.
- The persisted timestamp of the last successful hide is trustworthy enough to serve as the primary automatic recovery anchor unless an older explicit compatibility rule says otherwise.
- Sensitive article content and hidden text must not be displayed in routine logs, reports, or console status.
- Microservice architecture means internal microservice-like boundaries in one local binary for this feature, not a split into extra deployed services.
- Economy means bounded resource use and measured low-spec behavior without compromising performance, latency, recovery targets, or documentation quality.
- Real-time hiding begins only after an eligible edit becomes observable to this external monitoring path; eliminating all first-view exposure would require a broader in-wiki or pre-publication control path outside this feature's scope.
- The deployment may use a local supervisor path instead of a system service manager, so operator-facing requirements must remain truthful for whichever authoritative launch path is actually in use.
- Terminals used by operators can make direct use of rendered revision links or plain revision URLs without requiring a separate browser-launch action in the TUI itself.
- Repo-wide rules for compatibility prompts or migration approval may grow from this incident, but this feature is responsible only for the suppressor-specific operator surfaces and setup it changes.
- Release evidence can require an explicit human go/no-go check when compatibility, migration, or rollback risk would otherwise leave the operator guessing whether the new setup is safe to trust.
- A deployed server host already has or receives the required `config.toml` and `.env`/environment
  secrets through an operator-controlled path; the `server-start` command may create runtime
  directories and log files, but it must not generate, store, print, or rsync credentials.
- The target server for the documented MVP deployment is a Linux host that can run the
  aarch64-unknown-linux-musl suppressor binary, invoke it from a local shell, keep a detached child
  alive after SSH logout through the binary's own process-detach behavior, reach be.wikipedia.org,
  and write the configured state directory, PID file, runtime status file, cache files, and
  detached log path. The MVP deployment MUST NOT assume systemd, tmux, screen, shell backgrounding,
  or `nohup` are available or authoritative.

## Documentation Impact

- Update suppressor operator documentation to explain real-time health states, expected hiding latency, emergency catch-up, and accident-window coverage checks.
- Update suppressor operator documentation to explain the `Last 24 hours` preset, the automatic recovery anchor at the last successful hide, the randomized daytime rolling 24-hour verification, and the randomized nightly full recheck.
- Update suppressor implementation or runtime-boundary documentation to distinguish real-time hiding, catch-up, and nightly reconciliation responsibilities.
- Update suppressor implementation or runtime-boundary documentation to distinguish rolling 24-hour daytime verification from the randomized nightly full watched-set recheck.
- Update suppressor testing documentation with controlled verification cases for immediate hiding, stale monitoring, missed-event catch-up, duplicate events, and rights/session failures.
- Update operator-facing docs and release evidence to explain revision-link rendering, coverage-window naming, and how the operator should interpret recovery start points derived from the last successful hide.
- Update operator-facing docs and release evidence to explain the required approval point, compatibility verdict, and fallback or rollback path whenever a release changes the trusted operator workflow or status artifacts.
- Update implementation docs with internal service boundaries, resource-economy defaults, state/log bounds, and incident lessons that should shape future suppressor changes.
- Update operations docs with low-spec expectations, benchmark use of `Удзельнік:Plaga med Bot/suppressor/tests`, bot-edit requirements, and release evidence interpretation.
- Update operator and operations docs to explain daemon-owned status truth, one-shot command separation, launch-path-aware verification, and degraded protection versus mere stream freshness.
- Update operator-facing docs to define the primary status view in operator language, including uptime, current task, recovery window, last successful hide, latest actionable error, and which secondary diagnostics are intentionally de-emphasized.
- Update operator-facing docs to state the post-publication architecture limit explicitly and avoid any claim that the current feature can guarantee zero first-view prevention.
- Update operator-facing docs or quickstart with the `make build-server` wrapper for
  `target/aarch64-unknown-linux-musl/release/suppressor` and the requirement not to store server
  credentials in release evidence.
- Update operator-facing docs or quickstart with the `server-start` one-command background launch
  path, including its safe failure modes, PID/status/log evidence, and the rule that it does not
  replace secrets provisioning or claim systemd authority.
- If this feature establishes a reusable compatibility or migration-warning rule for machine-readable operator surfaces, capture the generalized lesson in `specs/000-repo-governance/research.md` instead of leaving it only in suppressor-local docs.
- Repo governance has been amended in constitution v1.5.0 to require low-spec economy without performance, robustness, or documentation compromise.
