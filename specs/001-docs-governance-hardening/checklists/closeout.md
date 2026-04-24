---
docmeta:
  status: working
  review: feature-local
  purpose: Close-out and merge-readiness checklist for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](../spec.md)'
---

# Close-Out Checklist: Docs Governance Hardening


## Requirement Completeness

- [X] CHK001 Are the remaining close-out requirements complete enough to cover managed-doc registry review, maintained-doc TODO cleanup, feature-local review queue cleanup, final validation, feature-pointer cleanup, commit, and merge? [Completeness, Plan §Remaining Incremental Delivery, Tasks §Phase 7]
- [X] CHK002 Are all close-out blockers from the status workflow represented in written requirements or tasks, including `approval_needed`, `comment_requested`, `update_needed`, and `registry_or_link_errors` states? [Completeness, Spec §FR-002, Contract §Status Report Output, Tasks §T014-T023]
- [X] CHK003 Are requirements present for reconciling `.specify/memory/constitution.md` alongside `specs/000-repo-governance/spec.md`, `plan.md`, and `quickstart.md`, rather than treating constitution drift as out of scope? [Completeness, Plan §TODO Review Findings, Plan §Task Reconciliation Rule]
- [X] CHK004 Are requirements defined for the exact maintained-governance docs whose review or approval state must be registry-backed before close-out? [Completeness, Spec §FR-027, Plan §Slice B, Tasks §T015]
- [X] CHK005 Are requirements defined for how each `RQ001` through `RQ008` queue item becomes non-blocking, rather than only saying the queue should be cleared? [Completeness, Review Queue §Current Queue, Tasks §T022-T023]
- [X] CHK006 Are requirements present for keeping the `suppressor` follow-on work as the next feature after `001` without mixing suppressor implementation scope into this feature? [Completeness, Spec §FR-013, Spec §SC-004, Tasks §T020-T021]

## Requirement Clarity

- [X] CHK007 Is "close-out" clearly distinguished from "implemented in the tree", "review-open", "closure-ready", and "landed in repo history"? [Clarity, Contract §Delivery-State Language, Plan §Summary]
- [X] CHK008 Is the intended source of truth for durable managed-doc review state stated unambiguously as `.specify/doc-registry.json`, not Markdown frontmatter edits? [Clarity, Spec §FR-027, Contract §Managed Governance Review Capture]
- [X] CHK009 Are the requirements clear about which inline TODO-style comments should be moved, deleted as stale, or rehomed in a follow-on feature? [Clarity, Spec §FR-028, Plan §TODO Review Findings]
- [X] CHK010 Is the difference between repo-level unresolved governance questions and feature-scoped human input specified clearly enough to decide between `research.md`, `questions.md`, and `review-queue.md`? [Clarity, Spec §FR-029, Contract §Temporary Review Surface Contract]
- [X] CHK011 Is the final meaning of `closure_needed` specified clearly enough that it cannot appear while feature-local review rows remain actionable? [Clarity, Contract §Closure Semantics, Spec §FR-009]
- [X] CHK012 Are merge-readiness requirements specific about what must be true before `.specify/feature.json` stops pointing at `001`? [Clarity, Contract §Closure Semantics, Plan §Slice D, Tasks §T023]

## Requirement Consistency

- [X] CHK013 Do `spec.md`, `plan.md`, `tasks.md`, and `contracts/status-report.md` agree that the registry remains authoritative when feature-local queue files mention managed-doc review state? [Consistency, Spec §FR-009, Spec §FR-027, Contract §Queue Precedence And Fallback]
- [X] CHK014 Do the open task descriptions align with the plan's wider scope that includes `.specify/memory/constitution.md` cleanup? [Consistency, Plan §Task Reconciliation Rule, Tasks §T014-T016]
- [X] CHK015 Are requirements consistent about not copying stale reminders into temporary review surfaces when the durable docs already resolve them? [Consistency, Plan §Delivery Priorities, Spec §FR-029]
- [X] CHK016 Are lifecycle requirements consistent about not treating a passing docs gate as approval, closure, or merge completion by itself? [Consistency, Contract §Delivery-State Language, Plan §Close-Out Strategy]
- [X] CHK017 Are the feature-local review queue statuses consistent with the canonical status categories documented for the docs workflow? [Consistency, Review Queue §Status Legend, Contract §Status Report Output]
- [X] CHK018 Are close-out requirements consistent with the constitution rule that maintained standing-governance docs must not retain unresolved inline TODO-style review comments? [Consistency, Spec §FR-028, Plan §Constitution Check]

