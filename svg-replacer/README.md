# svg-replacer

_AI-assisted tool; review its proposals before publishing._

Interactive terminal tool for replacing raster images (PNG/JPG/…) with their
existing SVG equivalents on Wikimedia projects. It starts from a Commons SVG
URL, identifies the original raster, finds pages that use the raster, and walks
the operator through one reviewed, approved replacement at a time.

## Safety model

- **Read-only by default.** Nothing is written without `--apply`, and even with
  `--apply` every single edit requires an individual interactive
  `approve / skip / stop` decision. There is no bulk mode and no unattended
  publishing.
- **Viewing has zero side effects.** Discovery, listing, diff previews and
  navigation only issue anonymous read queries (no login, no tokens, no edits).
- **Conflict checks.** Before publishing, the current page revision is compared
  with the revision the diff was built from, and the same revision id is passed
  as `baserevid`; the server enforces it. Conflicts and API errors are reported
  as failed edits, never as successes.
- **Wikitext preservation.** Replacement rewrites only the filename span inside
  a direct `[[File:…]]`-style link. Namespace aliases, underscores, image
  options, captions, dimensions, Unicode (Belarusian text) and all surrounding
  wikitext stay byte-for-byte identical.
- **Conservative skipping.** Usages that are transcluded through a template,
  passed as template parameters, inside `<nowiki>`/comments, or not present in
  the page's own wikitext are skipped with a reason. Talk pages, user pages,
  templates and other non-article namespaces are excluded by default.
  Equivalence judgment (language-specific graphics, partial vectorizations,
  incompatible diagrams) stays with the operator at approval time.

## Quick start

```bash
cd svg-replacer
uv sync --dev
make run ARGS="https://commons.wikimedia.org/wiki/File:Example.svg"
```

From the repository root:

```bash
make svg-replacer-run ARGS="https://commons.wikimedia.org/wiki/File:Example.svg"
```

## Workflow

1. Fetch Commons metadata for the SVG and identify the original raster from the
   page's source/derivation information. If there is not exactly one candidate,
   the tool asks for the raster URL (`--raster` pre-fills it); it never guesses.
2. Verify that both files exist and print description-page, direct-file and
   thumbnail links for side-by-side visual comparison (confirmation required).
3. Query the MediaWiki GlobalUsage API for pages using the raster, filtered to
   the selected Wikipedia edition and namespace (default `be.wikipedia.org`,
   namespace 0).
4. List candidates with titles, links and usage context; direct article uses
   come first, auto-skips are labelled.
5. For each replaceable candidate: show the exact unified diff of the proposed
   wikitext change and ask for `approve / skip / stop`.
6. After the article loop, separately propose adding
   `{{Vector version available|Example.svg}}` to the raster's Commons
   file-description page (existing equivalent templates are detected and never
   duplicated) — own diff, own approval.
7. Print a final summary of published, dry-run, skipped, failed and
   not-processed items.

## Options

| Option | Meaning |
| --- | --- |
| `svg_url` | Commons URL (or `File:` title) of the SVG file |
| `--raster URL\|File:X.png` | original raster when discovery is ambiguous |
| `--wiki LANG` | Wikipedia edition (default `be`) |
| `--ns N` | namespace to search, repeatable (default `0`) |
| `--limit N` | max candidate pages to review (default `25`) |
| `--apply` | enable publishing; requires an interactive terminal |
| `--env PATH` | credential file (default `biblio/.env` in the repository) |

Exit codes: `0` success, `1` API/credential failure or failed edits,
`2` invalid input, `130` interrupted.

## Credentials

Publishing loads `WIKI_BOT_USERNAME` (a BotPasswords login, `Username@label`)
and `WIKI_BOT_PASSWORD` from `biblio/.env`. The file is never copied and the
values are never printed or logged. Credentials are read only when `--apply` is
given, and each wiki (the target Wikipedia and Commons) authenticates its own
session separately — the bot password must be valid on each wiki you publish to.

## Tests

```bash
make test    # unit tests, mocked API responses for all write paths
make lint
make check   # sync + test + lint
```

Read-only tests against the real Wikimedia APIs are opt-in and never edit:

```bash
SVG_REPLACER_LIVE=1 make test ARGS="tests/test_live_readonly.py"
```

## Known limitations

- Raster discovery reads the SVG page's own wikitext (file links and Commons /
  upload URLs in the source fields). Derivation info recorded elsewhere is not
  guessed at: the tool asks for the raster URL instead.
- Image uses inside template invocations (e.g. infobox `|image=`) are skipped
  by design; replace those manually if appropriate.
- Duplicate-vector detection recognizes `{{Vector version available}}`,
  `{{VVA}}` and `{{subst:…}}` spellings only.
- Transient HTTP 429/503 throttling is retried on reads (2 bounded retries);
  login and edit requests are never retried automatically — a throttled edit is
  reported as failed so the operator can decide.
