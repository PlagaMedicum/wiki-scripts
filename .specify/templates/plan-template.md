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
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable, or explicitly unknown]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens, or explicitly unknown]

If a direct human answer is still required, write it into `questions.md` or a feature-local review
file and either resolve it during research or stop instead of inventing policy. Do not rewrite
managed-doc review labels by hand; change `.specify/doc-registry.json` when durable review state
changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

Include document impact in this check:

- which README files change
- whether `specs/000-repo-governance/spec.md` changes
- whether `specs/000-repo-governance/research.md` changes
- whether the constitution or Spec Kit workflow files change
- whether `.specify/doc-registry.json` changes
- whether `make docs` / `python3 tools/doc_workflow.py all` must be run
- whether the feature needs `questions.md` or `review-queue.md` updates to capture pending human
  input explicitly

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
