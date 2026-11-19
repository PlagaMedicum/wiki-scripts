# agentic-bot

_AI-assisted documentation._

A lightweight, persistent, terminal-based Wikipedia edit proposal and review system.

Designed for supervised AI workflows where an assistant (Codex) investigates issues and prepares edit proposals, while the operator independently reviews, modifies, approves, declines, or publishes them through a colorized terminal interface.

## Core Invariants & Safety Policies

- **Human Review**: CLI and dashboard approval/publication require an interactive terminal. This is an operator safeguard, not a sandbox against code calling library APIs directly.
- **Durable History**: Declined proposals are never deleted. Rejection rationale and complete version histories are preserved.
- **Fail-Closed Verification**: Publication checks page freshness and blocks unresolved merge markers.
- **Interface Rights Guard**: Editing `MediaWiki:` JavaScript and CSS requires the corresponding interface-administrator rights.
- **Explicit Confirmation & Approval**: Every publication requires an interactive terminal, prior explicit approval, and confirmation (`[y/N]`). Only approved, unchanged proposals can be published; pending proposals must be approved before publication, and declined, conflicted, and published proposals must first be reopened.
- **Unicode & Wikitext Preservation**: Full preservation of Belarusian Cyrillic characters (e.g. `і`, `ў`, `'`), wikitext syntax, and indentation.

## Workflow

```text
1. Investigate  → Read-only page retrieval via MediaWiki API
2. Propose      → Create persistent proposal (page snapshot, proposed text, summary, rationale)
3. Review       → Interactive terminal UI displaying colorized unified diff
4. Edit         → Modify proposed content or summary in Vim ($VISUAL / $EDITOR)
5. Approve      → Mark proposal as approved for publication
6. Decline      → Mark proposal as declined with optional rejection reasons
7. Reopen       → Revisit and reopen declined proposals
8. Publish      → Submit edit to MediaWiki after freshness and permission checks
```

