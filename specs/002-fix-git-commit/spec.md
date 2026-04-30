---
docmeta:
  status: draft
  review: feature-local
  purpose: Specify the future behavior of explicit `speckit.git.commit` invocations.
  source: user-request-derived
---

# Feature Specification: Git Commit Command Reliability


## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explicit Commit Runs Actually Commit Work (Priority: P1)

An operator explicitly invokes `speckit.git.commit` because they want the current worktree saved in
Git immediately. The command must not silently do nothing just because hook automation is disabled.

**Why this priority**: The explicit command is currently not trustworthy enough for the operator to
use as a real save point, which breaks the intended workflow.

**Independent Test**: Start with a dirty worktree, run `speckit.git.commit` manually, and confirm
that all pending intended changes are either committed or blocked with an explicit reason before any
partial result is left behind.

**Acceptance Scenarios**:

1. **Given** tracked or untracked worktree changes exist, **When** the operator runs
   `speckit.git.commit` directly, **Then** the command creates commit output instead of skipping
   because hook auto-commit is disabled.
2. **Given** the command cannot safely commit everything because of a blocking Git condition,
   **When** the operator runs it, **Then** it stops with a clear blocking reason and does not
   pretend that nothing needed to be committed.

---

### User Story 2 - Mixed Work Is Split Into Small Coherent Commits (Priority: P2)

An operator often accumulates several related but distinct edits before asking for a commit. The
command should split that work into small-scope commits instead of collapsing unrelated edits into a
single large history entry.

**Why this priority**: Reviewability and later audit depend on commit history that preserves the
separate intent of each change group.

**Independent Test**: Prepare a dirty worktree that contains at least two clearly different change
groups, run `speckit.git.commit`, and verify that the produced history contains separate commits
whose file scopes and messages align with those groups.

**Acceptance Scenarios**:

1. **Given** pending changes fall into multiple coherent scopes, **When** the operator runs
   `speckit.git.commit`, **Then** the command creates multiple commits rather than one aggregate
   commit.
2. **Given** only one coherent change scope is pending, **When** the operator runs
   `speckit.git.commit`, **Then** the command may create one detailed commit but still must cover
   all pending intended changes.

---

### User Story 3 - Commit Results Are Understandable And Auditable (Priority: P3)

An operator needs to know exactly what the command committed, why commits were grouped the way they
were, and whether hook-driven auto-commit behavior differs from explicit manual invocation.

**Why this priority**: A commit command that saves work but does not explain its result still leaves
the operator uncertain about what happened.

**Independent Test**: Run the command in direct-invocation and hook-driven contexts and verify that
the output distinguishes manual commit behavior from disabled hook behavior, and that every created
commit has a readable structured message.

**Acceptance Scenarios**:

1. **Given** the command creates one or more commits, **When** the operator reviews the result,
   **Then** they can see the created commit identifiers and the scope or reason for each commit.
2. **Given** hook automation is disabled but the operator invokes `speckit.git.commit` manually,
   **When** the command runs, **Then** the result clearly reflects manual commit execution rather
   than reporting a hook-configuration skip.
3. **Given** no pending changes exist, **When** the operator runs `speckit.git.commit`, **Then**
   the command reports a true clean-worktree result rather than a misleading generic skip.

---

### Edge Cases

- What happens when the worktree contains tracked, untracked, deleted, and renamed files at the
  same time?
- How does the command behave when unrelated scopes are interleaved across the same feature area
  and cannot be cleanly separated without risking false grouping?
- What happens when the Git index is blocked by unresolved conflicts, a stale lock, or missing
  write permission?
- How does the command distinguish a true clean worktree from a disabled hook configuration or a
  blocked commit path?
- What happens when the current repo already has staged content before the command starts?
- How does the system preserve current hook-driven behavior for automatic before/after commands
  while changing explicit manual invocation behavior?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A direct operator invocation of `speckit.git.commit` MUST attempt to commit the
  current pending worktree changes even when hook auto-commit configuration is disabled.
- **FR-002**: The system MUST distinguish explicit manual invocation from hook-triggered
  auto-commit so that disabled hook settings do not cause the manual command to no-op.
