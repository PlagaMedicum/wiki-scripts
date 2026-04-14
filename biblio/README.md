# Biblio

`biblio` is the preferred Python CLI for controlled bibliography cleanup runs. It was first
developed for be.wikipedia.org, so the defaults and examples lean toward that wiki, but the source
folders are generic and can be retargeted to another local wiki.

This directory is the project root for the bibliography tool inside the wider `scripts/`
repository.

## Quick Local Setup

1. Sync the locked project environment with `uv`:

   ```bash
   cd biblio
   uv sync --dev
   ```

2. Create `biblio/.env` with your bot-password credentials from `Special:BotPasswords` on
   the target wiki.
3. Run `uv run --locked biblio --help` to check the installed command.
4. Run `make run` to open the startup wizard.

Special:BotPasswords setup:

- create a bot password for the account you will use
- choose a clear label, such as `biblio-local`
- grant `High-volume (bot)` access so MediaWiki will accept bot-marked saves for that session
- put the base account name, without `@label`, in `WIKI_BOT_USERNAME`
- put only the chosen label in `WIKI_BOT_PASSWORD_SUFFIX`
- put the generated bot password secret in `WIKI_BOT_PASSWORD`
- do not commit `.env`

Example mapping:

```dotenv
WIKI_BOT_USERNAME=ExampleBot
WIKI_BOT_PASSWORD_SUFFIX=biblio-local
WIKI_BOT_PASSWORD=REDACTED
```

That corresponds to a bot-password login shown by MediaWiki as `ExampleBot@biblio-local`.

## Operator Runbook

Start here for a normal run:

- `make run` opens the interactive startup wizard.
- `make list` shows the configured sources.
- `make validate` checks source folder layouts and canonical filenames.
- `make add-source` creates a new source scaffold.

The canonical human entry point is `make run`. The installed command and the internal module path
are both `biblio`.

All saved page edits are submitted with MediaWiki's bot flag, and startup now hard-fails if the
authenticated session does not actually hold the `bot` right.

To run a specific source without using the wizard, pass the CLI arguments through the Makefile or
call the CLI directly:

```bash
make run ARGS="run gvb1 --limit 10"
uv run --locked biblio run gvb1 --limit 10
```

## Maintainer Workflow

For design notes, architecture, and review context, read:

- [Documentation index](docs/README.md)
- [Architecture overview](docs/architecture.md)
- [Architecture review](docs/architecture-review.md)
- [Page save boundary](docs/page-save-boundary.md)

For code and data:

- [Package code](biblio/)
- [Source definitions](sources/)
- [Tests](tests/)

## Layout

- `biblio/`: shared Python package
- `sources/<source_id>/`: per-source config plus optional local runtime state
- `docs/`: maintainer documentation and architectural review
- `tests/`: unit and CLI coverage
- `.env`, `.pywikibot/`, `apicache/`, `throttle.ctrl`: local operator config and runtime state

## Adapting To Another Local Wiki

The code was first built for be.wiki, but a new local wiki usually only needs source and auth
changes, not a rewrite.

- copy or add a source folder under `sources/<source_id>/`
- set the target wiki in that source's `site_lang` and `family`
- adjust the source search terms, template names, page patterns, and normalization toggles
- review the default edit summary text and any Belarusian wiki-facing template output before reuse
- keep `WIKI_BOT_USERNAME`, `WIKI_BOT_PASSWORD_SUFFIX`, and `WIKI_BOT_PASSWORD` pointing at the
  target wiki's bot password credentials
- if the new wiki needs different login variable names or endpoint defaults, update the shared
  bootstrap contract and the docs together
- keep the source-specific README local to the source folder and link back to this project README
- treat the existing `sources/` tree as be.wiki-specific examples, not a drop-in source pack for
  another wiki

## Requirements

- Python 3.14+
- `uv` 0.11.6+
- `pywikibot`
- `python-dotenv`
- `rich`
- a local `.env` file in this directory with:
  - `WIKI_BOT_USERNAME`
  - `WIKI_BOT_PASSWORD_SUFFIX`
  - `WIKI_BOT_PASSWORD`

## Dependency Tracking

`biblio` now treats `uv.lock` as the authoritative dependency snapshot.

- Runtime dependencies are intentionally minimal: `pywikibot`, `python-dotenv`, and `rich`.
- Dev-only tools live in the `dev` dependency group and are not shipped as runtime requirements.
- `make run`, `make test`, `make lint`, and `make audit` all execute with `uv run --locked`, so
  they refuse to drift away from the committed lockfile.
- The Makefile keeps `uv` and audit caches inside the project tree, so the workflow does not rely
  on mutable global cache directories.

## Install

Run these commands from `biblio/`:

```bash
uv sync --dev
```

That installs the package plus the locked development toolchain into the local `uv` environment.

If you need a plain editable install without `uv`, `pip install -e .` still works for the package
itself, but the tracked maintainer workflow is `uv`.

## Direct CLI Equivalents

```bash
uv run --locked biblio
uv run --locked biblio list
uv run --locked biblio validate
uv run --locked biblio add-source
uv run --locked biblio run gvb1 --limit 10
uv run --locked python -m biblio
```

## Read Order

1. [README.md](README.md)
2. [docs/README.md](docs/README.md)
3. [docs/architecture.md](docs/architecture.md)
4. [docs/architecture-review.md](docs/architecture-review.md)
5. `sources/<source_id>/README.md`

## Source Notes

Each source keeps its own canonical files:

- `source.toml`
- `README.md`

The JSON runtime files are local and gitignored:

- `rules.json`
- `review_variants.json`
- `ignored_variants.json`

## Development

Use the local Makefile for the normal project loop:

```bash
make sync
make lock
make test
make lint
make audit
make format
make check
```

`make check` syncs the locked environment, then runs tests, linting, and a dependency audit.
