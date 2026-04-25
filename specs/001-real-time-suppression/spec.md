---
docmeta:
  status: draft
  review: feature-local
  purpose: Feature specification for restoring urgent real-time suppressor hiding.
  source: user request on 2026-04-24
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

---

### User Story 3 - Verify Accident-Window Coverage (Priority: P3)

As the suppressor operator, I need confidence that edits made after the suppressor-rights accident have either been hidden or explicitly reported as unresolved, so the night-time workflow is not treated as complete while sensitive edits are still exposed.

**Why this priority**: The operator already ran a night-time workflow and suspects all or some accident-window changes were hidden, but the immediate incident shows that hidden coverage and current protection both need verification.

**Independent Test**: Run an accident-window coverage check over the configured sensitive-page set and receive a concise report of hidden, already-hidden, skipped, failed, and unresolved edits.

**Acceptance Scenarios**:

1. **Given** the operator starts an accident-window coverage check, **When** the check completes, **Then** every eligible edit in that window is counted as hidden, already hidden, skipped by policy, failed, or unresolved.
2. **Given** unresolved eligible edits remain after the coverage check, **When** the operator views the report, **Then** the report lists the affected page, edit identifier, age, reason, and recommended next action without exposing sensitive content.

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

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST continuously monitor new changes on watched sensitive pages whenever the suppressor daemon is running.
- **FR-002**: The system MUST automatically hide each newly published eligible edit on a watched sensitive page without requiring manual refresh, cache reload, or nightly reconciliation.
- **FR-003**: The system MUST keep the real-time hiding path active independently from slower reconciliation, coverage, or reporting work.
- **FR-004**: The system MUST determine and record one final outcome for every observed watched-page edit: hidden, already hidden, skipped by policy, failed, retried, or unresolved.
- **FR-005**: The system MUST detect stale, stalled, disconnected, or gapped real-time monitoring and attempt recovery without operator intervention.
- **FR-006**: The system MUST catch up on eligible watched-page edits missed during daemon downtime, feed gaps, restart, or recovery before declaring real-time monitoring healthy.
- **FR-007**: The system MUST surface real-time health in the operator console, including current freshness, lag, last observed change, last eligible edit handled, last hiding action, and latest actionable error.
- **FR-008**: The system MUST provide an operator-initiated emergency catch-up or verification action that checks recent watched-page edits and reports unresolved exposure.
- **FR-009**: The system MUST provide an accident-window coverage report that separates hidden, already-hidden, skipped, failed, and unresolved edits.
- **FR-010**: The system MUST retry transient hiding failures while avoiding duplicate or conflicting actions for edits that are already hidden.
- **FR-011**: The system MUST preserve safety boundaries by hiding only edits that match the watched-page set and the suppressor policy.
- **FR-012**: The system MUST produce audit information sufficient for operational review without exposing sensitive content, hidden text, credentials, tokens, or session secrets.
- **FR-013**: The system MUST make "daemon running but real-time hiding ineffective" visible as an unhealthy state rather than a normal running state.
- **FR-014**: The system MUST support verification with controlled events so regressions in immediate hiding, stall detection, catch-up, and reporting can be tested before production use.
- **FR-015**: The system MUST treat changes to `Удзельнік:Wizardist/SuppressionList` and configured source-adjacent request pages, including `Вікіпедыя:Запыты да схавальнікаў`, as immediate recovery triggers that refresh source state and run bounded catch-up for newly added or recently affected watched pages.
- **FR-016**: The system MUST serialize MediaWiki API timestamp parameters in a MediaWiki-accepted UTC second-precision format and test this behavior against catch-up and coverage queries.
- **FR-017**: The system MUST classify MediaWiki/API/transport failures into compact non-sensitive categories, persist the actionable class/code/status, and aggregate repeated failures so one root cause cannot flood the TUI or terminal.
- **FR-018**: The system MUST keep implementation boundaries microservice-like inside the existing local daemon: stream ingestion, source refresh, catch-up, worker execution, state persistence, and TUI rendering communicate through explicit structs, bounded channels, and small interfaces, without adding extra OS services or public network surfaces for this feature.
- **FR-019**: The system MUST remain economical on low-spec hardware by using bounded queues, bounded catch-up windows, bounded concurrency, compact persisted state, coalesced logging, and no unbounded in-memory revision/title buffers, without lowering latency/recovery targets or dropping documentation evidence.
- **FR-020**: The system MUST preserve implementation lessons in durable code comments, tests, and maintained suppressor docs when they prevent recurrence of this incident, especially timestamp formatting, source-list catch-up, error classification, warning coalescing, and test-page benchmark rules.

### Key Entities