- **FR-003**: The manual command MUST either cover all pending intended changes in the current
  worktree or stop with an explicit blocking reason before leaving a misleading partial result.
- **FR-004**: When pending changes can be separated into more than one coherent scope, the manual
  command MUST create multiple small-scope commits instead of one aggregate commit.
- **FR-005**: Every commit created by the manual command MUST use a structured message that
  includes a concise summary and additional explanatory detail about scope, intent, or rationale.
- **FR-006**: The system MUST report the outcome of a manual invocation clearly, including whether
  it created commits, found a clean worktree, or stopped because of a blocking Git condition.
- **FR-007**: The system MUST treat tracked, untracked, modified, deleted, and renamed files as
  part of the explicit manual commit coverage unless an existing documented ignore rule excludes
  them from the repository workflow.
- **FR-008**: The system MUST preserve existing configuration-controlled hook behavior for automatic
  before/after command contexts unless the operator explicitly invokes the manual commit command.
- **FR-009**: If the system cannot safely determine multiple coherent scopes, it MUST choose the
  smallest truthful grouping it can justify and report that grouping outcome instead of silently
  collapsing unrelated work without explanation.
- **FR-010**: The system MUST detect blocking repository states such as unresolved conflicts,
  unusable index state, or write-permission failures and surface an actionable operator message.
- **FR-011**: The system MUST make the produced commit history inspectable enough that a reviewer
  can understand which files and intent belong to each generated commit without reading chat
  history.
- **FR-012**: The feature’s docs and workflow guidance MUST explain the difference between
  configuration-controlled hook auto-commit and direct manual `speckit.git.commit` behavior.

### Key Entities *(include if feature involves data)*

- **Commit Invocation Context**: The operator-visible mode in which commit behavior is requested,
  such as explicit manual invocation or hook-triggered auto-commit. Key attributes include trigger
  source, configuration effect, and whether commit execution is authoritative.
- **Commit Scope Group**: A coherent subset of pending changes that should become one history
  entry. Key attributes include included paths, grouping rationale, and whether it can be
  separated safely from other pending work.
- **Commit Result Summary**: The user-facing outcome of a commit run. Key attributes include
  created commit identifiers, clean-worktree result, blocking reason, and any grouping explanation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of regression scenarios where a dirty worktree is present and no blocking Git
  condition exists, a direct `speckit.git.commit` invocation produces one or more commits instead
  of a configuration-based no-op result.
- **SC-002**: In the maintained mixed-scope regression fixture, 100% of pending paths are covered
  by the created commit sequence, and no path is left uncommitted without an explicit blocking
  reason.
- **SC-003**: In the maintained multi-scope regression fixture, the command produces at least one
  separate commit per coherent change group identified by the fixture acceptance rules.
- **SC-004**: 100% of commits created by the command contain both a concise one-line summary and at
  least one explanatory body line describing scope or intent.
- **SC-005**: In operator verification, the outcome text lets a maintainer distinguish successful
  commit creation, clean-worktree status, hook-skip status, and blocked-commit status within 15
  seconds.
- **SC-006**: Updated workflow guidance and command documentation are sufficient for a maintainer
  to predict the difference between explicit manual commit behavior and hook-driven auto-commit
  behavior without relying on chat history.

## Assumptions

- The operator request targets the explicit manual `speckit.git.commit` command first; hook-driven
  auto-commit remains configuration-controlled unless separately approved for broader behavior
  changes.
- When only one coherent scope exists in the pending worktree, one detailed commit is acceptable;
  the must-split behavior applies when multiple coherent scopes are present.
- The repository remains a normal Git worktree with permission to create commits when the command is
  used successfully.
- Rewriting existing history, amending prior commits, or changing branch-switch behavior is outside
  this feature unless explicitly added later.
- Grouping may use repository context and visible change boundaries, but it should not depend on
  undocumented human memory of why a file changed.

## Documentation Impact

- Update the repo-local `speckit-git-commit` command guidance and any extension readme that
  describes auto-commit behavior.
- Update any workflow docs that currently imply the manual command is governed only by
  `auto_commit` configuration.
- Update feature planning and task artifacts for this feature after the spec is accepted.
