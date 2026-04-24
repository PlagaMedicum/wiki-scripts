---
docmeta:
  status: working
  review: feature-local
  purpose: Research decisions and design tradeoffs for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Research: Docs Governance Hardening


## Decision 1: Use feature-local `questions.md` and `review-queue.md` files for active human input

- **Decision**: Keep direct human questions and review queues in feature-local Markdown files under
  `specs/NNN-feature-name/`.
- **Rationale**: This preserves the distinction between durable repo governance and scoped feature
  work, while making pending answers visible from the repo instead of chat-only context.
- **Alternatives considered**:
  - Put all questions in `specs/000-repo-governance/research.md`: rejected because feature-local
    blocking questions would pollute standing repo policy docs.
  - Keep questions only in chat: rejected because it violates the requested workflow and is not
    durable or reviewable.

## Decision 2: Extend docs status reporting with file-backed answer and comment visibility

- **Decision**: Teach `tools/doc_workflow.py status` to report `answer_needed` and
  `comment_requested` from the active feature, while also recognizing terminal states such as
  `answered`, `commented`, and `resolved` so already-processed items stop showing as pending.
- **Rationale**: The existing status report already exposes approval, manual review, update, and
  closure queues. Adding deterministic file-backed answer/comment visibility turns the repo into the
  current review surface without pretending to auto-approve anything.
- **Alternatives considered**:
  - Keep only the current five categories: rejected because pending answers and comments would stay
    buried inside Markdown files and not appear in the main status queue.
  - Add a separate tool instead of extending `doc_workflow.py`: rejected because it would duplicate
    the repo’s existing explicit docs gate surface.

## Decision 3: Treat `.specify/templates/*` edits as conservative, policy-bearing changes

- **Decision**: Update templates and workflow docs together, and require docs-tool test coverage for
  status-report behavior changes. Keep repo-local template behavior close to upstream Spec Kit
  defaults unless the user explicitly approves a deviation.
- **Rationale**: Template edits guide future LLM behavior. If they change how unknowns or approvals
  are handled, they act like workflow policy and must not drift without matching docs or tests.
- **Alternatives considered**:
  - Allow standalone template tweaks: rejected because subtle wording changes can create silent
    policy drift.
  - Move all guardrails into AGENTS instructions only: rejected because template users and repo docs
    also need to see the guardrails.

## Decision 4: Use frontmatter-first metadata with lean-by-type rules

- **Decision**: Workflow docs should use YAML frontmatter as the canonical metadata surface.
  Feature-local docs, managed docs, skill docs, and command docs share one `docmeta` model, but
  skills and command docs keep their existing top-level keys such as `name`, `description`,
  `compatibility`, and `metadata`.
- **Rationale**: This keeps metadata conventional, machine-readable, and truthful without forcing
  upstream-style skill and command docs into duplicated fields or custom rendered header systems.
- **Alternatives considered**:
  - Keep rendered `DOCMETA` headers as the long-term contract: rejected because they are less
    conventional and depend on repo-specific presentation choices.
  - Reuse registry-managed frontmatter values for feature-local docs: rejected because feature-local
    docs are not tracked by the registry and should not claim registry-managed review state.
  - Leave feature-local docs as free-form Markdown: rejected because the workflow becomes too easy
    to misread or mutate inconsistently.

## Decision 5: Name the next big backlog items as separate planned features, with `suppressor` next

- **Decision**: Convert the major open governance backlog into named follow-on features:
  `001-docs-governance-hardening` now, followed by `002-suppressor-journalling-policy`,
  `003-suppressor-operator-contract`, `004-biblio-boundary-cut`, and `005-biblio-proof-rule`.
- **Rationale**: This preserves narrow scope, makes sequencing explicit, and turns abstract backlog
  bullets into clear next-step work packets while respecting the newly stated priority that
  `suppressor` work should go next.
- **Alternatives considered**:
  - Leave backlog items as prose bullets in `tasks.md`: rejected because they remain too ambiguous
    to start confidently.
  - Start all follow-on specs in the same feature: rejected because it would mix planning horizons
    and make the current hardening feature too broad.

## Decision 6: Ignore marker examples when they appear only as documentation

- **Decision**: The docs workflow should treat unresolved-marker detection as content-aware enough
  to ignore marker syntax that appears only inside fenced code blocks, inline code spans, or
  similar contract examples.
