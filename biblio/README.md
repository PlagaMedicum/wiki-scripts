# Biblio

`biblio` is the Python tool for bibliography and citation cleanup on wiki pages. It remains a
narrow tool: deterministic source-driven matching, reviewable changes, and controlled wiki edits.

It was first built for be.wikipedia.org, but the project is being kept generic enough to retarget
to other local wikis later.

## Current Shape

- one Python project
- one installed CLI command: `biblio`
- one operator Makefile
- source definitions kept locally as `sources/<source_id>/source.toml`
- local runtime state kept next to the source as JSON and not treated as authored docs

Source onboarding/import code and page-processing/edit code are kept separate inside one Python
project and one CLI.

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

`--limit` applies to each source volume, not to the whole command. A merged
source can therefore inspect up to that many pages for every configured volume.

## Source Contract

Local source definition (the `sources/` directory is ignored by Git):

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
- page-title fallback proposals require manual review and are declined if the
  target cannot render the inferred entry
- initials-first authors followed by a period are separated from entry titles only
  when both source template forms can render the author
- protected comment and literal/code regions are not rewritten
- book citations with unsupported nonempty parameters, ambiguous parameter
  boundaries, duplicate parameters, or surrounding reference text remain unchanged;
  source links and custom anchors are not silently removed

These guards do not prove that every publication field matches the target template.
Check source definitions and review diffs, particularly when edition metadata cannot
be verified from the source configuration.

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
