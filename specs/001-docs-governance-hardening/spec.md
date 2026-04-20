---
docmeta:
  status: draft
  review: feature-local
  purpose: Feature specification and acceptance criteria for docs governance hardening.
  source: document-local metadata
---

# Feature Specification: Docs Governance Hardening


## Clarifications

### Session 2026-04-19

- Q: Should the docs status tool expose dedicated `answer_needed` and `comment_requested` categories? → A: Yes. They should be deterministic, file-based, and visible from the repo instead of chat-only context.
- Q: How should `.specify` template and workflow overrides be handled? → A: Conservatively. Repo-local workflow defaults should stay close to upstream Spec Kit guidance unless the user explicitly approves a deviation, and policy-bearing changes should land with matching docs or tests.
- Q: Should feature-local workflow docs use a stable local schema and metadata header? → A: Yes. `questions.md`, `review-queue.md`, and related workflow docs should state their purpose, status, connected docs, and review handling consistently.
- Q: Which planned feature area should come next after `001-docs-governance-hardening`? → A: `suppressor` work should be prioritized next, ahead of the `biblio` follow-ons.
- Q: Should managed docs and feature-local docs share one common metadata shape even though their metadata does not come from the same source? → A: Yes. Use one broad technical metadata schema across Markdown docs and keep provenance truthful instead of pretending every doc is registry-managed.
- Q: Should preview-specific compactness drive the canonical metadata contract? → A: No. Compact presentation may be useful, but the authoritative contract must stay conventional, frontmatter-first, and independent of custom preview behavior.
- Q: Should token economy be an explicit aim of this spec-driven workflow even when it affects technical notation and status surfaces? → A: Yes. The workflow should become materially more compact, but only through stable, documented shorthand and expandable full-fidelity detail so quality and grounding do not drop.

### Session 2026-04-20

- Q: Is the real safety problem the same as the docs metadata rewrite? → A: No. Repo-wide docs metadata sync is one broad write surface, but the destructive replacement of `plan.md` came from the planning setup workflow copying the template over the existing file. The spec must address both without conflating them.
- Q: Should the canonical docs metadata contract now be frontmatter-first instead of a rendered collapsible header system? → A: Yes. YAML frontmatter is the authoritative metadata surface; legacy `DOCMETA` remains compatibility input only, and conventional Markdown behavior is preferred over custom preview-only rendering tricks.
- Q: Should workflow generation and metadata migration be allowed to overwrite filled artifacts silently? → A: No. Existing filled artifacts such as `plan.md` must be preserved unless a maintainer explicitly requests an overwrite, and broad metadata rewrites must offer an inspectable or narrower execution path.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable `speckit.docs` Status Workflow (Priority: P1)

As the repo owner, I need `speckit.docs` and `python3 tools/doc_workflow.py status` to reflect
the actual review state of repo docs and active-feature workflow files so I can trust the output as
the current action surface.

**Why this priority**: The current docs workflow is the highest-priority broken surface. If it does
not reflect the true state of approvals, comments, TODOs, or queue files, the rest of the workflow
stops being trustworthy.

**Independent Test**: Run the docs status workflow and inspect the feature-local review files; the
required actions and their statuses are visible without rereading chat history, and the output no
longer silently drops real states that are already present in repo files.

**Acceptance Scenarios**:

1. **Given** current managed docs and an active feature, **When** I run the repo docs status
   workflow, **Then** I see a deterministic queue of docs that need approval, manual review,
   comment, answer, or update, based on documented registry and feature-file semantics.
2. **Given** a feature question has already been answered or commented in repo files, **When** I run
   the docs status workflow, **Then** that item is not incorrectly reported as still pending.
3. **Given** unresolved TODO markers are present in tracked docs, **When** I run the docs status
   workflow, **Then** they are surfaced consistently regardless of casing or the exact tracked doc.

---

### User Story 2 - Safe Frontmatter Metadata And Guardrails (Priority: P2)

As the repo owner, I need maintained Markdown docs and feature-generation workflows to use one
conservative frontmatter-first metadata contract with explicit overwrite guardrails so metadata
migration does not silently replace filled artifacts or drift into ad hoc schemas.

**Why this priority**: The current safety problem is not just inconsistent formatting. The repo now
has two separate write surfaces that can be confused with each other: broad metadata migration and
feature-artifact generation. Without explicit guardrails, maintainers can lose real plan content or
misread what a docs command is allowed to rewrite.

