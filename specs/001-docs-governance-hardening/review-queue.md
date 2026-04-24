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
- `resolved`: durable docs or git history now carry the outcome

## Current Queue

| ID | Status | Subject | Owner | Note |
|----|--------|---------|-------|------|
| RQ001 | resolved | [governance spec](../000-repo-governance/spec.md) | client | Accepted repo decisions are approved through the registry-backed review state |
| RQ002 | resolved | [governance plan](../000-repo-governance/plan.md) | client | Standing documentation-structure contract is approved through the registry-backed review state |
| RQ003 | resolved | [governance quickstart](../000-repo-governance/quickstart.md) | client | Workflow quickstart is approved through the registry-backed review state |
| RQ004 | resolved | [spec.md](./spec.md) | client | Durable scope and schema lessons were lifted into maintained governance docs and the feature can rest in git history |
| RQ005 | resolved | [plan.md](./plan.md) | client | Durable review-capture, temporary-surface, and traceability lessons were lifted into maintained governance docs |
| RQ006 | resolved | [tasks.md](./tasks.md) | client | Remaining close-out work was completed and the finished feature tree can be removed |
| RQ007 | resolved | [contracts/status-report.md](./contracts/status-report.md) | client | Queue semantics and unresolved-marker policy are reflected in maintained workflow guidance |
| RQ008 | resolved | [checklists/governance.md](./checklists/governance.md) | client | Checklist lessons are closed; future audit can use git history |