- **Rationale**: The status contract must be able to document the marker policy without permanently
  failing the docs gate. Reporting the contract file as unresolved simply for listing `TODO`,
  `TBD`, or similar tokens makes the workflow self-contradictory.
- **Alternatives considered**:
  - Ban literal marker examples in docs: rejected because the contract should show the real syntax
    it governs.
  - Keep raw substring detection: rejected because it creates false positives and weakens trust in
    `speckit.docs`.

## Decision 7: Keep registry-managed review state authoritative, with graceful fallback when no active feature exists

- **Decision**: `approval_needed` and `manual_review_needed` remain derived from
  `.specify/doc-registry.json`, while feature-local `questions.md` and `review-queue.md` only add
  scoped answer, comment, or update queues. If no active feature is set, feature-local queues are
  treated as empty rather than as an error.
- **Rationale**: This prevents feature-local docs from silently redefining durable review state,
  while still letting the workflow surface active follow-up work. It also keeps the status command
  usable outside active feature work.
- **Alternatives considered**:
  - Let feature-local queues override registry review state: rejected because it would blur the line
    between durable managed-doc state and scoped feature review requests.
  - Fail status when `.specify/feature.json` is absent: rejected because managed-doc governance must
    remain visible even when no feature is active.

## Decision 8: Treat `closure_needed` as closure-ready state, not as a synonym for completed tasks

- **Decision**: `closure_needed` should only appear when the active feature has completed tasks and
  no pending feature-local queue items remain that still require approval, comment, answer, manual
  review, or update work for that feature.
- **Rationale**: The analysis found that the current implementation can report both "still under
  review" and "needs closure" at the same time. That weakens status clarity and makes closure look
  more final than it really is.
- **Alternatives considered**:
  - Keep `closure_needed` as a pure pointer-cleanup reminder: rejected because it overloads
    "closure" with a state that is not actually closure-ready.
  - Remove `closure_needed` entirely: rejected because maintainers still need an explicit reminder
    to clear or move `.specify/feature.json` once a feature is truly done.

## Decision 9: Add direct proof tests for the documented fallback and precedence rules

- **Decision**: The next implementation slice should add explicit tests for missing
  `.specify/feature.json`, for registry-versus-feature-queue precedence, and for closure suppression
  while pending feature-local review work remains.
- **Rationale**: The analysis found that the current test suite covers many regression paths, but it
  does not directly prove all policy edges that the spec and contract now claim.
- **Alternatives considered**:
  - Rely on indirect coverage from broader status tests: rejected because the missing edges are
    exactly the kind of policy regressions that become ambiguous later.
  - Downgrade the contract instead of adding tests: rejected because the documented behavior is still
    the intended behavior.

## Decision 10: Keep git landing as documented close-out discipline, not as a new status category

- **Decision**: Distinguish "implemented in the working tree" from "landed in repo history" in the
  docs and close-out checklist, but do not add a new git-derived status category to
  `tools/doc_workflow.py` in this feature.
- **Rationale**: The analysis correctly noted that passing tests in a dirty or partly untracked tree
  is not the same as having landed the work. That distinction matters, but the deterministic docs
  tool should stay focused on file-backed review state rather than expanding into a general VCS
  auditor.
- **Alternatives considered**:
  - Add git cleanliness and tracking checks to the docs status tool now: rejected because it widens
    scope and mixes file-governance logic with repository-history policy.
  - Ignore landing state completely: rejected because the analysis showed that maintainers need the
    distinction to avoid overclaiming completion.

## Decision 11: Keep feature `Status: Draft` until review and approval work is closed explicitly

- **Decision**: Treat feature-document `Status: Draft` as compatible with completed implementation
  tasks when approvals or review comments are still open; only move beyond that state once the
  review queue and durable approvals are cleared explicitly.
- **Rationale**: The analysis flagged the current `Draft` label as confusing only because the
  lifecycle was implicit. Making the lifecycle explicit is enough; implementation completeness does
  not automatically imply approval or closure.
- **Alternatives considered**:
  - Auto-promote the feature spec status when tasks complete: rejected because task completion alone
    does not prove review completion.
  - Leave the lifecycle undocumented: rejected because it keeps the same ambiguity in place.

## Decision 12: Keep docs metadata sync and feature generation as separate write surfaces

- **Decision**: Broad metadata migration and feature-artifact generation remain separate workflows.
  Docs sync may rewrite frontmatter, but it must support preview and explicit scope selection;
  feature-generation scripts must not be treated as generic docs-maintenance commands.
