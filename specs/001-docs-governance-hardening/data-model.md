---
docmeta:
  status: working
  review: feature-local
  purpose: Data entities and schema notes for docs governance hardening.
  source: document-local metadata
  feature: '[spec.md](./spec.md)'
---

# Data Model: Docs Governance Hardening


## Entities

### Review Queue Entry

- **Purpose**: Represents a document, decision, or question that currently requires a specific human
  action.
- **Fields**:
  - `id`: stable identifier such as `RQ001`
  - `status`: one of `approval_needed`, `manual_review_needed`, `answer_needed`,
    `comment_requested`, `update_needed`, or `resolved`
  - `owner`: who needs to act, such as `client`, `maintainer`, or `reviewer`
  - `subject`: markdown link or question identifier pointing at the target of the action
  - `note`: short explanation of why the item is in the queue
- **Validation rules**:
  - status must be from the documented status set
  - subject must identify a real file or a question identifier in the same feature
  - feature-local review queue entries may request follow-up work, but they do not override
    registry-derived `approval_needed` or `manual_review_needed`

### Question Entry

- **Purpose**: Captures a direct human question that should not live only in chat.
- **Fields**:
  - `id`: stable identifier such as `Q001`
  - `title`: short question title
  - `status`: `pending-answer`, `pending-comment`, `answered`, `commented`, or `resolved`
  - `owner`: expected responder
  - `default`: recommended default if no explicit answer is given yet
  - `description`: the context or short problem statement when needed
  - `proposed_solution`: optional proposed resolution or recommendation
  - `related_docs`: affected files or artifacts
  - `answer_or_comment`: the human response once given
- **Lifecycle**:
  - created as `pending-answer` or `pending-comment`
  - reflected in the status report as `answer_needed` or `comment_requested`
  - moved to `answered` or `commented` when human input has been recorded but is still being folded
    into docs
  - updated to `resolved` once the answer is captured in docs and no further action is pending

### Managed Doc Review State

- **Purpose**: Represents the additive registry labels that determine whether a managed doc still
  needs approval or manual review.
- **Fields**:
  - `labels`: a set that may include provenance labels such as `client-input-derived`, pending
    labels such as `unreviewed`, and terminal labels such as `reviewed`, `approved`, or
    `client-confirmed`
  - `approval_pending`: derived boolean based on whether provenance labels still lack a terminal
    approval label
  - `manual_review_pending`: derived boolean based on whether pending review labels still lack a
    terminal review label
- **Validation rules**:
  - labels must come from `.specify/doc-registry.json`
  - queue semantics must be derived from documented label combinations instead of ad hoc string
    matching
  - manual edits to managed-doc `docmeta.review` are not authoritative durable review evidence
  - sync regenerates managed-doc frontmatter from the registry rather than treating Markdown as an
    equal source of truth
  - this entity remains authoritative for durable `approval_needed` and `manual_review_needed`
    status even when feature-local queue files exist

### Managed Review Change

- **Purpose**: Represents a real human review or approval event on a managed governance doc and the
  durable registry update that records it.
- **Fields**:
  - `target_doc`: managed Markdown path
  - `review_input`: short description of the client or maintainer review event
  - `labels_before`: previous additive label set from `.specify/doc-registry.json`
  - `labels_after`: updated additive label set recorded in `.specify/doc-registry.json`
  - `synced`: derived boolean indicating whether frontmatter has been regenerated from the registry
- **Validation rules**:
  - durable review or approval changes are complete only after the registry has been updated
  - `labels_after` must remain compatible with the documented additive-label semantics
  - `synced` must become true before the docs gate can treat the managed-doc review change as
    reconciled

### Unified Doc Metadata

- **Purpose**: Represents the frontmatter-first metadata contract shared by managed docs,
  feature-local docs, skills, and command docs.
- **Fields**:
  - `docmeta.status`: lifecycle state such as `maintained`, `working`, or `draft`
  - `docmeta.review`: truthful review provenance such as `reviewed`, `feature-local`, or
    `workflow-local`
  - `docmeta.purpose`: short human-oriented purpose statement unless the doc type already has an
    equivalent field such as `description`
  - `docmeta.source`: authority for the metadata such as `.specify/doc-registry.json` or
    `document-local metadata`
  - `docmeta.feature`: optional feature link
  - `docmeta.connected_docs`: optional related-doc list
  - `docmeta.branch`: optional branch identifier
  - `docmeta.created`: optional creation date
  - `docmeta.input`: optional input provenance
- **Validation rules**:
  - YAML frontmatter is authoritative when both frontmatter and legacy `DOCMETA` exist
  - managed docs must match registry-backed values exactly
  - non-managed docs are schema-linted without falsely claiming registry-backed review state
  - skill and command docs may satisfy `purpose` and `source` through existing top-level fields such
    as `description` and `metadata.source`

### Metadata Rewrite Scope

- **Purpose**: Represents the set of Markdown files a metadata-maintenance run may inspect or
  rewrite.
- **Fields**:
  - `scope`: `all`, `managed`, or `active-feature`
  - `dry_run`: boolean indicating preview-without-mutation
  - `targets`: derived list of Markdown paths selected by the scope
- **Validation rules**:
  - `managed` includes only registry-managed docs
  - `active-feature` includes only Markdown under the directory pointed to by `.specify/feature.json`
  - `dry_run` reports pending rewrites without mutating files
  - a rewrite run must not silently widen beyond the requested scope

### Artifact Overwrite Guardrail

- **Purpose**: Represents the policy that protects filled feature artifacts such as `plan.md` from
  silent replacement.