**Independent Test**: Run the metadata sync path and the planning setup path against representative
existing docs; frontmatter is augmented truthfully, legacy metadata is tolerated as migration input,
and an existing filled `plan.md` is not silently replaced.

**Acceptance Scenarios**:

1. **Given** a repo doc still uses legacy `DOCMETA` or partial frontmatter, **When** a maintainer
   runs the metadata sync workflow, **Then** the doc is augmented into the canonical frontmatter
   schema without losing its substantive body content or type-specific frontmatter keys.
2. **Given** a managed doc and a feature-local doc need different metadata authorities, **When**
   both are migrated or linted, **Then** they share one frontmatter-based schema while remaining
   honest about whether durable review state comes from `.specify/doc-registry.json` or from local
   feature context.
3. **Given** a maintainer runs the planning setup workflow against an existing feature with a filled
   `plan.md`, **When** no explicit overwrite was requested, **Then** the current plan content is
   preserved instead of being replaced by the template.
4. **Given** a maintainer wants to inspect or limit a broad metadata rewrite, **When** they invoke
   the docs-maintenance workflow, **Then** they have a safe way to preview or narrow the write scope
   instead of being forced into an unbounded repo-wide rewrite.

### User Story 3 - Token-Efficient Grounded Workflow Surfaces (Priority: P3)

As the repo owner, I need the spec-driven workflow to use fewer tokens without losing grounding,
reviewability, or diagnostic usefulness so human and agent work stays cheaper and less noisy without
becoming vague.

**Why this priority**: Token economy is now an explicit workflow goal. If the repo keeps verbose
technical repetition everywhere, the workflow becomes more expensive and harder to scan, but if it
compresses information carelessly it becomes untrustworthy.

**Independent Test**: Read representative status outputs, doc headers, review queues, and workflow
guidance; recurring technical content is more compact, stable shorthand is documented, and full
meaning remains recoverable without rereading chat or reverse-engineering the notation.

**Acceptance Scenarios**:

1. **Given** a repeated technical pattern such as a status, review state, path family, or command
   family, **When** the workflow presents it in a compact surface, **Then** the compact form is
   stable, documented, and still maps back to one unambiguous meaning.
2. **Given** a maintainer needs the full detail behind a compact status or notation, **When** they
   inspect the related docs or expanded view, **Then** they can recover the full meaning without
   hidden assumptions or chat-only context.
3. **Given** the workflow shortens logs or repeated technical wording, **When** a failure or review
   decision needs investigation, **Then** the compact presentation still preserves the critical
   identifiers, links, and distinctions needed to debug or review safely.

---

### User Story 4 - Prioritized Follow-On Feature Roadmap (Priority: P4)

As the repo owner, I need the next major governance backlog chunks turned into named, prioritized
follow-on features so I can move to the next spec deliberately instead of inferring the sequence from
TODO comments.

**Why this priority**: The current backlog now has enough direction that the next feature order
should be encoded explicitly, especially the decision that `suppressor` work is next.

**Independent Test**: Read the updated governance docs and feature plan; the next scoped features are
named, ordered, and justified without relying on inline TODOs.

**Acceptance Scenarios**:

1. **Given** the current repo-governance backlog, **When** I read the updated roadmap and planning
   docs, **Then** the `suppressor` and `biblio` follow-ups are described as separate planned
   features with explicit priority order and implementation intent.
2. **Given** a maintainer starts the next non-trivial change after `001`, **When** they consult the
   updated governance docs, **Then** they can identify the next feature directly instead of relying
   on an inline comment.

### Edge Cases

- If there is no active feature pointer, the status workflow still reports managed-doc queues and
  treats feature-local answer, comment, and update queues as empty instead of failing.
- If an active feature has pending file-backed questions, comments, or updates but no managed-doc
  review backlog, the status workflow still surfaces those feature-local queues.
- If `questions.md` or `review-queue.md` mixes pending and terminal items, only the pending items
  are surfaced; `answered`, `commented`, and `resolved` remain visible in the file but not in the
  pending queue.
- If a managed doc uses additive labels such as `client-input-derived, approved`, queue state is
  derived from the label combination and the doc is not falsely reported as still pending approval.
