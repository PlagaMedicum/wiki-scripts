---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for resource economy, performance preservation, and durable documentation.
  source: speckit-checklist on 2026-04-25
---

# Resource Economy Checklist: Real-Time Suppression Recovery

**Purpose**: Validate that requirements define low-spec operation without compromising performance, robustness, operator visibility, or documentation quality.
**Created**: 2026-04-25
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [ ] CHK001 Are resource-economy requirements defined across CPU, memory, disk, network, queue depth, polling, API concurrency, state retention, and log volume? [Completeness, Plan §Resource Goals, Spec §FR-019]
- [ ] CHK002 Are bounded-resource requirements documented for every internal boundary that can buffer, retry, poll, persist, or emit repeated warnings? [Completeness, Spec §FR-018, Plan §Internal Service Boundaries]
- [ ] CHK003 Are performance-preservation requirements complete enough to prevent resource economy from lowering the 1-second, 5-second, stale-detection, and 2-minute recovery targets? [Completeness, Spec §FR-019, Spec §SC-001, Spec §SC-003, Spec §SC-011]
- [ ] CHK004 Are documentation-preservation requirements defined for operator docs, implementation docs, runtime-boundary docs, testing strategy, and concise code comments where lessons are non-obvious? [Completeness, Spec §FR-020, Spec §SC-012, Plan §Documentation impact]
- [ ] CHK005 Are source-list and request-page immediate-recovery requirements complete for cache refresh, watched-title diffing, catch-up scope, success outcome, and failure outcome? [Completeness, Spec §FR-015, Spec §SC-007, Contract §Source-List Immediate Recovery]
- [ ] CHK006 Are warning-coalescing requirements complete for repeated API/catch-up failures, including aggregate counts, safe samples, root-cause classification, and compact TUI display? [Completeness, Spec §FR-017, Spec §SC-009, Contract §Runtime Status]
- [ ] CHK007 Are benchmark requirements complete for approved page scope, bot edit marker, safe content, run labeling, sample-size limits, timing fields, and source-list non-mutation? [Completeness, Spec §SC-010, Contract §Test Page Benchmark]
- [ ] CHK008 Are low-spec release-evidence requirements defined for normal operation and failure/recovery scenarios, not only the happy-path daemon state? [Completeness, Data Model §ResourceEconomySnapshot, Quickstart §Resource Economy And Boundary Check]

## Requirement Clarity

- [ ] CHK009 Is "low-spec" clarified with measurable evidence fields or environment notes instead of remaining an informal hardware label? [Ambiguity, Spec §SC-011, Data Model §ResourceEconomySnapshot]
- [ ] CHK010 Is "bounded" clarified with configurable limits, retention rules, or explicit maximums for queues, concurrency, state, benchmark samples, and warning summaries? [Clarity, Spec §FR-019, Plan §Resource Goals, Tasks §Phase 2]
- [ ] CHK011 Is "without lowering latency/recovery targets" expressed in a way that can be objectively compared against the performance success criteria? [Clarity, Spec §FR-019, Spec §SC-001, Spec §SC-003]
- [ ] CHK012 Is "without dropping documentation evidence" clarified with required durable locations and evidence types rather than a broad documentation aspiration? [Clarity, Spec §FR-020, Spec §SC-012, Quickstart §Feature Close-Out Notes]
- [ ] CHK013 Is "microservice-like" clarified enough to require typed internal ownership boundaries while excluding extra OS services and public network surfaces for this feature? [Clarity, Spec §FR-018, Plan §Architecture Constraints, Research §Microservice-like internal boundaries]
- [ ] CHK014 Is the distinction between diagnostic/fallback actions and primary live protection clear for cache reload, nightly reconciliation, current-day reconciliation, and emergency catch-up? [Clarity, Spec §FR-002, Spec §FR-003, Contract §Operator Commands]

## Requirement Consistency

- [ ] CHK015 Are resource-economy requirements consistent between the constitution v1.5.0 amendment, feature spec, implementation plan, and generated tasks? [Consistency, Spec §Assumptions, Plan §Constitution Check, Tasks §Phase 6]
- [ ] CHK016 Are benchmark requirements consistent between the spec, operator-command contract, quickstart, and task list about using only `Удзельнік:Plaga med Bot/suppressor/tests` and marking edits as bot edits? [Consistency, Spec §SC-010, Contract §Test Page Benchmark, Quickstart §Bot Test Page Benchmark, Tasks §T076-T090]
- [ ] CHK017 Are API timestamp requirements consistent between the runtime finding, functional requirement, success criterion, research decision, and foundational tasks? [Consistency, Spec §FR-016, Spec §SC-008, Research §Serialize MediaWiki API timestamps, Tasks §T006-T007]
- [ ] CHK018 Are warning-summary requirements consistent between the API failure requirement, TUI contract, research decision, and US2 tasks? [Consistency, Spec §FR-017, Spec §SC-009, Contract §Runtime Status, Tasks §T045-T057]
- [ ] CHK019 Are durable-documentation requirements consistent with the feature close-out note that feature-local planning artifacts may be removed after lessons are copied into maintained suppressor docs? [Consistency, Spec §FR-020, Spec §SC-012, Quickstart §Feature Close-Out Notes]