- **Fields**:
  - `target_path`: artifact path such as `specs/001-example/plan.md`
  - `exists`: whether the artifact already exists
  - `non_empty`: whether the artifact already has substantive content
  - `force_requested`: whether an explicit overwrite flag such as `--force` was passed
  - `action`: derived outcome such as `preserved`, `copied-template`, or `touched-empty`
- **Validation rules**:
  - non-empty artifacts must be preserved by default
  - overwrite requires an explicit force path
  - the workflow should surface the chosen action so it is inspectable in logs and tests

### Active Feature Context

- **Purpose**: Represents whether the status workflow currently has an active feature directory for
  feature-local queue parsing.
- **Fields**:
  - `feature_directory`: relative path from `.specify/feature.json`, when present
  - `active`: derived boolean indicating whether the pointed feature directory exists
  - `feature_queue_enabled`: derived boolean indicating whether `questions.md` and `review-queue.md`
    should be scanned
- **Validation rules**:
  - missing active feature context is not an error for managed-doc queue reporting
  - feature-local queue categories remain empty when no active feature is set

### Temporary Review Surface

- **Purpose**: Represents the authoritative temporary file that is allowed to hold unresolved human
  input before it becomes durable governance or completed feature work.
- **Fields**:
  - `scope`: `repo-governance` or `feature-local`
  - `authoritative_file`: canonical Markdown file for unresolved items in that scope
  - `item_kind`: `research-question`, `question`, `review-queue-item`, or similar
  - `subject_refs`: related docs, features, or queue identifiers
  - `resolved`: derived boolean indicating whether the underlying issue has already been folded into
    durable docs
- **Validation rules**:
  - repo-level unresolved governance points belong in `specs/000-repo-governance/research.md`
  - feature-scoped human input belongs in that feature's `questions.md` or `review-queue.md`
  - the same unresolved point should not remain active in several temporary surfaces at once
  - resolved items should be removed or marked resolved once the durable docs are updated

### Feature Closure State

- **Purpose**: Represents whether an active feature is merely implemented, still review-open, or
  actually ready for closure and pointer cleanup.
- **Fields**:
  - `tasks_complete`: derived boolean from `tasks.md`
  - `pending_question_items`: derived list of unresolved `questions.md` entries
  - `pending_review_items`: derived list of unresolved `review-queue.md` entries in actionable
    states
  - `ready_for_closure`: derived boolean indicating that feature-local pending review work is empty
    and the implementation checklist is complete
  - `pointer_cleanup_needed`: derived boolean indicating that the feature is closure-ready while
    `.specify/feature.json` still points at it
- **Validation rules**:
  - `ready_for_closure` must not become true while feature-local answer, comment, update, approval,
    or manual-review items remain pending
  - `pointer_cleanup_needed` must not be reported for a feature that is still review-open
  - durable approval and manual-review state still come from `.specify/doc-registry.json`, even when
    feature-local queue entries mention the same subject as a closure blocker

### Feature Delivery State

- **Purpose**: Distinguishes working-tree completion from explicit review completion and final git
  landing.
- **Fields**:
  - `implemented_in_tree`: derived boolean indicating that planned changes exist locally and tests
    pass
  - `review_open`: derived boolean indicating that approvals, comments, or other queued human work
    remain
  - `landed_in_repo`: documented operational state indicating that the relevant feature artifacts are
    tracked and committed in normal git history
- **Validation rules**:
  - `implemented_in_tree` does not imply `landed_in_repo`
  - `landed_in_repo` is a documented close-out fact, not a value currently emitted by
    `tools/doc_workflow.py`
  - feature-doc `Status` language must not imply review closure merely because `implemented_in_tree`
    is true

### Durable Lesson Trace

- **Purpose**: Represents the audit trail that links a durable governance rule or code comment back
  to the feature, review, or decision that produced it.
- **Fields**:
  - `origin_type`: `feature`, `review`, `question`, or `decision`
  - `origin_ref`: feature path, queue id, or other stable source reference
  - `destination_ref`: maintained doc path, code comment location, or contract file
  - `trace_mode`: `inline-note`, `linked-doc`, `review-queue-ref`, or `git-history-only`
  - `material`: derived boolean indicating whether the trace is worth preserving in human-facing
    docs
- **Validation rules**:
  - human-facing traceability should be kept when it materially helps later audit or git-history
    lookup
  - traceability must not reintroduce unresolved TODO comments into maintained governance docs
  - `git-history-only` is acceptable only when extra visible traceability would not materially help

### Unresolved Marker Match

- **Purpose**: Represents a candidate unresolved marker found in Markdown content before queue
  reporting decides whether it is actionable.
- **Fields**:
  - `marker`: canonical marker family such as `todo-comment`, `tbd`, or `needs-clarification`
  - `raw_text`: matched text from the document
  - `context`: one of `plain-text`, `inline-code`, or `fenced-code`
  - `reportable`: derived boolean indicating whether the match should create `update_needed`
- **Validation rules**:
  - matches inside `inline-code` or `fenced-code` are not reportable
  - case does not affect marker-family matching

### Planned Feature Chunk

- **Purpose**: Names a future scoped feature derived from the governance backlog.
- **Fields**:
  - `feature_id`: e.g. `002-suppressor-journalling-policy`
  - `scope`: short scope statement
  - `depends_on`: earlier feature or governance prerequisite
  - `reason`: why the feature exists
- **Validation rules**:
  - feature id must be unique in the roadmap
  - scope must map back to an unresolved backlog concern

### Guardrail Rule

- **Purpose**: Documents a workflow restriction that prevents silent policy invention or unintended
  standing-doc edits.
- **Fields**:
  - `rule_id`: stable identifier
  - `location`: template, workflow doc, or tool
  - `intent`: what the rule prevents
  - `enforcement`: doc guidance, status-report logic, or test coverage
