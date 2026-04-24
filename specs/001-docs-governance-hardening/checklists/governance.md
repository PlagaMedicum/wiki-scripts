---
docmeta:
  status: working
  review: feature-local
  purpose: Governance checklist for docs governance hardening quality and review readiness.
  source: document-local metadata
  feature: '[spec.md](../spec.md)'
---

# Governance Checklist: Docs Governance Hardening


## Requirement Completeness

- [X] CHK001 Are file-backed review and question workflows defined for both the active feature and the deterministic status tool? [Completeness, Spec §FR-001, Spec §FR-002]
- [X] CHK002 Does the spec define which pending human actions must be represented explicitly in repo files? [Completeness, Spec §FR-001, Spec §FR-006]
- [X] CHK003 Are the major unresolved governance backlog chunks named as future features instead of left as generic backlog prose? [Completeness, Spec §FR-003]

## Requirement Clarity

- [X] CHK004 Is the boundary between `specs/000-repo-governance/` and `specs/NNN-feature-name/` stated in implementation-facing terms? [Clarity, Spec §FR-004]
- [X] CHK005 Is “deterministic” defined clearly enough for status-report behavior to be verified without guessing? [Clarity, Spec §FR-002, Spec §SC-001]
- [X] CHK006 Is the phrase “policy-bearing template edits” explained concretely enough to guide future `.specify` changes? [Clarity, Spec §FR-005, Spec §FR-007]

## Requirement Consistency

- [X] CHK007 Are the status names used consistently across the spec, review queue, questions file, and status-report contract? [Consistency, Spec §FR-001, Spec §FR-002]
- [X] CHK008 Do the success criteria align with the functional requirements without introducing extra undocumented queue behaviors? [Consistency, Spec §FR-001, Spec §FR-002, Spec §SC-001]

## Acceptance Criteria Quality

- [X] CHK009 Can the success criteria for queue visibility be measured by running documented commands and reading documented files? [Acceptance Criteria, Spec §SC-001, Spec §SC-002]
- [X] CHK010 Do the success criteria distinguish current workflow hardening from later `biblio` and `suppressor` implementation work? [Acceptance Criteria, Spec §SC-003]

## Scenario Coverage

- [X] CHK011 Are requirements defined for the case where the active feature has open questions but no managed-doc review changes? [Coverage, Edge Case]
- [X] CHK012 Are requirements defined for the case where a standing governance doc and a feature-local queue disagree about the current action needed? [Coverage, Edge Case]

## Edge Case Coverage

- [X] CHK013 Does the spec define what happens when there is no active feature pointer but a maintainer still needs a review queue? [Edge Case, Spec §Edge Cases]
- [X] CHK014 Are mixed resolved and unresolved question states handled explicitly in the requirements? [Edge Case, Spec §Edge Cases]

## Non-Functional Requirements

- [X] CHK015 Are the constraints against automatic approval and silent policy invention explicit enough to review objectively? [Non-Functional, Spec §FR-005, Spec §FR-007]
- [X] CHK016 Are test-coverage expectations specified for status-report behavior changes? [Non-Functional, Spec §FR-007, Spec §SC-004]

## Dependencies & Assumptions

- [X] CHK017 Are the assumptions about managed-doc review labels versus feature-local queues documented and non-conflicting? [Assumption, Spec §Assumptions]
- [X] CHK018 Are dependencies on existing docs tooling and Spec Kit scripts documented rather than implied? [Dependency, Plan §Technical Context]

## Ambiguities & Conflicts

- [X] CHK019 Is there any unresolved ambiguity about whether pending-answer and pending-comment states belong in the status tool or only in Markdown files? [Ambiguity, Gap]
- [X] CHK020 Do the requirements avoid conflating review visibility with an automatic approval system? [Conflict, Spec §FR-002, Spec §Assumptions]

## Workflow Schema Quality