## Acceptance Criteria Quality

- [ ] CHK020 Can the low-spec success criterion be objectively evaluated from the written requirements, including what measurements are required and what result blocks production-readiness claims? [Measurability, Spec §SC-011, Contract §Resource Economy Verification]
- [ ] CHK021 Can the warning-coalescing success criterion be objectively evaluated without relying on subjective TUI readability alone? [Measurability, Spec §SC-009, Contract §Runtime Status]
- [ ] CHK022 Can benchmark success be objectively evaluated for both smoke evidence and percentile-compliance evidence? [Measurability, Spec §SC-010, Data Model §BenchmarkRun, Quickstart §Benchmark And Latency Evidence]
- [ ] CHK023 Can documentation success be objectively evaluated from the written criteria for lessons, performance evidence, operational checks, and maintained docs? [Measurability, Spec §SC-012, Quickstart §Durable Lesson Check]
- [ ] CHK024 Are release-readiness criteria explicit about whether unresolved resource, latency, external-wiki, or documentation gaps block release or allow a narrower confidence claim? [Acceptance Criteria, Quickstart §Production Readiness Gate]

## Scenario Coverage

- [ ] CHK025 Are requirements defined for resource behavior during idle daemon, daemon plus TUI, live edit, startup catch-up, source-refresh catch-up, benchmark, and repeated-failure scenarios? [Coverage, Data Model §ResourceEconomySnapshot, Contract §Resource Economy Verification]
- [ ] CHK026 Are requirements defined for recovery when source-list refresh succeeds but immediate catch-up fails or remains unresolved? [Coverage, Spec §FR-015, Data Model §SourceListRefresh, Contract §Source Refresh Contract]
- [ ] CHK027 Are requirements defined for quiet-stream conditions where the EventStreams feed is silent but the wiki is active, including how the freshness probe stays bounded? [Coverage, Spec §SC-002, Contract §Runtime Status, Plan §Phase 6]
- [ ] CHK028 Are requirements defined for repeated root-cause failures that affect many watched pages without letting the terminal warning surface become the main operator interface? [Coverage, Spec §SC-009, Research §Coalesce repeated catch-up warnings]
- [ ] CHK029 Are requirements defined for benchmark runs with too few samples, failed bot markers, unhidden benchmark revisions, and unavailable external wiki conditions? [Coverage, Contract §Test Page Benchmark, Quickstart §Production Readiness Gate]
- [ ] CHK030 Are requirements defined for old or missing runtime status fields so resource-economy and realtime-health reporting cannot falsely appear healthy after upgrade? [Coverage, Contract §Compatibility]

## Dependencies & Assumptions

- [ ] CHK031 Are assumptions about single local operator, local hardware limits, MediaWiki API availability, EventStreams behavior, and account rights documented at the right level for resource-economy decisions? [Assumption, Spec §Assumptions, Plan §Technical Context]
- [ ] CHK032 Are external dependencies for benchmark edits, bot markers, RevDel rights, and production wiki availability documented without turning external success into an unstated release prerequisite? [Dependency, Contract §Test Page Benchmark, Quickstart §Production Readiness Gate]
- [ ] CHK033 Are assumptions about avoiding new runtime dependencies, processes, public services, and framework layers consistent with the required internal service boundaries? [Assumption, Plan §Minimalism Constraints, Research §Prefer small targeted code]
- [ ] CHK034 Are documentation dependencies clear enough to show which maintained docs must receive durable lessons before feature-local planning notes can be removed? [Dependency, Spec §Documentation Impact, Quickstart §Feature Close-Out Notes]

## Ambiguities & Conflicts

- [ ] CHK035 Is there any ambiguity between "low catch-up concurrency by default" and the requirement to complete 30-minute recovery within 2 minutes? [Ambiguity, Spec §SC-003, Plan §Phase 6]
- [ ] CHK036 Is there any conflict between compact warning summaries and the need to preserve enough safe diagnostic evidence for post-incident diagnosis? [Conflict, Spec §FR-017, Data Model §ApiFailureSnapshot]
- [ ] CHK037 Is there any ambiguity about whether low-spec verification must be automated, manual, or both for production-readiness claims? [Ambiguity, Spec §SC-011, Quickstart §Resource Economy And Boundary Check]
- [ ] CHK038 Is there any ambiguity about when concise code comments are required versus when tests or maintained docs are sufficient to preserve a durable lesson? [Ambiguity, Spec §FR-020, Data Model §DurableLesson]

## Notes

- Focus areas: resource economy, performance preservation, warning coalescing, source-triggered recovery, benchmark evidence, and durable documentation.
- Depth: standard reviewer gate before implementation.
- Audience/timing: author and reviewer before `$speckit-implement`.
- These items test the quality of the written requirements, not whether the suppressor implementation works.
