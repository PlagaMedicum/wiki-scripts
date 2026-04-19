# Specs

<!-- DOCMETA:START -->
> Status: maintained
> Review: client-input-derived
> Purpose: Explains the standing governance spec versus change-specific feature specs.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

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
├── quickstart.md
├── contracts/
└── tasks.md
```

Feature specs are owned by the Spec Kit workflow and are not part of the managed human-doc
registry.

Completed feature specs should stay only while they still add active context. Git history is the
default archive once durable lessons are fixed elsewhere.

## Read Order

1. `README.md`
2. `.specify/memory/constitution.md`
3. `specs/000-repo-governance/`
4. if `.specify/feature.json` exists, the active feature spec referenced there
5. otherwise, the relevant `specs/NNN-feature-name/` directory for the current non-trivial work