- If registry-managed review state and a feature-local queue disagree, the registry remains the
  source of truth for durable approval/manual-review status and the feature queue can only request
  follow-up review or alignment work.
- If a document does not need fields such as `Feature`, `Connected Docs`, `Branch`, or `Input`, the
  shared frontmatter schema still stays concise without placeholder keys or misleading empty values.
- If a document needs extra context such as `Feature`, `Connected Docs`, `Branch`, `Created`, or
  `Input`, those optional fields fit inside the same frontmatter schema without implying false
  registry management.
- If a skill or command doc already uses upstream-style top-level frontmatter such as `name`,
  `description`, `compatibility`, or `metadata`, migration preserves those keys and augments only
  the missing repo-governance metadata semantics.
- If a document contains both frontmatter and legacy `DOCMETA`, frontmatter remains authoritative
  and legacy metadata is treated as compatibility-only input during migration.
- If a maintainer runs plan setup against a feature that already has a filled `plan.md`, the
  workflow must stop, warn, or require an explicit overwrite action instead of silently replacing
  the artifact.
- If a docs-maintenance command would rewrite a broad set of Markdown files, the maintainer must be
  able to inspect or constrain the rewrite scope before the tool mutates files.
- If the workflow introduces shorthand, codes, wrappers, or compact notation for token economy, the
  meaning must stay stable and documented rather than becoming repo folklore.
- If compact logs omit repeated wording, they must still preserve the identifiers and references
  needed to recover full context during review or debugging.
- If numeric or abbreviated codes are used, maintainers must be able to resolve them quickly without
  guessing.
- Unresolved TODO-style markers are matched case-insensitively, but marker syntax shown only inside
  inline code or fenced examples is treated as documentation rather than live unresolved work.
- `specs/000-repo-governance/` remains durable standing guidance, while `specs/NNN-feature-name/`
  remains scoped feature work; generators and workflow tooling must preserve that distinction.
- If a template or workflow-policy change alters maintainer expectations without matching human-doc
  updates or automated coverage, the feature remains incomplete rather than silently accepted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repo MUST provide a file-based review and question workflow for the active feature
  so maintainers can track pending approvals, manual review, comments, updates, and direct answers
  outside chat-only context.
- **FR-002**: The docs status workflow MUST remain deterministic and MUST surface the current queue
  categories for managed docs, plus supported file-based queue states from the active feature using a
  documented schema for pending and terminal states, including cases where only managed-doc queues
  exist, only feature-local queues exist, or no active feature is set.
- **FR-003**: The governance docs MUST name the major unresolved backlog chunks as separate planned
  features instead of leaving them only as vague future-work bullets.
- **FR-004**: The repo MUST preserve the distinction between `specs/000-repo-governance/` as
  durable standing guidance and `specs/NNN-feature-name/` as scoped feature work.
- **FR-005**: `.specify` templates and workflow docs MUST require explicit unknown handling and MUST
  discourage silent policy invention by LLMs.
- **FR-006**: If a human answer or approval is needed during feature work, the workflow MUST direct
  maintainers to record that need in a file under the feature directory instead of relying on chat
  alone.
- **FR-007**: Policy-bearing updates to docs tooling or `.specify` templates MUST land with updated
  workflow guidance and automated coverage where practical, or remain incomplete feature work.
- **FR-008**: Feature-local workflow docs such as `questions.md`, `review-queue.md`, and status
  contracts MUST use the shared technical metadata-header schema and MUST state purpose, current
  status, connected docs, and review handling truthfully.
- **FR-009**: `speckit.docs` MUST interpret canonical review-label semantics for managed docs
  and canonical state semantics for `questions.md` and `review-queue.md`, including terminal states
  that should no longer be reported as pending, while leaving durable approval/manual-review status
  anchored to the managed-doc registry.
- **FR-010**: The docs workflow MUST detect unresolved TODO-style markers case-insensitively across
  managed docs and active feature docs.
- **FR-011**: The docs workflow MUST distinguish actual unresolved markers from documentation about
  those markers, so fenced examples, inline code, and schema contracts do not report false
  `update_needed` items by merely naming the marker syntax.
- **FR-012**: Managed-doc review handling MUST support additive review labels so provenance labels
  such as `client-input-derived` can coexist with terminal review labels such as `approved` or
  `reviewed` without being misreported as still pending.
