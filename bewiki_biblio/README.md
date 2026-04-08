# be.wiki Bibliography Replacers

`bewiki-biblio` is the Python CLI for controlled bibliography cleanup runs on be.wikipedia.org. The operator-facing text stays English, while the wiki-facing templates, signatures, and summaries stay Belarusian where required.

This directory is the project root for the bibliography tool inside the wider `scripts/` repository.

## Start Here

- [Documentation index](docs/README.md)
- [Architecture overview](docs/architecture.md)
- [Architecture review and proposals](docs/architecture-review.md)
- [Package code](bewiki_biblio/)
- [Source definitions](sources/)
- [Tests](tests/)

## Layout

- `bewiki_biblio/`: shared Python package
- `sources/<source_id>/`: per-source config plus optional local runtime state
- `docs/`: project documentation, including the stable architecture guide and critical review
- `tests/`: unit and CLI coverage
- `.env`, `.pywikibot/`, `apicache/`, `throttle.ctrl`: local operator config and runtime state

## Requirements

- Python 3.14+
- `pywikibot`
- `python-dotenv`
- `rich`
- a local `.env` file in this directory with:
  - `WIKI_BOT_USERNAME`
  - `WIKI_BOT_PASSWORD_SUFFIX`
  - `WIKI_BOT_PASSWORD`

## Install

Run these commands from `bewiki_biblio/`:

```bash
python3 -m pip install -e .
python3 -m pip install -e '.[dev]'
```

The first command installs the CLI. The second adds test and lint dependencies.

## Common Commands

- `make run` opens the interactive startup wizard.
- `make run SOURCE=gvb1 ARGS="--limit 10"` runs one source.
- `make run SOURCE="gvb1 gvb2 gvb3" ARGS="--learn-variants --limit 50"` runs several sources.
- `make run SOURCE="--all" ARGS="--apply --yes --skip-review-required --limit 500"` runs every configured source unattended.
- `make list` lists configured sources.
- `make validate` checks source folder layouts and filenames.
- `make add-source` creates a new source scaffold.
- `make test`, `make lint`, `make format`, `make check` cover the local development workflow.

Direct CLI equivalents are also available:

```bash
python3 -m bewiki_biblio
python3 -m bewiki_biblio list
python3 -m bewiki_biblio validate
python3 -m bewiki_biblio add-source
python3 -m bewiki_biblio run gvb1 --limit 10
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
make test
make lint
make format
make check
```

`make check` runs tests and linting.