Before adding or changing a template invocation, check its current Belarusian
Wikipedia documentation for supported parameters and generated output; inspect
the implementation or rendered result when the documentation is insufficient.
Do not duplicate headings or other markup the template supplies. For example,
[`{{зноскі}}`](https://be.wikipedia.org/wiki/Шаблон:Зноскі) already generates
the “Зноскі” section heading: use it without a separate `== Зноскі ==` above.
Template existence and TemplateData validation alone do not establish correct usage.

When preparing Belarusian Wikipedia proposals, if a linked article is absent
locally but an equivalent article exists in another Wikipedia, use
[`{{Нп5}}`](https://be.wikipedia.org/wiki/Шаблон:Нп5):
`{{Нп5|Belarusian title|display text|language code|foreign article title}}`.
Parameter 2 may be empty to display parameter 1. Verify local absence (including
redirects), the foreign article's existence and that it covers the same subject;
preserve the intended link text. Record the checked pages in the rationale.
Never guess the foreign target; if it cannot be verified, report the gap.
This is proposal-preparation guidance, not an automatic validator rewrite.

## Quick Start (Single Entrypoint)

From the repository root:

```bash
make agentic-bot           # Launches interactive dashboard directly
./agentic-bot/agentic-bot  # Direct executable launcher
```

Or from `agentic-bot/`:

```bash
make run                   # Launches interactive dashboard directly
./agentic-bot              # Direct executable launcher
```

When started with no arguments, `agentic-bot` presents the **Interactive Proposals Dashboard**:
- Previews proposal IDs, status, diff line counts, test-status claims from rationale text, page titles, and agent rationale notes. Test badges are not independently verified.
- Starts with **ACTIVE** proposals: pending, approved and conflicted. Published and declined proposals appear only after selecting them with `f` (or selecting ALL). `list` uses the same default; `list --status published`, `--status declined` or `--status all` explicitly includes archived work.
- Use arrow keys to select a proposal, Enter to inspect it (and approve with `a`), `p` to publish approved proposals with confirmation, `d` to decline, `e` to edit, `o` to open its page, and `q` to quit.
- The dashboard renders a terminal-sized window of proposals, keeping the selected row and controls visible; arrow navigation crosses windows automatically. ID, status, page and issue retain space even for long text. Below 100 columns, mode, diff and test-claim columns are omitted; open the proposal for those details. Long cells are ellipsized.
- If the terminal cannot fit a usable view, a resize/back/quit hint replaces the frame.
- The mouse wheel selects proposals on the dashboard and scrolls content in details,
  like Up/Down (one row/line per event). Requires terminal mouse-reporting support.
  Mouse capture is released for prompts, Vim and exit; other mouse events are ignored.

Control colours are consistent across dashboard and details: neutral/white for
navigation and view filters, cyan for inspection (Validate, Browser), yellow for
changes (Edit, Rebase, Summary, Toggle Bot), green for Approve/Publish, and red for
Decline. Green controls do not imply validation has passed or bypass confirmation.
Status/validation colours use yellow for pending or incomplete, green for accepted,
published or successful, and red for declined, conflicts or errors. Diff additions
are green and removals red; labels and `+`/`-` remain the primary cues without colour.

## Vim Editing (Pull & Merge)

When inspecting a proposal, pressing `[e]` to edit in Vim:
1. Re-fetches the latest live revision from Wikipedia.
2. If another proposal was published or the page was edited, automatically performs a standard 3-way merge (`git merge-file`).
3. If clean, merges seamlessly; if conflicting, inserts standard conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`) for you to resolve in Vim.
4. On save, updates the proposal's base revision to the live revision.
5. Publishing still checks for newer revisions and unresolved conflict markers; an edit conflict can occur if the page changes again.

Fetch failures stop the edit with an explanation rather than silently using
an old revision. Merges invalidate approval; conflict markers block it until
resolved. Article temporary files use `.wiki`, which Vim detects as
`mediawiki` for its built-in syntax highlighting; JS/CSS suffixes are unchanged.
`VISUAL` / `EDITOR` may include arguments (including quoted arguments); they
are passed directly to the editor without invoking a shell.
Editor launch/exit failures return to the review screen with an explanation,
without saving the attempted edit or rebase.

## Proposal Detail Actions

- `[c]` Run remote validation explicitly and show scrollable diagnostics.
- `[a]` Approve proposal for publication.
- `[p]` Approve a pending proposal and then publish it in the same action, with separate explicit approval and publication confirmations and fresh validation at each step. Already-approved proposals go directly to publication confirmation. Cancelling publication retains approval.
- `[d]` Discard / decline (prompts for optional rejection rationale, keeps durable history).
- `[e]` Edit in Vim with automatic pull-and-merge.
- `[r]` Rebase onto the latest live revision (3-way merge without editing; unresolved conflicts must be fixed with `[e]`).
- `[m]` Edit edit summary in Vim.
- `[o]` Open the affected Wikipedia page URL in your default browser.
- `[b]` Back to dashboard.
- `[q]` Quit.

## Proposal Validation

Proposals are validated against the target wiki before human approval:
newly introduced internal links in any local namespace (missing pages,
redirect usage, section anchors), newly introduced templates (existence,
TemplateData parameter validity when available), and parser warnings from
`action=parse` rendering. Linked-page and template names come from the
parser's own `links`/`iwlinks`/`templates` output, so namespace prefixes,
magic words, and interwiki prefixes are resolved authoritatively rather than
by string heuristics; fragment names the parser does not list (plain-form
`[[en:...]]` interwiki links are invisible in its output) are classified via
`siteinfo interwikimap`. Only problems **newly introduced** relative to the
base revision are reported; pre-existing problems are ignored.
Inspection and navigation use local snapshots only: no wiki connection or
remote validation runs on open. Press `[c]` to validate explicitly. Content
edits/rebases make existing results stale without rerunning remote checks.
Approval and publication each run fresh validation before human confirmation,
including publication from the dashboard. Remote calls are synchronous and may
take several seconds: input waits until the requested operation completes.
Ordinary inspection and navigation remain local.

Confirmed missing transcluded templates/modules are errors that block approval
and publication. Missing internal page links are warnings requiring human
attention, not blockers: intentional red links are valid MediaWiki usage,
including links to template pages (as distinct from transclusions).
Redirects, section mismatches and unknown TemplateData parameters remain
warnings. Unverified checks remain non-blocking, but never report success.
The header distinguishes not-run, stale, failed and incomplete validation;
`[c]` opens detailed findings, also available in the `[v]` view cycle.

Limitations (by design):

- Wikitext pages only; other content models (JS/CSS/...) are skipped and
  reported as unverified.
- Section anchors are matched against `prop=sections` headings only;
  anchors from templates or raw HTML can produce false warnings, so
  mismatches are warnings and never block.
- Newly introduced interwiki links, categories, and file links are counted
  and reported as unverified (out of scope), as are newly introduced
  template invocations with nested arguments; fragment anchors and template
  named parameters — which the parser does not expose — come from regex
  extraction, not a wikitext parser.
- TemplateData checks run only where TemplateData exists; otherwise the
  parameter check is reported as unverified.
- API failures and unrecognised response shapes degrade every affected
  check to unverified — never to a false pass, and never to a block.

## Command-line Examples

```bash
make run ARGS="fetch MediaWiki:Gadget-wikificator.js -o wikificator.js"

# Create a proposal programmatically
make run ARGS="propose MediaWiki:Gadget-wikificator.js --content fix.js --summary 'Вікіфікатар: выпраўленне' --issue 'Arithmetic conversion' --rationale 'rationale.md'"
```

From repository root:

```bash
make agentic-bot-run ARGS="list"
make agentic-bot-test
make agentic-bot-check
```

## Storage Layout (`agentic-bot/proposals/`)

Each proposal lives in a dedicated directory:

```text
proposals/
└── 001/
    ├── proposal.json        # Machine-readable metadata & decision history
    ├── original.txt         # Verbatim original page content fetched from wiki
    ├── proposed.txt         # Current proposed content
    ├── summary.txt          # Current proposed edit summary
    ├── rationale.md         # Explanation and justification
    └── versions/            # Historical versions preserved across edits
        ├── v1/
        │   ├── proposed.txt
        │   ├── summary.txt
        │   └── rationale.md
        └── v2/
            └── ...
```

Proposals and existing local `.env` files are ignored by Git. Credentials can be
placed in `.env` in the repository root or in `~/.config/wiki-scripts/publisher.env`
(permissions `600`). When `.env` is absent in the tool root, `publisher.env` is
loaded by default. Authentication and cookies stay in memory; the isolated temporary
Pywikibot configuration contains no password. Restart the bot if its session expires
or Pywikibot was already initialized in the process. Existing credential and cookie
files from earlier versions are not removed.

## Testing & Quality Gates

```bash
make test    # Run pytest suite
make lint    # Run ruff check & ruff format --check
make check   # Aggregate quality gate
```

For TUI changes, reproduce the behavioral failure before repair, then run the
focused regression and `make check`. Exercise navigation, recovery and Vim in
an actual terminal at 80×24 and 120×40 with disposable proposals; never use live
approval/publication as a smoke test. Measure redraw time on synthetic large
proposals before adding performance machinery. Local `AGENTS.md` defines
maintenance safeguards; this README owns operator workflow.
