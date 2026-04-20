---
docmeta:
  status: working
  review: feature-local
  purpose: Feature-local review queue for pending approval, comment, and update work.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Review Queue: Docs Governance Hardening


This queue is the current human action surface for the active feature and the related standing docs.
Core implementation is already in the tree; the remaining items here are review and approval
blockers that keep the feature review-open.

## Status Legend

- `approval_needed`: explicit client approval needed
- `manual_review_needed`: human review or comment needed
- `answer_needed`: direct answer requested in `questions.md`
- `comment_requested`: review comment requested in `questions.md`
- `update_needed`: document or workflow update still needed

## Current Queue

| ID | Status | Subject | Owner | Note |
|----|--------|---------|-------|------|
| RQ001 | approval_needed | [governance spec](../000-repo-governance/spec.md) | client | Accepted repo decisions still need explicit client confirmation in the registry |
| RQ002 | approval_needed | [governance plan](../000-repo-governance/plan.md) | client | Standing documentation-structure contract still needs explicit client confirmation in the registry |
| RQ003 | approval_needed | [governance quickstart](../000-repo-governance/quickstart.md) | client | Workflow quickstart still needs explicit client confirmation in the registry |
| RQ004 | comment_requested | [spec.md](./spec.md) | client | Review the updated scope, schema requirements, additive review-label semantics, and `speckit.docs` priority |
| RQ005 | comment_requested | [plan.md](./plan.md) | client | Review the updated implementation priorities, marker-example guardrail, and follow-on feature order |
| RQ006 | comment_requested | [tasks.md](./tasks.md) | client | Review the updated task ordering with `speckit.docs` reliability first and `doc_status.py` included in the schema work |
| RQ007 | comment_requested | [contracts/status-report.md](./contracts/status-report.md) | client | Review the proposed queue schema, review-label semantics, and unresolved-marker policy |
| RQ008 | comment_requested | [checklists/governance.md](./checklists/governance.md) | client | Review whether the requirements-quality checklist covers the schema, additive review labels, and docs-workflow risks |
