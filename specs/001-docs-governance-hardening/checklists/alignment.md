---
docmeta:
  status: working
  review: feature-local
  purpose: Checklist for cross-artifact alignment and close-out readiness of docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](../spec.md)'
---

# Alignment Checklist: Docs Governance Hardening


## Spec-Plan-Tasks Coherence

- [ ] CHK001 Does the specification define frontmatter-first metadata as the canonical contract rather than the removed rendered `DOCMETA`/CSS header path? [Consistency, Conflict]
- [ ] CHK002 Does `plan.md` describe the same frontmatter-first scope that the committed implementation delivered, instead of template placeholders or an older closure-only slice? [Consistency, Conflict]
- [ ] CHK003 Does `tasks.md` distinguish already-implemented work from the still-open review, approval, and close-out work? [Completeness, Conflict]
- [ ] CHK004 Is lifecycle vocabulary consistent enough across the spec, plan, tasks, and review queue to distinguish implemented, review-open, and closure-ready states? [Clarity, Gap]

## Metadata Migration Contract

- [ ] CHK005 Are managed-doc requirements specific that registry-backed values sync into frontmatter rather than into visible HTML metadata blocks? [Clarity, Gap]
- [ ] CHK006 Are non-managed Markdown docs defined by schema validation rather than by exact registry-sync expectations? [Consistency, Gap]
- [ ] CHK007 Are lean-by-type rules explicit enough that skill and command docs preserve top-level `name`, `description`, `compatibility`, and `metadata` without redundant duplicated semantics? [Clarity, Gap]
- [ ] CHK008 Are legacy `DOCMETA` compatibility rules explicit about parse tolerance, frontmatter precedence, and post-migration lint expectations? [Completeness, Gap]

## Review & Closure Readiness

- [ ] CHK009 Do the plan and tasks treat remaining human approvals and requested comments as explicit close-out blockers instead of mixing them into implementation work? [Acceptance Criteria, Gap]
- [ ] CHK010 Are the conditions for clearing `.specify/feature.json` concrete enough that closure cannot happen while review items remain pending? [Clarity, Gap]
- [ ] CHK011 Are final review and close-out steps documented so a maintainer can finish the feature without guessing which docs or commands still matter? [Coverage, Gap]

## Assumptions & Cleanup

- [ ] CHK012 Are obsolete assumptions about preview CSS, collapsible headers, or rendered shared metadata blocks explicitly removed or superseded? [Conflict, Gap]
- [ ] CHK013 Do the docs explain why legacy headers may still parse during migration while frontmatter is the sole authoritative metadata surface? [Clarity, Assumption]

## Write-Surface Safety

- [ ] CHK014 Do the requirements distinguish repo-wide metadata migration from feature-artifact generation clearly enough that maintainers can tell which write surface they are invoking? [Clarity, Spec §User Story 2, Spec §FR-018, Spec §FR-019, Spec §FR-020]
- [ ] CHK015 Is the phrase “explicit maintainer-approved overwrite action” specific enough to implement without guessing whether the workflow should stop, prompt, force, or require a dedicated flag? [Ambiguity, Spec §FR-019]
- [ ] CHK016 Do the migration requirements define exactly what content must be preserved during frontmatter sync, including non-metadata prose and existing type-specific frontmatter keys? [Completeness, Spec §FR-018, Spec §SC-007, Spec §SC-008]
- [ ] CHK017 Are the requirements for inspecting or narrowing metadata rewrites concrete enough to distinguish preview/dry-run behavior from scoped mutation behavior? [Clarity, Spec §FR-020, Gap]

## Implementation Readiness

- [ ] CHK018 Do `plan.md` and `tasks.md` reflect the new write-surface safety scope, rather than only the older closure-semantics slice and shared-header migration wording? [Consistency, Plan §Summary, Tasks §Phase 1-4]
- [ ] CHK019 Are the success criteria specific enough to verify both migration completion and overwrite protection as separate outcomes, instead of bundling them into one vague “safe rewrite” claim? [Acceptance Criteria, Spec §SC-006, Spec §SC-007, Spec §SC-008]
- [ ] CHK020 Does the documentation-impact section name the concrete docs, templates, and tooling entrypoints that must change to implement overwrite guardrails and safer rewrite scope? [Coverage, Spec §Documentation Impact]

## Notes

- This checklist captures the current drift after the frontmatter-first implementation landed.
- Use it alongside `governance.md`: governance tests requirement quality, while this file tests cross-artifact coherence and close-out readiness.
