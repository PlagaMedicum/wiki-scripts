---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current biblio boundaries, module roles, and source-definition rules.
  source: .specify/doc-registry.json
---

# Biblio Architecture


## Current Reality

`biblio` is currently a modular Python CLI application, not a split service architecture.

An initial internal boundary now exists between source onboarding/import flow and
source-processing/edit flow, but that boundary is still inside one package and one operator-facing
CLI.

It has three important boundary areas:

- source-driven text rules
- operator workflow orchestration
- wiki/filesystem/UI adapters

## Boundary Map

### Core Rules

These modules own deterministic source logic and should stay closest to the center:

- `models.py`
- `source_templates.py`
- `specs.py`
- `text.py`
- `engine.py`

This area owns source loading, normalization, extraction, matching, and template rendering.

### Orchestration And Policy

These modules sequence the operator workflow:

- `query.py`
- `page_analysis.py`
- `page_execution.py`
- `page_save.py`
- `session.py`
- `workflow.py`
- `runner.py`
- `startup.py`
- `manage_*.py`

This layer should coordinate policy without turning into a second domain layer.

The current onboarding/import side is most visible in:

- `manage_import.py`
- `manage_tui.py`
- `manage_questions.py`
- `manage_write.py`

### Adapters

These modules touch external systems:

- `bootstrap.py`
- `runtime.py`
- `runtime_json.py`
- `state.py`
- `ui.py`
- `observability.py`
- `transport.py`

## Source Contract

Tracked source-of-truth:

- `sources/<source_id>/source.toml`

Local runtime state:

- `rules.json`
- `review_variants.json`
- `ignored_variants.json`

Per-source README files are not part of the tracked source-definition contract anymore.

## Auth Contract

`biblio` now aligns with the repo-wide bot-login shape:

- `WIKI_BOT_USERNAME=username@label`
- `WIKI_BOT_PASSWORD=secret`

## Scope Boundary

`biblio` is still bibliography-first.

Good fit:

- citation cleanup
- bibliography normalization
- deterministic template replacement
- reviewable wiki edits

Bad fit:

- broad text automation
- fuzzy document ranking
- semantic cleanup tasks
- unrelated wiki maintenance workflows

If a request stops being bibliography-shaped, it should become a separate tool.

## Future Direction

Planned direction, not current implementation:

- turn the current code-level onboarding/import boundary into a more explicit real boundary with
  the smallest useful next step
- keep shared reusable components beneath that split
- keep one operator-facing Makefile even if the backend shape grows
