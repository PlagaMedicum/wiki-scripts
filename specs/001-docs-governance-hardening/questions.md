---
docmeta:
  status: working
  review: feature-local
  purpose: Feature-local questions, answers, and pending comment requests.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Open Questions: Docs Governance Hardening


This file is the policy-backed place for follow-up questions on this feature. New questions should
be added here instead of relying on chat-only context.

## Status Legend

- `pending-answer`: direct answer requested from the client
- `pending-comment`: proposed direction awaiting review or comment
- `answered`: direct answer recorded and ready to fold into docs
- `commented`: comment recorded and ready to fold into docs
- `resolved`: answer captured in docs and no longer blocking this feature

## Schema

- Use one `### Q###:` heading per question.
- Include `Status`, `Owner`, `Why it matters`, and `Related Docs` for every entry.
- Include `Default` or `Proposed Solution` when a recommendation exists.
- Include `Answer` or `Comment` once client input has been provided.
- Move an item to `resolved` once the decision has been integrated into the feature docs or
  implementation plan.

## Questions

### Q001: Should the docs status tool add dedicated `answer_needed` and `comment_requested` categories?

- Status: resolved
- Owner: client
- Default: yes
- Why it matters: this decides whether file-based questions and comment requests are visible only in
  Markdown files or also reflected directly in the deterministic status report.
- Related Docs: `tools/doc_workflow.py`, `.specify/extensions/docs/README.md`,
  `.specify/extensions/docs/commands/speckit.docs.md`, `specs/001-docs-governance-hardening/review-queue.md`
- Answer: yes. The docs status tool should expose these categories directly.

### Q002: Should every future `.specify/templates/*` edit require matching workflow-doc updates or tests in the same feature?

- Status: resolved
- Owner: client
- Default: yes
- Why it matters: template changes shape future LLM behavior and can quietly change repo policy if
  they are not treated as policy-bearing edits.
- Related Docs: `.specify/templates/spec-template.md`, `.specify/templates/plan-template.md`,
  `specs/000-repo-governance/quickstart.md`
- Answer: Treat templates and similar defaults conservatively. Keep repo-local behavior close to
  upstream Spec Kit guidance unless the user explicitly confirms a workflow change, and pair
  policy-bearing changes with matching docs or tests.

### Q003: Should feature-local workflow docs use a stable local metadata/header schema?

- Status: resolved
- Owner: client
- Default: yes
- Why it matters: feature-local docs currently risk looking disconnected from repo policy or review
  handling.
- Related Docs: `specs/001-docs-governance-hardening/questions.md`,
  `specs/001-docs-governance-hardening/review-queue.md`,
  `specs/001-docs-governance-hardening/contracts/status-report.md`
- Answer: yes. Feature-local workflow docs should state their purpose, status, connected docs, and
  review handling explicitly.

### Q004: Which planned feature area should come next after `001-docs-governance-hardening`?

- Status: resolved
- Owner: client
- Default: `suppressor` next
- Why it matters: the governance roadmap should not rely on inline TODO comments for feature order.
- Related Docs: `specs/000-repo-governance/tasks.md`,
  `specs/001-docs-governance-hardening/spec.md`,
  `specs/001-docs-governance-hardening/plan.md`
- Answer: `suppressor` follow-on work should be prioritized next.
