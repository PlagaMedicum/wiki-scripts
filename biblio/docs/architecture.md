# Architecture

Read this with:

- [Project README](../README.md)
- [Documentation index](README.md)
- [Page save boundary](page-save-boundary.md)
- [Architecture review and proposals](architecture-review.md)

## Vision

The `biblio` project hosts reusable bibliography replacement tools that were first developed for
be.wikipedia.org and are intended to be retargetable to other local wikis.
Each source-specific bibliography family lives in its own folder, while a shared CLI and engine
handle wiki login, search, normalization, replacement, review state, diffs, and operator prompts.

The goal is to make new bibliography replacers mostly declarative:

- describe the source in `source.toml`
- keep machine state in local JSON files
- reuse the same English operator CLI
- preserve Belarusian wiki-facing behavior where needed

## Module Map

These are the main moving parts in the current codebase:

- `cli.py`: parser, subcommands, and no-argument startup wizard handoff
- `startup.py`: interactive run setup and wizard presentation
- `runtime.py`: wiki-client wrappers, site-client pooling, direct page-save transport, and
  injected dependency wiring
- `page_analysis.py`: explicit page-analysis objects, replacement analysis, and manual-review lookup
- `page_execution.py`: diff display and dry-run review learning
- `page_save.py`: save-policy decisions, `PageEdit` planning, and post-save rule promotion
- `session.py`: explicit session-policy objects, summary overrides, and save/quit state
- `workflow.py`: source orchestration and page iteration
- `manage_*.py`: source-scaffold prompting, rendering, writing, and validation reports
- `state.py` and `runtime_json.py`: durable local state loading, caching, and atomic writes

## Folder Layout

```text
biblio/
  README.md
  docs/
    README.md
    architecture.md
    architecture-review.md
  Makefile
  pyproject.toml
  .env
  biblio/
    bootstrap.py
    cli.py
    engine.py
    manage.py
    manage_questions.py
    manage_render.py
    manage_reports.py
    manage_write.py
    query.py
    runner.py
    runtime.py
    runtime_json.py
    page_analysis.py
    page_execution.py
    page_save.py
    source_templates.py
    session.py
    specs.py
    startup.py
    state.py
    text.py
    ui.py
    workflow.py
  sources/
    gvb1/
      source.toml
      README.md
      rules.json
      review_variants.json
      ignored_variants.json
    gvb2/
      ...
  tests/
    ...
```

## Source Lifecycle

1. The operator selects one source ID, multiple source IDs, or `--all`.
   A no-argument startup wizard is also available and can gather the same choices interactively.
2. The CLI loads `sources/<source_id>/source.toml`.
3. `add-source` can create a fresh `sources/<source_id>/` scaffold with the tracked definition
   files plus empty local runtime JSON files. The command is split into four source-management
   steps: prompt collection, scaffold rendering, file writing, and report rendering.
4. `validate` checks that existing source folders follow the repository conventions for persistent
   files and reports missing or misnamed files.
5. The query builder generates an `insource:` query from configured search terms unless `--query`
   overrides it.
6. Pywikibot logs into the target wiki using `.env` credentials and a runtime-generated `.pywikibot/`
   config directory.
7. The startup and runtime layers build run options, session policy, and wiki-client state before
   any page work begins.
8. The workflow layer searches matching pages, loads page text, and hands the text to the page
   analysis layer.
9. The page-analysis layer executes replacement detection, augments review reasons, and collects
   manual-review candidates.
10. The page-execution layer shows diffs, handles dry-run review learning, and hands apply runs to
   the page-save layer.
11. The page-save layer applies review and prompt policy, builds `PageEdit` requests, calls the
   runtime wiki client transport, persists line-exact promotions, and updates save/error counters.
12. The session policy layer decides whether matched pages can be auto-saved, whether to prompt,
   whether to carry summary overrides forward, and whether the run should stop.
13. The Rich UI shows colored diffs, replacement metadata, progress, and interactive prompts.
14. When `--learn-variants` is enabled, unknown candidates and manual-review heuristic matches can
   be added to review or ignore state.
15. Promoted line-exact rules are persisted back into the local `rules.json` runtime file after
   successful saves.
16. Heuristic matches can still pause for confirmation if a rule is marked review-required or if an
   extracted entry does not match the page title closely enough.
17. `--skip-review-required` lets unattended apply runs save only safe matches and leave
   review-required pages untouched for a later pass.

## Config And State Separation

### `source.toml`

Hand-authored and reviewed by humans. These are the persistent source files that belong in git:

- source identity and target wiki
- generated search terms
- independent candidate-detection terms
- replacement template forms
- default Belarusian edit summary format
- page-number extraction patterns
- optional extra-argument extractors for source-specific template parameters
- normalization toggles and alias normalization
- source-local regex macros
- declarative regex replacements with required rule names

