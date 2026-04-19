# Repo Documentation Structure Plan

<!-- DOCMETA:START -->
> Status: maintained
> Review: client-input-derived
> Purpose: Current documentation structure contract for the repo.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

## Current Structure Contract

This repo keeps durable human guidance in a very small set of places:

- `README.md`
- `.specify/memory/constitution.md`
- `specs/README.md`
- `specs/000-repo-governance/`
- project-local README/docs files that directly help operators or maintainers

There is no separate top-level `docs/` tree anymore.

## Specs Layout

### Standing Repo Spec

`specs/000-repo-governance/` is the durable repo-maintained area:

- `spec.md`: accepted repo model and decisions
- `research.md`: unresolved repo-level questions
- `quickstart.md`: practical Spec Kit usage in this repo
- `plan.md`: documentation and workflow structure contract
- `tasks.md`: future work roadmap

### Change Specs

`specs/NNN-feature-name/` is for scoped change work:

- feature specification
- design and research artifacts
- implementation task breakdown
- evidence and change-local notes

Feature specs are not part of the managed human-doc registry.

## Managed Doc Policy

- Managed docs are listed in `.specify/doc-registry.json`.
- `tools/doc_workflow.py sync` rewrites their metadata blocks deterministically.
- `tools/doc_workflow.py lint` fails if registry state and Markdown drift apart.
- `tools/doc_workflow.py status` reports review backlog, update backlog, stale feature specs, and
  registry/link problems.

## Explicit Final Gate

The standard repo docs gate is:

```bash
make docs
```

That runs:

1. metadata sync
2. metadata lint
3. docs-tool tests
4. status reporting

The equivalent explicit Spec Kit command is `/speckit.docs.docs`.

## Project-Local Docs

Project-local docs should stay only where they add real value beyond the project README:

- architecture/runtime shape
- operator contract
- testing strategy

Project-local doc index files should not exist just to repeat a short link list.
