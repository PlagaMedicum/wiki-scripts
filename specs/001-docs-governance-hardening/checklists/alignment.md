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

## Notes

- This checklist captures the current drift after the frontmatter-first implementation landed.
- Use it alongside `governance.md`: governance tests requirement quality, while this file tests cross-artifact coherence and close-out readiness.