- [X] CHK021 Are additive managed-doc review labels defined clearly enough to distinguish provenance from approval state? [Clarity, Spec §FR-002, Spec §FR-009]
- [X] CHK022 Are terminal question states such as `answered`, `commented`, and `resolved` defined so the status tool can stop reporting them as pending? [Consistency, Spec §FR-009]
- [X] CHK023 Are metadata/header expectations defined for feature-local workflow docs such as `questions.md`, `review-queue.md`, and `contracts/status-report.md`? [Completeness, Spec §FR-008]
- [X] CHK024 Are review-queue requirements specific enough to define which rows the status tool should parse and which remain human-facing only? [Clarity, Spec §FR-002, Spec §FR-009]
- [X] CHK025 Is unresolved-marker detection specified consistently enough to cover lowercase and mixed-case TODO comments? [Coverage, Spec §FR-010, Spec §SC-003]
- [X] CHK026 Does the spec state clearly that marker syntax documented in inline code or fenced examples must not be reported as unresolved work? [Clarity, Spec §FR-011, Spec §SC-003]
- [X] CHK027 Are additive review-label combinations specified clearly enough that provenance and terminal approval/review state can coexist without false backlog items? [Consistency, Spec §FR-012, Spec §SC-001]
- [X] CHK028 Does the spec encode the post-`001` feature order clearly enough that inline TODO comments are unnecessary? [Completeness, Spec §FR-013, Spec §SC-004]

## Frontmatter Authority & Migration

- [X] CHK029 Does the spec define YAML frontmatter as the canonical metadata authority and legacy `DOCMETA` as compatibility-only input rather than as the long-term rendered header system? [Consistency, Gap]
- [X] CHK030 Are migration requirements specific about how `DOCMETA`-only files are automatically augmented without dropping existing frontmatter keys, skill metadata, or document body content? [Completeness, Gap]
- [X] CHK031 Are lean-by-type rules defined clearly enough that skill and command docs can reuse `description` and `metadata.source` without being forced into duplicate `purpose` or `source` fields? [Clarity, Gap]
- [X] CHK032 Does the requirements set distinguish exact registry sync for managed docs from schema-only lint for non-managed Markdown under the frontmatter-first model? [Consistency, Gap]

## Presentation Contract

- [X] CHK033 Do the requirements avoid depending on collapsed HTML/CSS header rendering now that the intended metadata format is frontmatter-first and conventional Markdown-first? [Conflict, Spec §FR-018, Spec §FR-020, Spec §SC-006, Spec §SC-008]
- [X] CHK034 Are acceptance criteria written so preview success is judged by truthful frontmatter metadata and provenance clarity rather than by the presence of a rendered shared header block? [Acceptance Criteria, Gap]

## Cross-Artifact Alignment

- [X] CHK035 Do `plan.md` and `tasks.md` describe the same frontmatter-first scope as the feature intent, rather than an older closure-remediation slice or the removed DOCMETA/CSS design? [Consistency, Plan §Summary, Tasks §Phase 1-4]
- [X] CHK036 Is the close-out language across spec, plan, and tasks explicit enough to distinguish implemented work, review-open state, and readiness to clear `.specify/feature.json`? [Clarity, Plan §Delivery Priorities, Tasks §Phase 7]

## Traceability Residuals

- [X] CHK037 Do roadmap requirements such as `FR-003` and `FR-013` still have explicit traceability in `tasks.md`, rather than relying only on implication from `plan.md`, `spec.md`, or repo history? [Coverage, Traceability, Spec §FR-003, Spec §FR-013, Tasks §Phase 1-3]

## Review-Derived Governance Rules

- [X] CHK038 Are the requirements explicit that managed-governance review and approval changes become durable only through `.specify/doc-registry.json` plus sync, rather than through hand-edited Markdown review labels? [Clarity, Spec §FR-027]
- [X] CHK039 Do the requirements state clearly that unresolved review comments must leave maintained standing-governance docs and move into an authoritative temporary surface instead of remaining as inline TODO markers? [Completeness, Spec §FR-028]
- [X] CHK040 Is the temporary-surface split defined clearly enough that repo-level unresolved governance points live in `research.md` while feature-scoped human input stays in `questions.md` or `review-queue.md`? [Consistency, Spec §FR-029]
- [X] CHK041 Are the traceability expectations for durable lessons specific enough to preserve later audit value without requiring every maintained doc to carry excessive historical commentary? [Acceptance Criteria, Spec §FR-030]