- **Rationale**: The repo has already demonstrated that broad metadata rewrites and plan generation
  can both touch `plan.md`, but they fail in different ways and need different guardrails.
- **Alternatives considered**:
  - Treat all Markdown-writing workflows as one undifferentiated write surface: rejected because
    maintainers then cannot tell which command is allowed to touch which artifact family.
  - Keep repo-wide sync but hide scope from operators: rejected because it removes the inspectable
    path needed before large mutations.

## Decision 13: Preserve existing `plan.md` by default and require `--force` for overwrite

- **Decision**: `.specify/scripts/bash/setup-plan.sh` should preserve an existing non-empty
  `plan.md` unless the maintainer explicitly passes `--force`. The script should also surface which
  action it took so wrappers and tests can inspect the outcome.
- **Rationale**: The repo already hit a real failure mode where a filled plan was replaced with the
  raw template. Default-preserve plus explicit force matches the documented guardrail and keeps the
  workflow honest.
- **Alternatives considered**:
  - Always copy the template and rely on the same run to refill it: rejected because interruptions
    leave the template overwrite behind.
  - Block all future overwrite paths entirely: rejected because maintainers still need a deliberate
    way to reset a plan when they truly intend to do so.

## Decision 14: Record managed-governance review state through the registry, not Markdown edits

- **Decision**: Review and approval changes for managed governance docs stay durable only when they
  are recorded in `.specify/doc-registry.json` and synced back into frontmatter. Manual edits to
  `docmeta.review` inside managed Markdown may reflect real human intent, but they do not count as
  the authoritative review state.
- **Rationale**: The constitution already treats registry-backed metadata as the source of truth for
  managed docs. Allowing Markdown-only review labels to count would make the docs gate lie about
  what has actually been approved and would weaken the whole frontmatter-sync contract.
- **Alternatives considered**:
  - Treat matching Markdown edits as equivalent to registry edits: rejected because two writable
    sources of truth invite drift and silent disagreement.
  - Ban human review on managed docs entirely: rejected because the problem is where the review
    state is recorded, not whether review can happen.

## Decision 15: Move unresolved standing-governance review comments out of maintained docs

- **Decision**: Inline TODO-style review comments must not remain inside maintained standing
  governance docs after review input has been captured. Unresolved repo-level points move into
  `specs/000-repo-governance/research.md`, a feature-local review file, or a new scoped feature
  spec until they are resolved.
- **Rationale**: Maintained governance docs should describe current accepted policy, not mix policy
  with unresolved editorial or design debate. Leaving inline TODO comments in accepted docs blurs
  current behavior and future direction, and it also poisons the unresolved-marker gate.
- **Alternatives considered**:
  - Keep inline TODO review comments as a lightweight backlog: rejected because they make accepted
    governance docs self-contradictory.
  - Delete unresolved review comments without moving them anywhere: rejected because the feedback is
    real and should remain inspectable until resolved.

## Decision 16: Keep one authoritative temporary review surface per scope

- **Decision**: Repo-level unresolved governance questions live in
  `specs/000-repo-governance/research.md`. Feature-scoped human input lives in that feature's
  `questions.md` or `review-queue.md`. Resolved items should be cleaned out of the temporary
  surface once durable docs are updated.
- **Rationale**: The repo now has multiple temporary Markdown surfaces for human input. They are
  useful only if each one has a clear scope. Otherwise the same unresolved point can sit in several
  files and nobody can tell which one is authoritative.
- **Alternatives considered**:
  - Collapse all temporary review input into one repo-wide file: rejected because feature-scoped
    review would pollute standing governance.
  - Allow the same unresolved point to remain in several files for convenience: rejected because it
    recreates duplication and stale-state drift.

## Decision 17: Preserve traceability when feature review becomes durable governance

- **Decision**: When a feature review or implementation produces a durable governance lesson, the
  updated maintained doc or supporting evidence should preserve traceability back to the originating
  feature, decision, or review source when that materially helps later audit or git-history lookup.
- **Rationale**: Once review feedback is folded into durable docs, the repo should not lose the
  ability to answer "where did this rule come from?" A light traceability link keeps the workflow
  auditable without forcing every durable doc to carry excessive historical commentary.
- **Alternatives considered**:
  - Strip all review provenance once a decision is folded into governance: rejected because later
    audits lose the path back to the originating context.
  - Keep all traceability only in git history: rejected because some future reviewers need a faster,
    human-facing clue about the origin of a durable rule.
