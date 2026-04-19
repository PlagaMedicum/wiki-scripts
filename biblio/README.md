# Biblio

<!-- DOCMETA:START -->
> Status: maintained
> Review: code-reviewed
> Purpose: Operator entry points and current documented contract for biblio.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

`biblio` is the Python tool for bibliography and citation cleanup on wiki pages. It remains a
narrow tool: deterministic source-driven matching, reviewable changes, and controlled wiki edits.

It was first built for be.wikipedia.org, but the project is being kept generic enough to retarget
to other local wikis later.

## Current Shape

- one Python project
- one installed CLI command: `biblio`
- one operator Makefile
- source definitions tracked as `sources/<source_id>/source.toml`
- local runtime state kept next to the source as JSON and not treated as authored docs

The future direction is to separate source-population/import work from source-processing/edit work,
but that split is not implemented yet.

## Quick Start

Run from `biblio/`:

```bash
uv sync --dev
cp .env.example .env
make run
```

Example `.env`:

```dotenv
WIKI_BOT_USERNAME=YourBot@biblio-local
WIKI_BOT_PASSWORD=REDACTED
```

`WIKI_BOT_USERNAME` now uses the full BotPasswords login in the form `username@label`.

## Common Commands

- `make run`
- `make list`
- `make validate`
- `make add-source`
- `make test`
- `make lint`
- `make format`
- `make audit`
- `make check`

Direct CLI examples:

```bash
uv run --locked biblio
uv run --locked biblio run gvb1 --limit 10
uv run --locked biblio run gvb1 --limit 10 --apply
```

## Source Contract

Tracked source definition:

- `sources/<source_id>/source.toml`

Local runtime state:

- `rules.json`
- `review_variants.json`
- `ignored_variants.json`

Per-source `README.md` files are no longer part of the source-definition contract.

## Review Rules

- broad regex rules require manual review
- uncertain source mapping or import matches require manual review
- page-wide rewrites may auto-apply only when the match is exact and deterministic
- learned replacements need one manually approved proven occurrence before automatic promotion

## Scope Boundary

Use `biblio` for:

- bibliography and citation cleanup
- deterministic template replacement
- structured source families that still fit source-driven matching

Do not stretch `biblio` into a general wiki text engine. If a request stops looking like
bibliography or citation cleanup, it should become a separate tool.

## Current Requirements

- Python `3.14+` in the current project metadata
- `uv`
- a local `.env`

## Further Reading

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/testing-strategy.md`](docs/testing-strategy.md)