- **FR-013**: The updated governance roadmap MUST encode that `suppressor` follow-on work is the
  next planned feature area after `001-docs-governance-hardening`.
- **FR-014**: Managed docs and feature-local docs that participate in this workflow MUST share one
  common frontmatter-based metadata schema at the top of the Markdown file instead of separate
  rendered header systems.
- **FR-015**: The shared frontmatter schema MUST support a core field set for document identity and
  review context, plus optional fields such as feature link, connected docs, branch/date, and input
  provenance, without requiring irrelevant fields on every document.
- **FR-016**: The shared frontmatter schema MUST remain readable and truthful in conventional
  Markdown tooling and MUST not depend on custom HTML callouts, disclosure widgets, or repo-local
  CSS for correctness.
- **FR-017**: The shared metadata schema MUST keep provenance explicit, so managed docs can point at
  `.specify/doc-registry.json` while feature-local docs can point at their local feature context
  without falsely claiming registry-managed review state.
- **FR-018**: Docs metadata sync MUST augment existing docs conservatively, preserving non-metadata
  document content and existing type-specific frontmatter keys while migrating legacy metadata into
  the canonical frontmatter schema.
- **FR-019**: Feature-generation and setup workflows MUST NOT overwrite an existing filled artifact
  such as `plan.md` without an explicit maintainer-approved overwrite action.
- **FR-020**: Docs-maintenance tooling MUST provide a safe way to inspect or narrow metadata
  rewrites before applying broad Markdown mutations, so maintainers can distinguish managed-doc sync
  from repo-wide migration behavior.
- **FR-021**: The spec-driven workflow MUST treat token economy as an explicit design goal for
  repeated technical surfaces such as headers, queues, status output, logs, and recurring command or
  notation patterns.
- **FR-022**: Compact workflow surfaces MUST preserve grounding and quality by keeping critical
  identifiers, links, review distinctions, and expansion paths intact.
- **FR-023**: Any shorthand, code, abbreviation, wrapper, or compact notation adopted for token
  economy MUST have a stable documented meaning and MUST not rely on informal tribal knowledge.
- **FR-024**: The workflow MUST provide a lossless path from compact notation or compact output to
  full detail, whether through legends, linked docs, expansion affordances, or deterministic mapping
  rules.
- **FR-025**: Token-economy changes MUST reduce unnecessary repetition without compressing away
  safety-relevant differences such as approval state, review state, unresolved status, error class,
  or target path.
- **FR-026**: The repo MAY use wrappers, shorthands, structured codes, or shorter technical
  notations to achieve token economy, but the spec MUST evaluate them by clarity and recoverability
  rather than by brevity alone.

### Key Entities *(include if feature involves data)*

- **Review Queue Entry**: A file-backed item describing a path or decision that currently needs a
  specific action such as approval, comment, update, or answer.
- **Question Entry**: A structured feature-local item with an identifier, owner, status, default
  recommendation or proposed solution, and related docs.
- **Planned Feature Chunk**: A named follow-on feature derived from governance backlog items, with a
  scope statement, rationale, and sequencing note.
- **Guardrail Rule**: A documented workflow or template rule that prevents silent policy invention
  or unintended edits across standing governance docs and active feature docs.
- **Managed Doc Review State**: The additive set of review labels in `.specify/doc-registry.json`
  that determines whether a managed doc still needs approval or manual review.
- **Unified Doc Metadata**: A shared frontmatter-based metadata block that can describe managed docs
  and feature-local docs using one schema while keeping the source of truth explicit.
- **Metadata Rewrite Scope**: The set of Markdown files a docs-maintenance command is allowed to
  inspect, lint, preview, or rewrite in one run.
- **Artifact Overwrite Guardrail**: A workflow rule that blocks or requires explicit approval for
  replacing an existing filled feature artifact such as `plan.md`.
- **Compact Workflow Surface**: A deliberately shortened workflow artifact such as a status output,
  header, queue row, or log line that reduces repeated technical wording while preserving meaning.
- **Shorthand Mapping Rule**: A documented relationship between a compact code, notation, or wrapper
  form and its full canonical meaning.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running `python3 tools/doc_workflow.py status` after this feature lands emits a
  deterministic set of queue categories that reflects managed-doc review labels plus supported
  `questions.md` and `review-queue.md` states from the active feature.
