---
docmeta:
  status: working
  review: feature-local
  purpose: Stable contract for docs workflow status queues and frontmatter metadata behavior.
  source: document-local metadata
  feature: '[spec.md](../spec.md)'
---

# Contract: Docs Status Report And File-Backed Question Queues


## Status Report Output

`python3 tools/doc_workflow.py status` and `python3 tools/doc_workflow.py status --json` expose the
deterministic docs-review queue.

### Required categories

- `approval_needed`
- `manual_review_needed`
- `answer_needed`
- `comment_requested`
- `update_needed`
- `closure_needed`
- `registry_or_link_errors`

## Managed Doc Review Semantics

Managed docs get their metadata from `.specify/doc-registry.json`.

- `client-input-derived` marks provenance from direct client input.
- `approved` or `client-confirmed` closes the approval queue for a `client-input-derived` doc.
- `unreviewed` marks a managed doc that still needs manual review.
- `reviewed`, `approved`, `client-confirmed`, `code-reviewed`, and `operator-verified` count as
  terminal review outcomes for the manual-review queue.
- Multiple labels may coexist. The workflow must derive queue state from the combination rather
  than treating each label as an isolated pending flag.

## Managed Governance Review Capture

- Review or approval changes on managed governance docs become durable only when
  `.specify/doc-registry.json` is updated and the managed frontmatter is synced from that registry.
- Manual edits to managed-doc `docmeta.review` do not count as durable review evidence.
- Feature-local queue files may request alignment or follow-up work on managed docs, but they do
  not replace the registry as the source of truth for durable managed review state.
- Unresolved review comments on maintained standing-governance docs must move into
  `specs/000-repo-governance/research.md`, a feature-local review file, or a follow-on feature
  spec. They should not remain as inline TODO markers in the maintained doc.

## File-Backed Question Contract

Feature-local `questions.md` files may contain entries in this form:

```markdown
### Q001: Short question title

- Status: pending-answer
- Owner: client
- Default: yes
- Description: ...
- Proposed Solution: ...
- Why it matters: ...
- Related Docs: ...
- Answer: ...
```

Supported question statuses:

- `pending-answer` -> reported as `answer_needed`
- `pending-comment` -> reported as `comment_requested`
- `answered` -> not reported
- `commented` -> not reported
- `resolved` -> not reported

## Review Queue Contract

Feature-local `review-queue.md` files are human-facing summaries. They may reuse the same status
language as the status report, but the tool’s deterministic reporting depends only on the documented
queue markers it knows how to parse.

Queue rows use a Markdown table with:

- `RQ###` identifier
- canonical queue `status`
- `subject` as a Markdown link or question reference
- `owner`
- `note`

Action-needed rows in `review-queue.md` may be surfaced by the status tool for:

- `answer_needed`
- `comment_requested`
- `update_needed`

## Temporary Review Surface Contract

- Repo-level unresolved governance questions belong in `specs/000-repo-governance/research.md`.
- Feature-scoped human input belongs in the active feature's `questions.md` or `review-queue.md`.
- Resolved items should be cleaned out of the temporary surface once the durable docs are updated.
- When durable governance lessons are lifted from a feature review, the repo should preserve
  traceability to the originating feature or decision source when that materially helps later audit.

## Queue Precedence And Fallback

- If `.specify/feature.json` is absent or points to no active feature, managed-doc queue categories
  still report normally and feature-local queue categories remain empty.
- If feature-local queue files contain both pending and terminal items, only pending items are
  surfaced in the status report.
- If a feature-local queue entry implies a different durable review state than
  `.specify/doc-registry.json`, the registry remains authoritative for `approval_needed` and
  `manual_review_needed`. Feature-local queue files may request alignment work, but they do not
  override managed-doc review state on their own.

## Closure Semantics

- `closure_needed` is a closure-ready reminder, not a synonym for "tasks are complete".
- The active feature may emit `closure_needed` only when:
  - `tasks.md` is fully complete for that feature
  - no pending `questions.md` items remain
  - no pending `review-queue.md` rows remain in actionable states
- Feature-local `review-queue.md` rows may include `approval_needed` or `manual_review_needed` as
  closure blockers, but they do not replace the registry as the durable source of those review
  states.
- A feature may therefore be implemented and still remain review-open. In that state, the status
  report should show the open review queues and suppress `closure_needed`.

## Metadata Maintenance Contract

`python3 tools/doc_workflow.py sync` and `python3 tools/doc_status.py sync` are the explicit
metadata-maintenance entrypoints.

- `--dry-run` previews pending rewrites without mutating files.
- `--scope managed` limits sync to registry-managed docs.
- `--scope active-feature` limits sync to Markdown under the active feature directory.
- `--scope all` is the broad repo-wide rewrite path.
- YAML frontmatter is authoritative whenever both frontmatter and legacy `DOCMETA` are present.
- Legacy `DOCMETA` may still be parsed during migration, but `DOCMETA`-only workflow docs are not
  compliant with the maintained frontmatter contract.

These controls exist so maintainers can inspect or narrow rewrites before a broad mutation run.

## Plan Setup Guardrail

`.specify/scripts/bash/setup-plan.sh` is a feature-artifact generation step, not a generic
docs-maintenance command.

- If the target `plan.md` already exists and is non-empty, the script preserves it by default.
- Overwrite requires an explicit action such as `--force`.
- Script output includes `PLAN_ACTION` so callers can tell whether the plan was preserved or the
  template was copied.

## Delivery-State Language

- Passing `python3 tools/doc_workflow.py all` proves the current docs workflow passes in the working
  tree.
- It does not, by itself, prove that the feature is approved, closed, or landed in git history.
- Feature docs should therefore keep lifecycle wording explicit:
  - implementation complete
  - review still open
  - closure-ready
  - landed in repo history
- The current feature spec may remain `Draft` while review or approval work remains pending.

## Unresolved Marker Policy

The docs workflow should detect unresolved markers case-insensitively in actionable prose, while
ignoring the same marker syntax when it appears only inside inline code or fenced code blocks.

Canonical marker families include:

- `TODO(`
- `<!-- TODO:`
- `TBD`
- `[NEEDS CLARIFICATION`
- `: not decided:`

The status report should therefore treat this as reportable:

```markdown
Pending follow-up remains here. <!-- TODO: tighten wording -->
```

And this as documentation only, not reportable:

```markdown
Use marker syntax such as `<!-- TODO:` or `TBD` only for real unresolved items.
```

## Non-Goals

- The status report is not an approval engine.
- File-backed queue items do not automatically mutate managed-doc review labels in
  `.specify/doc-registry.json`.
