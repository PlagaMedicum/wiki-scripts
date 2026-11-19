# svg-replacer

_AI-assisted tool; review its proposals before publishing._

Interactive terminal tool for replacing raster images (PNG/JPG/…) with their
existing SVG equivalents on Wikimedia projects. It starts from a Commons SVG
URL, identifies the original raster, finds pages that use the raster, and walks
the operator through one reviewed, approved replacement at a time.

## Safety model

- **Nothing is written without an explicit publish decision.** The tool asks
  `Publish approved edits?` at startup (default no); `--apply` answers it up
  front. Even then every single edit requires an individual interactive
  `approve / skip / stop` decision. There is no bulk mode and no unattended
  publishing.
- **Preview mode is anonymous.** Discovery and previews never log in.
  Publishing logs in lazily per wiki; later reads use that wiki's session.
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
  Comment/literal-content tags (including attributed `<nowiki>`, `<pre>` and
  `<syntaxhighlight>`) are excluded from replacement and template-depth counting.
- **File identity.** The destination must be SVG and the source a different
  supported raster. Both must resolve to the intended Commons files on the target
  wiki; local files shadowing either name cause an abort.
  Equivalence judgment (language-specific graphics, partial vectorizations,
  incompatible diagrams) stays with the operator at approval time.

## Quick start

```bash
cd svg-replacer
uv sync --dev
make run
```

The tool first asks whether to publish (default no), then prompts for the
Commons SVG link. Answering yes — or `make run ARGS="--apply"` — sets PUBLISH
mode; each edit still asks individually. The yellow PREVIEW banner and
`[Enter/a] Preview (not saved)` mean no edit is sent; PUBLISH uses
`[Enter/a] Publish`. Pressing `Enter` approves the shown diff, nothing else.
Colours are automatic in terminals; `NO_COLOR` disables them.

From the repository root:

```bash
make svg-replacer-run
```

## Workflow

1. Fetch Commons metadata for the SVG and identify the original raster from the
   page's source/derivation information. If there is not exactly one candidate,
   the tool asks for the raster URL (`--raster` pre-fills it); it never guesses.
2. Show one Commons description-page link per file for visual comparison
   (confirmation required).
3. Query the MediaWiki GlobalUsage API for pages using the raster across every
   Wikimedia project (or only the editions named with `--wiki`), filtered to
   the selected namespaces (default 0).
4. List candidate titles; direct article uses come first, auto-skips are labelled.
5. Show each target link, exact unified diff (including surrounding context) and
   edit summary. Press `Enter` (or `a`) to approve — the action is Preview when
   publishing is off, Publish otherwise — `s` to skip, `q` to quit.
6. After the article loop, separately propose the Commons file-description page
   of the raster: add `{{Vector version available|Example.svg}}` on top and
   remove any stale `{{SVG}}`/`{{Convert to SVG}}` conversion-request marker
   (one diff, one approval). Existing equivalent notices are detected and never
   duplicated.
7. Summarize saved and previewed changes, including the separate Commons notice.
   Zero-count skip/failure details are omitted.

## Options

| Option | Meaning |
| --- | --- |
| `svg_url` | optional Commons SVG URL (or `File:` title); prompted when omitted |
| `--raster URL\|File:X.png` | original raster when discovery is ambiguous |
| `--wiki all\|en,ar` | wikis to scan (default `all`, every project using the file) |
| `--ns N` | namespace to search, repeatable (default `0`) |
| `--limit N` | max candidate pages to review (default `25`) |
| `--apply` | start in PUBLISH mode without the prompt (interactive terminal required) |
| `--env PATH` | credential file (default `biblio/.env` in the repository) |

Exit codes: `0` success, `1` API/credential failure or failed edits,
`2` invalid input, `130` interrupted.

## Credentials

Publishing loads `WIKI_BOT_USERNAME` (a BotPasswords login, `Username@label`)
and `WIKI_BOT_PASSWORD` from `biblio/.env`. The file is never copied and the
values are never printed or logged. Credentials are read only once publishing is
chosen, and each wiki (every edit target and Commons) authenticates its own
session separately — the bot password must be valid on each wiki you publish to.
Password representations and authentication errors omit secrets. Terminal
control characters in remote text are displayed as escapes, not executed.

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

- Raster discovery reads the SVG page's own wikitext: file links, file URLs and
  literal positional filenames in `{{Derived from|…}}`. Nested template
  expressions and derivation information elsewhere require manual raster input.
- Image uses inside template invocations (e.g. infobox `|image=`) are skipped
  by design; replace those manually if appropriate.
- Duplicate-vector detection recognizes `{{Vector version available}}`,
  `{{VVA}}` and `{{subst:…}}` spellings only. The Commons cleanup removes only
  the `{{SVG}}`/`{{Convert to SVG}}` marker family, outside comments and
  literal-content tags.
- Transient HTTP 429/503 throttling is retried on reads (3 bounded retries);
  login and edit requests are never retried automatically. Missing revision
  acknowledgements and explicit no-change responses are not counted as published.
- `--limit` stops discovery after enough eligible unique candidates are found.
  Earlier edits remain published if a later edit fails or the operator stops.
