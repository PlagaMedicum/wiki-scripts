---
docmeta:
  status: maintained
  review: workflow-local
  purpose: Template for implementation plans and design records.
  source: document-local metadata
---

# Implementation Plan: [FEATURE]


## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75, or explicitly unknown]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM, or explicitly unknown]  
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test, or explicitly unknown]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM, or explicitly unknown]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app, or explicitly unknown]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps, or explicitly unknown]  
**Resource Goals**: [CPU, memory, disk, network, queue, polling, and log-volume budgets or explicitly unknown]
**Compatibility/Migration**: [existing setup, config/state/schema/CLI/operator-surface/launch-path impact, migration path, rollback/fallback, or explicitly none]
**Config Change Review**: [if config files, schema, defaults, environment variable names, loading semantics, or deployment-required sections change, state motivation, human review evidence, backward-compatibility strategy, migration path, rollback/fallback, and server verification; otherwise explicitly none]
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable, or explicitly unknown]  
**Architecture Constraints**: [internal service boundaries, process boundaries, dependency limits, or explicitly unknown]
**Minimalism Constraints**: [what must stay simple, local, bounded, or low-overhead, or explicitly unknown]
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens, or explicitly unknown]

If a direct human answer is still required, write it into `questions.md` or a feature-local review
file and either resolve it during research or stop instead of inventing policy. Do not rewrite
managed-doc review labels by hand; change `.specify/doc-registry.json` when durable review state
changes. If standing-governance review produces unresolved follow-up, move it into
`specs/000-repo-governance/research.md` or another scoped review surface instead of leaving inline
TODO review comments in maintained docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

Include document impact in this check:

- whether an active human-safety freeze is in effect; if yes, confirm this feature is the active
  safety feature or a direct enabler, otherwise stop before planning
- whether `.specify/feature.json` points at the active safety feature when such a freeze is in
  effect
- which README files change
- whether `specs/000-repo-governance/spec.md` changes
- whether `specs/000-repo-governance/research.md` changes
- whether the constitution or Spec Kit workflow files change
- whether `.specify/doc-registry.json` changes
- whether standing-governance review follow-up must move out of maintained docs and into an
  authoritative temporary surface
- whether the change deletes, invalidates, or silently rewrites previous setups, schemas, state,
  configs, operator surfaces, or authoritative launch paths
- whether the change touches tracked config files, config schema, defaults, environment variable
  names, config loading semantics, or deployment-required config sections; if yes, confirm the
  motivation, explicit human review evidence, compatibility strategy, migration path,
  rollback/fallback, and deployment verification
- whether explicit human approval is required before destructive mutation, broad rewrite, major
  refactor, incompatible schema/surface change, or another setup-invalidating change
- whether compatibility strategy, migration steps, fallback/rollback, and operator-visible
  diagnostics are documented before implementation
- whether safety-, reliability-, or performance-sensitive work states resource goals, bounded
  concurrency/state/logging, and recovery/status behavior
- whether resource economy preserves performance targets and documentation completeness instead of
  treating them as optional
- whether a requested microservice architecture is represented by explicit ownership boundaries
  first, with any extra process or dependency justified by isolation or operator-control benefits
- whether low-spec verification, benchmarks, or manual checks are required before completion
- whether incident lessons need tests, docs, or narrowly useful code comments before closure
- whether `make docs` / `python3 tools/doc_workflow.py all` must be run
- whether the feature needs `questions.md` or `review-queue.md` updates to capture pending human
  input explicitly

If the active suppressor MVP freeze applies, the plan MUST minimize scope to the stable
server-runnable daemon path: automatic live hiding, recovery/reconciliation, nightly fallback,
truthful non-healthy status, bounded failure behavior, actual-launch-path verification, and the
shortest meaningful test evidence. Non-essential refactors, new services, cosmetic UI work, broad
docs, and unrelated tool changes must be deferred.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── questions.md         # Optional: direct human questions for the feature
├── review-queue.md      # Optional: current human action queue for the feature
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── checklists/          # Optional: requirements-quality checklists
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above. In this repo, that often means a project root such as `biblio/` or
`suppressor/`, not a synthetic top-level `src/` tree.]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
