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
- Use arrow keys to select a proposal, Enter to inspect it, `a` to approve, `p` to publish approved proposals with confirmation, `d` to decline, `e` to edit, `o` to open its page, and `q` to quit.

## Vim Editing (Pull & Merge)

When inspecting a proposal, pressing `[e]` to edit in Vim:
1. Re-fetches the latest live revision from Wikipedia.
2. If another proposal was published or the page was edited, automatically performs a standard 3-way merge (`git merge-file`).
3. If clean, merges seamlessly; if conflicting, inserts standard conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`) for you to resolve in Vim.
4. On save, updates the proposal's base revision to the live revision.
5. Publishing still checks for newer revisions and unresolved conflict markers; an edit conflict can occur if the page changes again.

## Proposal Detail Actions

- `[a]` Approve proposal for publication.
- `[p]` Publish / apply to Wikipedia (verifies approval, freshness, and interface permissions, requires explicit `[y/N]` confirmation).
- `[d]` Discard / decline (prompts for optional rejection rationale, keeps durable history).
- `[e]` Edit in Vim with automatic pull-and-merge.
- `[m]` Edit edit summary in Vim.
- `[o]` Open the affected Wikipedia page URL in your default browser.
- `[b]` Back to dashboard.
- `[q]` Quit.

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

Proposals and existing local `.env` files are ignored by Git. Prefer environment
variables for credentials. Authentication and cookies stay in memory; the
isolated temporary Pywikibot configuration contains no password. Restart the bot
if its session expires or Pywikibot was already initialized in the process.
Existing credential and cookie files from earlier versions are not removed.

## Testing & Quality Gates

```bash
make test    # Run pytest suite
make lint    # Run ruff check & ruff format --check
make check   # Aggregate quality gate
```