The source scaffold and validation commands both assume canonical filenames:

- `source.toml`
- `README.md`

This convention keeps the folder predictable for automation and for future source generators.

### JSON State

Machine-managed, local to the operator, and gitignored:

- `rules.json`: active exact-match rules
- `review_variants.json`: raw candidate bibliography lines waiting to be promoted
- `ignored_variants.json`: hashes of rejected candidates

Runtime JSON is loaded through explicit typed helpers, written atomically, and rejected with a
clear error when malformed instead of silently resetting to empty state.

## Normalization And Page Extraction

The shared text pipeline removes common wiki markup noise before comparison:

- strips `nowiki`
- resolves piped and plain wikilinks
- removes italic/bold apostrophes
- normalizes non-breaking spaces
- normalizes en/em dashes
- applies optional source-specific alias replacements

The normalization behavior is configurable per source through `[normalization]` booleans, so
future bibliography families can opt out of aggressive cleanup if their raw formatting matters for
matching.

Page extraction is source-driven. Each source can provide one or more patterns with a named `pages`
group, plus reject patterns for false-positive tails such as illustration extents. Page patterns are
compiled once when the source is loaded.

Additional template arguments are also source-driven. A source can declare
`[argument_extractors.<name>]` subtables for placeholders such as `author`, `responsible`, or future
source-specific fields. Extractors can read from template parameters and/or regex patterns, which
keeps the renderer and exact-rule promotion path expandable without introducing source-specific
Python code.

## Replacement Flow

The engine applies three layers in order:

1. line-exact rules derived from `rules.json` plus promoted `review_variants.json`
2. declarative regex rules from `source.toml`
3. normalized-unit regex rules against full candidate blocks when raw-text regex matching misses a
   formatting variant

Persisted `rules.json` replacements are now treated as authoritative stored replacements. Synthetic
rules derived from `review_variants.json` are still rendered dynamically from the current source
definition.

Regex-rule replacements can use named match groups and the shared `{template}` token. The shared
engine renders the correct template form depending on whether a `pages` group was captured.
If a regex rule captures extra named groups like `author` or `responsible`, those values are passed
into the shared template renderer as well.

Regex rules are macro-aware:

- every `[[regex_rules]].pattern` is expanded through `[macros]`
- built-in macros cover structural fragments only
- bibliography-specific fragments must live in the source file
- macro expansion is recursive, with undefined-macro and cycle detection at load time

Regex rules can also declare `review_required = true` with an optional `review_note`. This is
intended for broad but heuristic matches such as "entry before `//`" patterns. Those matches still
render automatically in dry-runs, but interactive apply mode will stop for confirmation even after
bulk-accept. The runner also compares extracted `entry` arguments with the page title using
conservative normalization; mismatches are treated as manual-review cases as well.

When an operator confirms that a review-required match is correct during a dry-run
`--learn-variants` pass, the matched normalized line can be stored in `review_variants.json`. On
later runs, that learned exact line is applied before heuristic regex rules, so the operator can
gradually turn reviewed heuristic matches into unattended exact replacements.

Candidate detection for review/debug flows is intentionally separate from query generation. Search
terms help find candidate pages, while `[candidate]` terms decide whether a specific source line
looks like the target bibliography.

## CLI UX Rules

- The operator CLI is English.
- The wiki-facing edits remain Belarusian where required.
- Dry-run is the default.
- Running the CLI with no arguments opens an interactive startup wizard for source selection and
  run-mode setup.
- Rich is used for:
  - startup panels
  - source and flag checklist screens
  - progress tracking
  - colored unified diffs
  - variant review panels
  - final summary tables
- `--no-color` keeps the same flow without terminal styling.
- `--skip-review-required` is the unattended mode for background apply runs. It suppresses prompts
  for manual-review pages and counts them as skipped instead.

## Development Tooling

- Ruff is the standard Python linter and formatter for this project.
- `make run` is the canonical human entry point and opens the interactive wizard when no source is
  supplied.
- `make list`, `make validate`, and `make add-source` cover the source-management workflow.
- `make test` runs the test suite.
- `make lint` runs `ruff check .` and `ruff format --check .`.
- `make format` applies safe Ruff fixes and formatting to the Python tree.
- `make check` runs tests and linting before a commit.
- The repo-wide `.gitignore` excludes Ruff cache, packaging artifacts, coverage output, local
  virtual environments, and per-source runtime JSON state.

## Extending The System

To add a new source, use `add-source` for the initial scaffold or copy an existing per-book source
such as `sources/gvb1/`, then tailor `source.toml`, validate the layout, and add tests for
normalization, page extraction, replacement rendering, and CLI output relevant to that source.
