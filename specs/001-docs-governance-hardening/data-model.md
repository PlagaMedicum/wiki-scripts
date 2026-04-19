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
  - this entity remains authoritative for durable `approval_needed` and `manual_review_needed`
    status even when feature-local queue files exist

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
