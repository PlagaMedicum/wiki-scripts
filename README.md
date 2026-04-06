# be.wiki Bibliography Replacers

`bewiki-biblio` is an English operator CLI for controlled bibliography cleanup runs on be.wikipedia.org. The wiki-facing data stays Belarusian where the template names, bibliography signatures, and edit summaries require it.

## Layout

- `bewiki_biblio/`: shared Python package
- `sources/<source_id>/`: per-source config plus optional local runtime state
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
make run-interactive
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

Launch the interactive startup wizard with no command-line arguments:

```bash
python3 -m bewiki_biblio
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

Review both unknown candidates and heuristic manual-review matches without saving:

```bash
python3 -m bewiki_biblio run belen1 --learn-variants --limit 50
```

Apply all matches without per-page confirmation:

```bash
python3 -m bewiki_biblio run gvb1 --apply --yes
```

Apply only already-verified matches in the background and skip pages that still need manual review:

```bash
python3 -m bewiki_biblio run --all --apply --yes --skip-review-required --limit 500
```

Override the default edit summary:

```bash
python3 -m bewiki_biblio run gvb1 --apply --summary 'Замена бібліяграфічнай спасылкі шаблонам {{Крыніцы/ГВБ}}'
```

Change the minor-edit threshold:

```bash
python3 -m bewiki_biblio run gvb1 --apply --minor-threshold 250
```

Disable Rich colors and styling:

```bash
python3 -m bewiki_biblio run gvb1 --no-color
```

## Run Controls

- Running `python3 -m bewiki_biblio` with no arguments opens an interactive startup wizard.
- The startup wizard lets you:
  - select one, many, or all sources with a checkbox list
  - choose dry-run, interactive apply, or background apply mode
  - choose runner flags before the run starts
  - review the equivalent command preview before confirming
- Dry-run is the default.
- `--apply` enables saving.
- `--apply` without `--yes` keeps the per-page review loop.
- `--all` runs every configured source in discovery order.
- `--minor-threshold` controls when saved edits are marked minor, based on changed UTF-8 bytes.
- `--skip-review-required` skips manual-review matches during apply instead of prompting for them.
- when you run multiple sources, they are processed in the order you entered them
- in a multi-source `--apply` run, pressing `a` saves all remaining matched pages across the rest of the entered sources, but only for matches that do not require manual review
- in a dry-run `--learn-variants` run, both unknown candidates and review-required heuristic matches can be sent to `review_variants.json` for later exact replacement
- During interactive apply runs:
  - `y` saves the current page
  - `n` skips the current page
  - `a` saves the current and all remaining safe matches
  - `e` edits the run summary for the remaining pages
  - `q` stops the run
- Heuristic regex rules can mark a match as review-required in `source.toml`.
- Entry-based replacements also compare the extracted entry with the page title.
- If the entry and page title do not match exactly after conservative whitespace/dash normalization, the page is paused for manual review even after `a` or `--yes`.
- If you learn a review-required match into `review_variants.json`, that exact line is applied before heuristic regex rules on the next run.

## Adding a New Source

1. Create `sources/<source_id>/`.
2. Add `source.toml` with `[source]`, `[search]`, `[candidate]`, `[replacement]`, `[summary]`, `[pages]`, `[normalization]`, `[macros]`, and `[[regex_rules]]`.
3. Add `sources/<source_id>/README.md` with operator notes and examples.
4. Optionally create `rules.json`, `review_variants.json`, and `ignored_variants.json` locally, or let the workflow create them on first use.
5. Add or update tests covering the new source behavior.

`source.toml` and `README.md` are the persistent source definition. The JSON state files are local machine-managed runtime data and are gitignored.

## Source Scaffolding

`add-source` is the interactive bootstrap command for a new bibliography source. It should create the canonical source folder and canonical filenames:

- `sources/<source_id>/source.toml`
- `sources/<source_id>/README.md`

It also creates local runtime state files for convenience:

- `sources/<source_id>/rules.json`
- `sources/<source_id>/review_variants.json`
- `sources/<source_id>/ignored_variants.json`

Those JSON files are gitignored and do not need to be committed.

The scaffold keeps search-term prompts blank. Candidate prompts are then guessed from what you entered:

- `must_contain_all` defaults to the first strong text term
- `must_contain_any` defaults to the ISBNs plus remaining text terms

These defaults come from the current scaffold answers, not from any existing source folder.

The folder name must be source-id-safe: lowercase ASCII letters, digits, and hyphens only. The scaffold should reject unsafe names instead of trying to normalize them silently.

## Validation

`validate` checks that the source tree follows the repository convention:

- each source lives in `sources/<source_id>/`
- the directory name matches `source.toml`'s `[source].id`
- persistent files exist under their canonical names
- obvious misnamings such as `readme.md` are reported as invalid

Validation exits nonzero when the source layout is incomplete or misnamed.

## `source.toml` Shape

- `[search]`:
  - `insource_terms` are always added to the generated query
  - `isbns` and `keywords` are convenience lists appended to the same query
- `[candidate]`:
  - `must_contain_all` is used for review/debug candidate detection
  - `must_contain_any` is an additional broadening/narrowing layer independent from search generation
- `[argument_extractors.<name>]`:
  - declares extra template arguments beyond `entry` and `pages`
  - each extractor can read values from template parameter aliases and/or regex `patterns`
  - `normalizer` can be `entry`, `pages`, `whitespace`, or `raw`
- `[macros]`:
  - regex rules may reference `{{MACRO_NAME}}`
  - built-in structural macros are available automatically: `LIST_PREFIX`, `WS`, `OPT_WS`, `SEP`, `DASH`, `OPT_DASH`, `PAGES`, `YEAR4`, `ISBN_TOKEN`
  - built-in names are reserved and cannot be overridden

Regex rules are compiled once at source-load time after recursive macro expansion. They can also capture extra named groups such as `author` or `responsible`; if those names appear in the replacement template, the shared renderer will fill them automatically.
Rules can additionally set `review_required = true` and an optional `review_note` to force interactive confirmation for heuristic matches.

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