- **SC-002**: Question entries marked `answered`, `commented`, or `resolved` are no longer surfaced
  as pending, while still-pending answers or comments remain visible.
- **SC-003**: Unresolved TODO-style markers in tracked docs are surfaced consistently regardless of
  case, no unresolved TODO markers remain in the updated docs shipped by this feature, and marker
  syntax mentioned only as documentation examples does not create false positives.
- **SC-004**: The next repo-governance roadmap after `001` explicitly prioritizes `suppressor`
  follow-on features before the `biblio` follow-ons.
- **SC-005**: The `.specify` template, registry-review-schema, and docs-workflow changes pass the
  docs-tool unit tests and the explicit docs gate without registry drift or broken queue semantics.
- **SC-006**: Representative managed docs, feature-local docs, skill docs, and command docs expose
  the same frontmatter-based metadata semantics with truthful provenance, and no tracked doc
  participating in the workflow remains legacy-`DOCMETA`-only.
- **SC-007**: Existing top-level frontmatter keys already used by skill and command docs remain
  intact after migration, while managed docs still derive authoritative review state from
  `.specify/doc-registry.json`.
- **SC-008**: Running the metadata-maintenance workflow on representative existing docs and running
  planning setup against a representative filled feature preserves non-metadata prose and does not
  silently replace an existing `plan.md`.
- **SC-009**: Representative workflow surfaces that were previously verbose become materially more
  compact while preserving the required identifiers, links, and review distinctions needed for safe
  use.
- **SC-010**: Maintainers can resolve representative compact notations or status codes back to their
  full meaning in one documented step, without relying on chat memory.
- **SC-011**: Token-economy improvements do not reduce docs-gate coverage or remove the information
  needed to distinguish approval, manual review, comment, answer, update, and closure states.

## Assumptions

- Existing managed-doc review labels remain the source of truth for approval and manual-review
  status on durable human docs.
- File-based question and review queues live under feature directories unless the work becomes
  standing repo policy.
- A shared frontmatter schema does not imply that all docs share the same workflow authority or
  review source of truth.
- Conventional Markdown tooling may show YAML frontmatter plainly, and that is acceptable as long as
  the metadata stays truthful, conventional, and machine-readable.
- Legacy `DOCMETA` may remain parseable during migration, but YAML frontmatter is the authoritative
  metadata surface once both are present.
- The repo can reduce repeated technical wording meaningfully through shared notation, compact
  surfaces, or wrappers without needing to sacrifice explicit source-of-truth rules.
- The docs workflow remains advisory and review-oriented; it does not auto-approve or auto-close
  human review steps.
- Repo-local overrides of upstream Spec Kit defaults should stay conservative and require explicit
  user confirmation when they materially shift workflow policy.
- Safety guardrails may refuse a write or require an explicit overwrite action rather than guessing
  maintainer intent.
- The first pass should harden the workflow and documentation surface now, while leaving room for
  deeper architecture work in later scoped features.
- Optional metadata fields may be omitted when they do not apply, as long as the shared frontmatter
  shape remains recognizable and truthful.

## Documentation Impact

- Update `specs/README.md` to document optional feature-local `questions.md`, `review-queue.md`,
  and `checklists/`.
- Update `specs/000-repo-governance/quickstart.md`, `research.md`, and `tasks.md` to reflect the
  current workflow, the user's recorded answers, and the explicit follow-on feature order.
- Update `README.md` and `.specify/doc-registry.json` so the docs gate and human review states stay
  aligned with the intended workflow.
- Update `.specify/extensions/docs/README.md` and
  `.specify/extensions/docs/commands/speckit.docs.md` to document the stricter status queue.
- Update managed docs, feature-local workflow docs, and any emitting templates or sync tooling so
  they all use the shared frontmatter metadata schema.
- Update planning setup guidance and the plan-generation workflow so existing filled artifacts are
  not overwritten silently.
- Update workflow docs, status/report contracts, and any related tooling surfaces so token-economy
  conventions are explicit, grounded, and recoverable.
- Update `.specify/templates/spec-template.md` and `.specify/templates/plan-template.md` to direct
  unresolved human questions into files instead of invented policy.
- Update `tools/doc_status.py`, `tools/doc_workflow.py`, tests, and the explicit docs gate behavior
  so frontmatter migration, queue parsing, review-label semantics, TODO detection, rewrite scope,
  and overwrite guardrails work as intended.