- **Watched Sensitive Page**: A page whose new eligible edits must be protected by the suppressor. Key attributes include page identity, current listing source, and whether it is active for suppression.
- **Observed Edit**: A newly observed or caught-up change on a watched page. Key attributes include page, edit identifier, timestamp, actor category, eligibility status, and handling outcome.
- **Suppression Action**: A hide attempt or confirmed hide result for an observed edit. Key attributes include target edit, outcome, timing, error reason if any, and retry state.
- **Real-Time Health State**: The operator-visible freshness and effectiveness state of background monitoring. Key attributes include last observed change time, last eligible edit time, current lag, recovery state, and latest actionable notice.
- **Coverage Window**: A bounded time range used to verify edits after the suppressor-rights accident or after daemon downtime. Key attributes include start, end, checked pages, counted outcomes, and unresolved items.
- **API Failure Snapshot**: A compact non-sensitive classification of a MediaWiki/API/transport failure. Key attributes include failure class, API code, HTTP status, retryability, operation, safe sample title/revision, and timestamp.
- **Source Refresh Event**: An observed source-list or request-page change plus its refresh and immediate catch-up result. Key attributes include trigger title, trigger revision, old/new source revision, added/removed titles, catch-up scope, outcome, and safe error details.
- **Benchmark Run**: A controlled verification run on `Удзельнік:Plaga med Bot/suppressor/tests`. Key attributes include run ID, bot-marked edit count, timing samples, percentile summaries, and unresolved benchmark revisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under normal wiki availability and account rights, at least 95% of newly published eligible watched-page edits are hidden within 1 second of becoming visible, and 99% are hidden within 5 seconds; release evidence must report p95 and p99 for the controlled realtime path.
- **SC-002**: If real-time monitoring is stale, stalled, disconnected, or ineffective for more than 10 seconds while relevant wiki activity continues, the operator console shows an unhealthy state and current lag measured against the latest observed target-wiki event or a bounded API freshness probe when the stream is silent.
- **SC-003**: After daemon restart or real-time recovery, eligible watched-page edits missed in the preceding 30 minutes are either hidden or reported unresolved within 2 minutes.
- **SC-004**: Accident-window verification accounts for 100% of eligible watched-page edits in the selected window as hidden, already hidden, skipped, failed, or unresolved.
- **SC-005**: The operator can distinguish "running and hiding", "running but catching up", "running but unhealthy", and "blocked by rights/session/wiki error" from the console without inspecting raw logs.
- **SC-006**: Automated or controlled verification covers immediate hiding, feed stall recovery, missed-edit catch-up, duplicate event handling, a burst of at least 10 controlled eligible events across watched pages, public `user|comment` RevDel safety boundaries, and rights/session failure reporting.
- **SC-007**: When `Удзельнік:Wizardist/SuppressionList` adds a watched title during daemon operation, the daemon refreshes the source state and starts bounded catch-up for newly added titles without waiting for manual reload or scheduled reconciliation.
- **SC-008**: Catch-up and coverage tests prove that MediaWiki timestamp parameters contain no fractional precision and that a mocked `badtimestamp` response is surfaced as a classified non-retryable API failure instead of thousands of per-page warnings.
- **SC-009**: Runtime warning output for a repeated catch-up/API root cause is coalesced into an aggregate summary with counts and safe samples, and the TUI remains readable on a compact terminal.
- **SC-010**: A benchmark run using `Удзельнік:Plaga med Bot/suppressor/tests` creates only bot-marked test edits, accounts for every benchmark revision, and records publish-to-detect, detect-to-queue, queue-to-hide, and publish-to-hidden timings.
- **SC-011**: Low-spec verification records idle and active resource use for daemon plus TUI, and default configuration keeps queues, concurrency, state files, and logs bounded while meeting the realtime and recovery targets.
- **SC-012**: Durable suppressor docs and targeted code comments/tests capture the incident lessons, performance evidence, and operational checks needed to prevent recurrence, including timestamp formatting, source-triggered catch-up, API error classification, warning coalescing, and benchmark safety.

## Assumptions

- The suppressor remains scoped to be.wikipedia.org sensitive-page suppression and does not broaden into a general moderation tool.
- The operator account is expected to have the required suppression rights during normal operation; missing rights are treated as an urgent unhealthy condition.
- Manual refresh and cache reload are diagnostic or recovery aids, not prerequisites for hiding newly published edits.
- Nightly reconciliation remains a fallback safety net; real-time hiding is the primary protection path.
- The exact accident window can be supplied during planning or operation; the feature must support checking any bounded recent window rather than hard-coding one date range.
- Sensitive article content and hidden text must not be displayed in routine logs, reports, or console status.
- Microservice architecture means internal microservice-like boundaries in one local binary for this feature, not a split into extra deployed services.
- Economy means bounded resource use and measured low-spec behavior without compromising performance, latency, recovery targets, or documentation quality.

## Documentation Impact

- Update suppressor operator documentation to explain real-time health states, expected hiding latency, emergency catch-up, and accident-window coverage checks.
- Update suppressor implementation or runtime-boundary documentation to distinguish real-time hiding, catch-up, and nightly reconciliation responsibilities.
- Update suppressor testing documentation with controlled verification cases for immediate hiding, stale monitoring, missed-event catch-up, duplicate events, and rights/session failures.
- Update implementation docs with internal service boundaries, resource-economy defaults, state/log bounds, and incident lessons that should shape future suppressor changes.
- Update operations docs with low-spec expectations, benchmark use of `Удзельнік:Plaga med Bot/suppressor/tests`, bot-edit requirements, and release evidence interpretation.
- Repo governance has been amended in constitution v1.5.0 to require low-spec economy without performance, robustness, or documentation compromise.