## Acceptance Criteria Quality

- [X] CHK019 Are final validation success criteria measurable without relying on chat memory or unstated maintainer judgment? [Acceptance Criteria, Spec §SC-005, Plan §Validation Plan, Tasks §T023]
- [X] CHK020 Are acceptance criteria explicit that no unresolved TODO markers remain in updated docs shipped by this feature, while documented marker examples remain non-blocking? [Acceptance Criteria, Spec §SC-003, Contract §Unresolved Marker Policy]
- [X] CHK021 Are acceptance criteria defined for registry sync being clean after durable review-state changes, including no remaining Markdown-only review drift? [Acceptance Criteria, Spec §SC-014, Tasks §T015]
- [X] CHK022 Are acceptance criteria defined for unresolved standing-governance review comments being moved into the appropriate temporary surface or folded into accepted policy before the docs gate is considered clean? [Acceptance Criteria, Spec §SC-015, Tasks §T014-T016]
- [X] CHK023 Are acceptance criteria for the final feature state explicit enough to cover both a clean status queue and the active feature pointer being cleared? [Acceptance Criteria, Contract §Closure Semantics, Tasks §T023]
- [X] CHK024 Are merge-readiness acceptance criteria documented well enough to distinguish local branch readiness from the later act of merging into `main`? [Acceptance Criteria, Plan §Close-Out Strategy, Gap]

## Scenario Coverage

- [X] CHK025 Are primary close-out scenarios covered for registry-backed approval, feature-local comments, maintained-doc updates, validation, feature-pointer cleanup, commit, and merge? [Coverage, Plan §Remaining Incremental Delivery, Tasks §T014-T023]
- [X] CHK026 Are alternate scenarios covered where a review comment becomes accepted policy versus a still-unresolved research item versus a new follow-on feature? [Coverage, Spec §FR-028, Spec §FR-029]
- [X] CHK027 Are exception scenarios covered for registry/frontmatter drift discovered after sync or lint? [Coverage, Contract §Managed Governance Review Capture, Spec §SC-014]
- [X] CHK028 Are exception scenarios covered for feature-local review rows remaining actionable after the engineering work is otherwise complete? [Coverage, Review Queue §Current Queue, Contract §Closure Semantics]
- [X] CHK029 Are recovery requirements specified if final validation finds that `closure_needed` is suppressed because a queue item or update marker is still pending? [Coverage, Contract §Closure Semantics, Gap]
- [X] CHK030 Are handoff scenarios covered so the urgent suppressor feature can start only after `001` is no longer the active feature pointer? [Coverage, Spec §FR-013, Plan §Slice D]

## Edge Case Coverage

- [X] CHK031 Are requirements defined for case-insensitive TODO markers in maintained governance docs while excluding examples in contracts or requirement prose? [Edge Case, Spec §FR-010, Spec §FR-011, Contract §Unresolved Marker Policy]
- [X] CHK032 Are requirements defined for additive review-label combinations such as `client-input-derived` plus `approved` or `reviewed` during close-out? [Edge Case, Spec §FR-012, Contract §Managed Doc Review Semantics]
- [X] CHK033 Are requirements defined for no-active-feature behavior after `.specify/feature.json` is cleared, so managed-doc queues still report normally? [Edge Case, Spec §Edge Cases, Contract §Queue Precedence And Fallback]
- [X] CHK034 Are requirements defined for preserving existing filled feature artifacts if setup or planning commands are touched during close-out? [Edge Case, Spec §FR-019, Contract §Plan Setup Guardrail]
- [X] CHK035 Are requirements defined for distinguishing actual unresolved TODO markers from the intentional TODO mentions inside the `001` requirements, status contract, and checklist text? [Edge Case, Spec §FR-011, Plan §TODO Review Findings]
- [X] CHK036 Are requirements defined for cleanup of resolved temporary-surface items so `research.md`, `questions.md`, and `review-queue.md` do not become duplicate archives? [Edge Case, Spec §FR-029, Contract §Temporary Review Surface Contract]

