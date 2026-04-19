---
docmeta:
  status: maintained
  review:
  - client-input-derived
  - approved
  purpose: Explains the standing governance spec versus change-specific feature specs.
  source: .specify/doc-registry.json
---

# Specs


`specs/` is the only structured top-level docs area in this repo.

## Two Kinds Of Specs Live Here

### `000-*`: Standing Repo-Maintained Specs

`specs/000-repo-governance/` is the durable repo state:

- accepted repo decisions
- unresolved repo-level questions
- practical workflow guidance
- future work backlog

This area is human-maintained and covered by `.specify/doc-registry.json`.

### `NNN-*`: Change-Specific Feature Specs

Use `specs/NNN-feature-name/` for non-trivial scoped work:

- new tools
- major refactors
- service splits
- high-risk operational changes
- workflow or doc-governance changes

Recommended layout:

```text
specs/<id>/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── questions.md        # Optional: direct human questions and requested comments
├── review-queue.md     # Optional: current human action queue for the feature
├── quickstart.md
├── checklists/         # Optional: requirements-quality checklists
├── contracts/
└── tasks.md
```

Feature specs are owned by the Spec Kit workflow and are not part of the managed human-doc
registry.

If a feature needs direct human approval, comments, or answers, record that need in feature-local
files such as `questions.md` or `review-queue.md` instead of relying only on chat history.

Completed feature specs should stay only while they still add active context. Git history is the
default archive once durable lessons are fixed elsewhere.

## Read Order

1. `README.md`
2. `.specify/memory/constitution.md`
3. `specs/000-repo-governance/`
4. if `.specify/feature.json` exists, the active feature spec referenced there
5. otherwise, the relevant `specs/NNN-feature-name/` directory for the current non-trivial work
