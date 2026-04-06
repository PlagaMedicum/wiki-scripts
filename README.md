# be.wiki Bibliography Replacers

`bewiki-biblio` is an English operator CLI for controlled bibliography cleanup runs on be.wikipedia.org. The wiki-facing data stays Belarusian where the template names, bibliography signatures, and edit summaries require it.

## Layout

- `bewiki_biblio/`: shared Python package
- `sources/<source_id>/`: per-source config and machine-managed state
- `docs/architecture.md`: architecture and extension guide
- `tests/`: unit and CLI coverage

## Requirements

- Python 3.14+
- `pywikibot`
- `python-dotenv`
- `rich`
- a `.env` file with:
  - `WIKI_BOT_USERNAME`
  - `WIKI_BOT_PASSWORD_SUFFIX`
  - `WIKI_BOT_PASSWORD`

## Setup

```bash
python3 -m pip install -e .
```

You can then run either `bewiki-biblio ...` or `python3 -m bewiki_biblio ...`.

For local development, install the dev extras as well:

```bash
python3 -m pip install -e '.[dev]'
```

## Everyday Usage

List configured sources:

```bash
python3 -m bewiki_biblio list
```

Use the root Makefile shortcuts if you prefer:

```bash
make list
make validate
make run SOURCE=gvb1 ARGS="--limit 10 --no-color"
make run SOURCE="gvb1 gvb2 gvb3" ARGS="--learn-variants --limit 50"
make run SOURCE="--all" ARGS="--learn-variants --limit 50"
make lint
make format
make check
```

Create a new source scaffold interactively:

```bash
python3 -m bewiki_biblio add-source
```

Validate source folder layouts and required filenames:

```bash
python3 -m bewiki_biblio validate
```

Run a dry-run with colored diffs:

```bash
python3 -m bewiki_biblio run gvb1 --limit 10
```

Run several sources in one sequence:

```bash
python3 -m bewiki_biblio run gvb1 gvb2 gvb3 --limit 50
```

Run every configured source:

```bash
python3 -m bewiki_biblio run --all --limit 50
```

Comma-separated source IDs are also accepted:

```bash
python3 -m bewiki_biblio run gvb1,gvb2,gvb3 --limit 50
```

Apply changes with interactive approval:

```bash
python3 -m bewiki_biblio run gvb1 --apply --learn-variants
```

Apply all matches without per-page confirmation:

```bash
python3 -m bewiki_biblio run gvb1 --apply --yes
```

Override the default edit summary:

```bash
python3 -m bewiki_biblio run gvb1 --apply --summary 'Замена бібліяграфічнай спасылкі шаблонам {{Крыніцы/ГВБ}}'
```

Disable Rich colors and styling:

```bash
python3 -m bewiki_biblio run gvb1 --no-color
```

## Run Controls

- Dry-run is the default.
- `--apply` enables saving.
- `--apply` without `--yes` keeps the per-page review loop.
- `--all` runs every configured source in discovery order.
- when you run multiple sources, they are processed in the order you entered them
- in a multi-source `--apply` run, pressing `a` saves all remaining matched pages across the rest of the entered sources
- During interactive apply runs:
  - `y` saves the current page
  - `n` skips the current page
  - `a` saves the current and all remaining matches
  - `e` edits the run summary for the remaining pages
  - `q` stops the run

## Adding a New Source

1. Create `sources/<source_id>/`.
2. Add `source.toml` with `[source]`, `[search]`, `[candidate]`, `[replacement]`, `[summary]`, `[pages]`, `[normalization]`, `[macros]`, and `[[regex_rules]]`.
3. Add `rules.json`, `review_variants.json`, and `ignored_variants.json`.
4. Add `sources/<source_id>/README.md` with operator notes and examples.
5. Add or update tests covering the new source behavior.

`source.toml` is hand-authored. The JSON state files are machine-managed and updated during review/learning workflows.

## Source Scaffolding

`add-source` is the interactive bootstrap command for a new bibliography source. It should create the canonical source folder and canonical filenames:

- `sources/<source_id>/source.toml`
- `sources/<source_id>/rules.json`
- `sources/<source_id>/review_variants.json`
- `sources/<source_id>/ignored_variants.json`
- `sources/<source_id>/README.md`

The scaffold keeps search-term prompts blank. Candidate prompts are then guessed from what you entered:

- `must_contain_all` defaults to the first strong text term
- `must_contain_any` defaults to the ISBNs plus remaining text terms

These defaults come from the current scaffold answers, not from any existing source folder.

The folder name must be source-id-safe: lowercase ASCII letters, digits, and hyphens only. The scaffold should reject unsafe names instead of trying to normalize them silently.

## Validation

`validate` checks that the source tree follows the repository convention:

- each source lives in `sources/<source_id>/`
- the directory name matches `source.toml`'s `[source].id`
- required files exist under their canonical names
- obvious misnamings such as `rules.JSON` or `readme.md` are reported as invalid

Validation exits nonzero when the source layout is incomplete or misnamed.

## `source.toml` Shape

- `[search]`:
  - `insource_terms` are always added to the generated query
  - `isbns` and `keywords` are convenience lists appended to the same query
- `[candidate]`:
  - `must_contain_all` is used for review/debug candidate detection
  - `must_contain_any` is an additional broadening/narrowing layer independent from search generation
- `[macros]`:
  - regex rules may reference `{{MACRO_NAME}}`
  - built-in structural macros are available automatically: `LIST_PREFIX`, `WS`, `OPT_WS`, `SEP`, `DASH`, `OPT_DASH`, `PAGES`, `YEAR4`, `ISBN_TOKEN`
  - built-in names are reserved and cannot be overridden

Regex rules are compiled once at source-load time after recursive macro expansion.

## Development

Use Ruff for both linting and formatting:

```bash
make lint
make format
make check
```

`make lint` runs `ruff check` and `ruff format --check`.

`make format` applies safe Ruff fixes and formats the Python codebase.

`make check` runs compile checks, tests, and linting in one pass.
