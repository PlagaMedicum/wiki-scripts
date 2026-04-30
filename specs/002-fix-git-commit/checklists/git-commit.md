---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for manual `speckit.git.commit` behavior.
  source: user-request-derived
---

# Git Commit Checklist: Git Commit Command Reliability

Purpose: Validate whether the feature requirements for explicit `speckit.git.commit` behavior are complete, clear, consistent, and measurable.
Created: 2026-04-30
Feature: [spec.md](/home/plagamed/Documents/wiki/scripts/specs/002-fix-git-commit/spec.md)

## Requirement Completeness

- [ ] CHK001 Are requirements defined for how pre-existing staged changes must be treated relative to unstaged changes when the manual command starts? [Completeness, Spec §Edge Cases, Spec §FR-003, Spec §FR-007]
- [ ] CHK002 Does the spec define whether ignored files, generated artifacts, or nested repositories are intentionally excluded from “all pending intended changes”? [Gap, Spec §FR-003, Spec §FR-007]
- [ ] CHK003 Are requirements defined for what operator-visible commit metadata must be reported beyond commit IDs, such as touched path summaries or grouping rationale? [Completeness, Spec §FR-006, Spec §FR-011, Spec §Commit Result Summary]
- [ ] CHK004 Are requirements complete for tracked, untracked, deleted, and renamed paths that appear together in the same scope group? [Coverage, Spec §Edge Cases, Spec §FR-007, Spec §Commit Scope Group]

## Requirement Clarity

- [ ] CHK005 Is “pending intended changes” defined precisely enough to distinguish intentional work from unrelated incidental dirty files already present in the worktree? [Ambiguity, Spec §FR-003]
- [ ] CHK006 Is “coherent scope” defined with objective grouping signals so two reviewers would classify the same worktree similarly? [Clarity, Spec §FR-004, Spec §FR-009, Spec §Commit Scope Group]
- [ ] CHK007 Is “small-scope commit” bounded well enough to avoid both over-splitting and collapsing unrelated changes? [Clarity, Spec §FR-004]
- [ ] CHK008 Is the required “structured message” format specified with concrete minimum fields beyond “summary plus detail”? [Clarity, Spec §FR-005, Spec §SC-004]

## Requirement Consistency

- [ ] CHK009 Do `FR-003` and `FR-009` align on whether the command may proceed when some changes cannot be separated safely from others? [Consistency, Spec §FR-003, Spec §FR-009]
- [ ] CHK010 Do User Story 2 and the assumptions section consistently define when one commit is acceptable versus when multiple commits are mandatory? [Consistency, Spec §User Story 2, Spec §Assumptions]
- [ ] CHK011 Do the manual-invocation requirements remain consistent with the preserved hook-controlled behavior described for automatic before/after contexts? [Consistency, Spec §FR-002, Spec §FR-008, Spec §User Story 3]

## Acceptance Criteria Quality

- [ ] CHK012 Can `SC-002` be verified objectively without a documented definition of “intended changes” for the mixed-scope regression fixture? [Measurability, Spec §SC-002, Spec §FR-003]
- [ ] CHK013 Can `SC-003` be verified objectively without fixture-level rules for what counts as a distinct coherent change group? [Measurability, Spec §SC-003, Spec §FR-004, Spec §FR-009]
- [ ] CHK014 Does `SC-005` define the exact output cues that let a maintainer distinguish clean, blocked, hook-skip, and committed outcomes within 15 seconds? [Clarity, Spec §SC-005, Spec §FR-006]
- [ ] CHK015 Are acceptance criteria defined for the actionability and specificity required from blocking-reason output under Git failure conditions? [Gap, Spec §FR-010, Spec §SC-005]

## Scenario Coverage

- [ ] CHK016 Are requirements complete for repos that start with partially staged files, where the index already encodes a scope split before the command runs? [Coverage, Spec §Edge Cases, Spec §FR-003, Spec §FR-007]
- [ ] CHK017 Are requirements defined for mixed outcomes where one planned scope commits successfully and a later scope hits a blocking Git condition? [Coverage, Spec §FR-003, Spec §FR-006, Spec §FR-010]
- [ ] CHK018 Are requirements complete for distinguishing a true clean worktree from a worktree where every dirty path is excluded by documented workflow rules? [Coverage, Spec §User Story 3, Spec §FR-006, Spec §FR-007]
- [ ] CHK019 Are requirements complete for renamed paths that also carry edits, where grouping and reporting may need both the old and new path identity? [Coverage, Spec §Edge Cases, Spec §FR-007, Spec §FR-011]

## Edge Case Coverage

- [ ] CHK020 Are rollback or recovery requirements defined for failures that occur after one of several planned commits has already been created? [Gap, Spec §FR-003, Spec §FR-010]
- [ ] CHK021 Are blocking-state requirements specific enough to cover stale lockfiles, unresolved conflicts, permission failures, detached HEAD, and similar repository states intentionally and consistently? [Coverage, Spec §FR-010, Spec §Edge Cases]
- [ ] CHK022 Does the spec define what should happen when unrelated scopes are interleaved in the same feature area and no clean split is defensible? [Clarity, Spec §Edge Cases, Spec §FR-009]

## Dependencies & Assumptions

- [ ] CHK023 Is the assumption that grouping can rely on “visible change boundaries” supported by documented signals or examples rather than implicit human memory? [Assumption, Spec §Assumptions, Spec §Commit Scope Group]
- [ ] CHK024 Are repository-specific ignore rules and workflow conventions documented well enough for `FR-007` to be applied consistently across projects? [Dependency, Spec §FR-007, Spec §Documentation Impact]
- [ ] CHK025 Does the spec define whether branch state, missing upstream configuration, or protected-branch policy belong to the set of blocking Git conditions? [Gap, Spec §FR-010]

## Ambiguities & Conflicts

- [ ] CHK026 Is there a clear rule for when the command must stop completely versus create the smallest truthful subset of commits and report the remainder? [Ambiguity, Spec §FR-003, Spec §FR-009]
- [ ] CHK027 Does the spec distinguish “manual command created no commit because the tree was clean” from “manual command created no commit because the remaining changes were intentionally excluded”? [Ambiguity, Spec §FR-006, Spec §FR-007, Spec §User Story 3]
- [ ] CHK028 Is it explicit whether hook-skip messaging is ever valid in a manual invocation path, or must manual invocation always suppress that wording entirely? [Consistency, Spec §FR-002, Spec §FR-006, Spec §User Story 3]