## Non-Functional Requirements

- [X] CHK037 Are non-functional safety requirements explicit enough to prevent broad metadata rewrites from happening without preview or scoped intent? [Non-Functional, Spec §FR-020, Plan §Slice A]
- [X] CHK038 Are non-functional traceability requirements clear enough to preserve useful origin evidence without forcing excessive historical commentary into every maintained doc? [Non-Functional, Spec §FR-030, Plan §Slice B]
- [X] CHK039 Are non-functional workflow constraints explicit that this close-out must not become a general git policy engine or automatic approval system? [Non-Functional, Plan §Technical Context, Contract §Non-Goals]
- [X] CHK040 Are non-functional token-economy requirements preserved during close-out so compact status labels do not hide approval, manual review, comment, answer, update, or closure distinctions? [Non-Functional, Spec §FR-021-FR-026, Spec §SC-013]
- [X] CHK041 Are non-functional validation expectations documented for docs-tool unit coverage, metadata linting, status reporting, dry-run previews, setup-plan preservation, and the explicit docs gate? [Non-Functional, Plan §Validation Plan, Spec §SC-005]

## Dependencies & Assumptions

- [X] CHK042 Are assumptions documented about which client approvals are already durable versus still pending in the feature-local review queue? [Assumption, Review Queue §Current Queue, Spec §Assumptions]
- [X] CHK043 Are dependencies on `.specify/doc-registry.json`, managed-doc sync, feature-local queue parsing, and tracked Markdown scanning explicit enough for close-out reviewers? [Dependency, Spec §FR-002, Spec §FR-027, Plan §Technical Context]
- [X] CHK044 Are dependencies on `tools/doc_status.py`, `tools/doc_workflow.py`, and `.specify/scripts/bash/setup-plan.sh` tied to specific close-out requirements instead of implied by command examples only? [Dependency, Plan §Technical Context, Tasks §T011-T023]
- [X] CHK045 Are assumptions about branch state, commit state, and fast-forward merge eligibility documented as merge-readiness requirements rather than left outside the feature close-out model? [Assumption, Gap]
- [X] CHK046 Are assumptions about starting `002-suppressor-journalling-policy` after `001` closes documented without creating hidden work in the current feature? [Assumption, Spec §FR-013, Tasks §T020-T021]

## Ambiguities & Conflicts

- [X] CHK047 Is there any remaining ambiguity about whether `RQ001` through `RQ003` require approval labels in the registry, queue-row status changes, or both? [Ambiguity, Review Queue §Current Queue, Contract §Managed Governance Review Capture]
- [X] CHK048 Is there any remaining ambiguity about whether the constitution inline TODO should be handled by the same maintained-doc cleanup path as the standing-governance docs? [Ambiguity, Plan §Task Reconciliation Rule, Tasks §T014-T016]
- [X] CHK049 Is there any conflict between the task list saying `T014` touches only governance spec and quickstart and the plan saying constitution cleanup is also required? [Conflict, Plan §TODO Review Findings, Tasks §T014]
- [X] CHK050 Is there any conflict between clearing `.specify/feature.json` and needing the active feature pointer for the final status or docs gate requirements? [Conflict, Contract §Queue Precedence And Fallback, Tasks §T023]
- [X] CHK051 Is there any unresolved ambiguity about whether finished feature specs should be deleted, archived, or kept after durable lessons are captured? [Ambiguity, specs/000 Quickstart §Normal Flow, Plan §Close-Out Strategy]
- [X] CHK052 Is there any unresolved ambiguity about the exact merge policy into `main`, such as fast-forward-only versus merge commit, and where that policy should be documented? [Ambiguity, Gap]

## Notes

- Check items off as requirement-quality questions are answered, not as implementation commands are executed.
- Items intentionally test whether the close-out and merge requirements are complete, clear, consistent, and measurable.
