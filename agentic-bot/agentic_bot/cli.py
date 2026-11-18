from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from agentic_bot.editor import edit_text_in_editor
from agentic_bot.review import (
    confirm_publication,
    get_file_suffix_for_page,
    interactive_dashboard_loop,
    pull_and_merge_for_edit,
    render_dashboard,
    render_proposal_card,
    review_proposal_interactive,
)
from agentic_bot.store import ProposalStore
from agentic_bot.wiki import EditConflictDetectedError, InsufficientPermissionsError, WikiClient


def cmd_dashboard(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    interactive_dashboard_loop(console, store)
    return 0


def cmd_list(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    render_dashboard(console, store)
    return 0


def cmd_show(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    try:
        proposal = store.load(args.id)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1

    render_proposal_card(console, proposal)
    return 0


def cmd_review(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    if args.id:
        try:
            proposal = store.load(args.id)
        except FileNotFoundError as exc:
            console.print(f"[bold red]Error: {exc}[/bold red]")
            return 1
        review_proposal_interactive(console, proposal, store)
        return 0

    interactive_dashboard_loop(console, store)
    return 0


def cmd_edit(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    try:
        proposal = store.load(args.id)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1

    try:
        wiki = WikiClient(
            site_lang=proposal.page.site_lang,
            family=proposal.page.family,
        )
    except Exception:
        wiki = None

    if wiki is not None:
        text_to_edit, was_rebased, live_snapshot = pull_and_merge_for_edit(
            console, proposal, store, wiki
        )
    else:
        text_to_edit, was_rebased, live_snapshot = proposal.proposed_content, False, proposal.page

    suffix = get_file_suffix_for_page(proposal.page.title)
    new_content, modified = edit_text_in_editor(text_to_edit, suffix=suffix)

    if modified or was_rebased:
        if was_rebased:
            proposal = store.rebase_base_page(
                proposal.id,
                new_snapshot=live_snapshot,
                new_proposed_content=new_content,
            )
            console.print(
                f"[bold green]Rebased proposal #{proposal.id} onto live revision "
                f"{live_snapshot.revid} (v{proposal.current_version})![/bold green]"
            )
        else:
            proposal = store.update_content(proposal.id, new_content, action="cli_edit")
            console.print(
                f"[green]Saved version v{proposal.current_version} for #{proposal.id}. "
                "Status reset to PENDING.[/green]"
            )
    else:
        console.print("[dim]No changes made.[/dim]")
    return 0


def cmd_summary(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    try:
        proposal = store.load(args.id)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1

    new_summary, modified = edit_text_in_editor(proposal.edit_summary, suffix=".txt")
    if modified and new_summary.strip():
        store.update_summary(proposal.id, new_summary.strip())
        console.print(f"[green]Updated edit summary for #{proposal.id}.[/green]")
    else:
        console.print("[dim]No changes made.[/dim]")
    return 0


def cmd_approve(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        console.print("[red]Approval requires an interactive terminal.[/red]")
        return 1
    try:
        proposal = store.load(args.id)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1

    if proposal.status == "approved":
        console.print(f"[green]Proposal #{proposal.id} is already APPROVED.[/green]")
        return 0
    if proposal.status != "pending":
        console.print(
            f"[red]Cannot approve proposal #{proposal.id} in '{proposal.status}' state. "
            "Reopen it first.[/red]"
        )
        return 1
    if "<<<<<<<" in proposal.proposed_content or ">>>>>>>" in proposal.proposed_content:
        console.print(
            f"[bold red]Cannot approve proposal #{proposal.id}: unresolved merge conflict markers.[/bold red]"
        )
        return 1

    # Display exact proposed diff and edit summary before confirmation
    render_proposal_card(console, proposal)

    from rich.prompt import Confirm

    confirmed = Confirm.ask(
        f"[bold green]Approve proposal #{proposal.id} for publication?[/bold green]",
        default=False,
        console=console,
    )
    if not confirmed:
        console.print(f"[yellow]Approval cancelled for proposal #{proposal.id}.[/yellow]")
        return 0

    proposal = store.set_status(args.id, "approved", reason="Approved via CLI")
    console.print(f"[green]Proposal #{proposal.id} marked as APPROVED.[/green]")
    return 0


def cmd_decline(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    try:
        proposal = store.set_status(args.id, "declined", reason=args.reason or "Declined via CLI")
        console.print(f"[red]Proposal #{proposal.id} marked as DECLINED.[/red]")
        return 0
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1


def cmd_reopen(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    try:
        proposal = store.set_status(args.id, "pending", reason="Reopened via CLI")
        console.print(f"[yellow]Proposal #{proposal.id} reopened (status: PENDING).[/yellow]")
        return 0
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1


def cmd_publish(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    try:
        proposal = store.load(args.id)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        return 1

    if proposal.status != "approved":
        if proposal.status == "pending":
            console.print(
                f"[yellow]Proposal #{proposal.id} is pending. "
                "Approve it first before publishing.[/yellow]"
            )
        else:
            console.print("[red]Reopen the proposal before publishing.[/red]")
        return 1
    if not args.dry_run:
        confirmed = confirm_publication(console, proposal)
        if confirmed is None:
            return 1
        if not confirmed:
            return 0

    wiki = WikiClient(
        site_lang=proposal.page.site_lang,
        family=proposal.page.family,
    )

    try:
        console.print(f"[cyan]Connecting to {proposal.page.wiki}...[/cyan]")
        new_revid, ts = wiki.publish_page(
            title=proposal.page.title,
            text=proposal.proposed_content,
            summary=proposal.edit_summary,
            expected_revid=proposal.page.revid,
            dry_run=args.dry_run,
            mark_as_bot=proposal.mark_as_bot,
        )

        if args.dry_run:
            console.print(
                f"[bold green]DRY-RUN SUCCESS: Preflight passed for #{proposal.id} "
                f"(current rev: {new_revid}). No edits made.[/bold green]"
            )
            return 0

        proposal = store.record_publication(proposal.id, new_revid, ts)
        console.print(
            f"[bold green]SUCCESS: Proposal #{proposal.id} published as revision {new_revid}![/bold green]"
        )
        return 0
    except EditConflictDetectedError as exc:
        console.print(f"[bold red]CONFLICT: {exc}[/bold red]")
        console.print(
            "[yellow]Hint: Use 'agentic-bot edit "
            f"{proposal.id}' to pull the latest wiki revision and 3-way merge automatically.[/yellow]"
        )
        store.set_status(proposal.id, "conflict", reason=str(exc))
        return 2
    except InsufficientPermissionsError as exc:
        console.print(f"[bold red]PERMISSION ERROR: {exc}[/bold red]")
        return 3
    except Exception as exc:
        console.print(f"[bold red]ERROR: {exc}[/bold red]")
        return 1


def cmd_fetch(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    wiki = WikiClient(site_lang=args.lang, family=args.family)
    try:
        console.print(f"Fetching '{args.title}' from {args.lang}.{args.family}.org...")
        snapshot = wiki.fetch_page(args.title)
        console.print(
            f"[green]Retrieved '{snapshot.title}'[/green] (revid: {snapshot.revid}, {snapshot.timestamp})"
        )
        if args.output:
            Path(args.output).write_text(snapshot.content, encoding="utf-8")
            console.print(f"Saved content to {args.output}")
        return 0
    except Exception as exc:
        console.print(f"[bold red]Fetch failed: {exc}[/bold red]")
        return 1


def cmd_propose(args: argparse.Namespace, store: ProposalStore, console: Console) -> int:
    wiki = WikiClient(site_lang=args.lang, family=args.family)
    try:
        console.print(f"Fetching base page '{args.title}'...")
        snapshot = wiki.fetch_page(args.title)
    except Exception as exc:
        console.print(f"[bold red]Failed to fetch base page: {exc}[/bold red]")
        return 1

    content_path = Path(args.content)
    if not content_path.exists():
        console.print(f"[bold red]Proposed content file not found: {content_path}[/bold red]")
        return 1
    proposed_content = content_path.read_text(encoding="utf-8")

    rationale = ""
    if args.rationale:
        r_path = Path(args.rationale)
        if r_path.exists():
            rationale = r_path.read_text(encoding="utf-8")
        else:
            rationale = args.rationale

    mark_as_bot = None
    if getattr(args, "bot", False):
        mark_as_bot = True
    elif getattr(args, "critical", False):
        mark_as_bot = False

    proposal = store.create(
        page=snapshot,
        proposed_content=proposed_content,
        edit_summary=args.summary,
        rationale=rationale,
        issue=args.issue,
        mark_as_bot=mark_as_bot,
    )
    console.print(
        f"[bold green]Created proposal #{proposal.id} for '{snapshot.title}'[/bold green]"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-bot",
        description="Terminal-based Wikipedia edit proposal and review system.",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    # dashboard
    subparsers.add_parser("dashboard", help="Interactive proposal dashboard (default)")

    # list
    p_list = subparsers.add_parser("list", help="List edit proposals table")
    p_list.add_argument(
        "--status",
        choices=["pending", "approved", "declined", "published", "conflict", "all"],
        default="all",
        help="Filter by status (default: all)",
    )

    # show
    p_show = subparsers.add_parser("show", help="Show proposal details and diff")
    p_show.add_argument("id", help="Proposal ID (e.g. 001)")

    # review
    p_review = subparsers.add_parser("review", help="Interactive terminal review")
    p_review.add_argument("id", nargs="?", help="Specific proposal ID to review")

    # edit
    p_edit = subparsers.add_parser("edit", help="Edit proposed content in Vim (pulls latest wiki)")
    p_edit.add_argument("id", help="Proposal ID")

    # summary
    p_summary = subparsers.add_parser("summary", help="Edit proposal edit summary in Vim")
    p_summary.add_argument("id", help="Proposal ID")

    # approve
    p_approve = subparsers.add_parser("approve", help="Mark proposal as approved")
    p_approve.add_argument("id", help="Proposal ID")

    # decline
    p_decline = subparsers.add_parser("decline", help="Decline a proposal")
    p_decline.add_argument("id", help="Proposal ID")
    p_decline.add_argument("--reason", default="", help="Optional rejection rationale")

    # reopen
    p_reopen = subparsers.add_parser("reopen", help="Reopen a declined proposal")
    p_reopen.add_argument("id", help="Proposal ID")

    # publish
    p_publish = subparsers.add_parser("publish", help="Publish an approved proposal to Wikipedia")
    p_publish.add_argument("id", help="Proposal ID")
    p_publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate permissions and freshness without submitting edit",
    )
    p_publish.add_argument(
        "--force",
        action="store_true",
        help="Allow pending proposals after interactive confirmation",
    )

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch a page source and metadata")
    p_fetch.add_argument("title", help="Page title")
    p_fetch.add_argument("--output", "-o", help="Save page content to file")
    p_fetch.add_argument("--lang", default="be", help="Wiki language (default: be)")
    p_fetch.add_argument("--family", default="wikipedia", help="Wiki family (default: wikipedia)")

    # propose
    p_propose = subparsers.add_parser("propose", help="Create a new edit proposal")
    p_propose.add_argument("title", help="Target page title")
    p_propose.add_argument("--content", required=True, help="File with proposed page content")
    p_propose.add_argument("--summary", required=True, help="Proposed edit summary")
    p_propose.add_argument("--issue", required=True, help="Short issue description")
    p_propose.add_argument(
        "--rationale", default="", help="Rationale text or path to markdown file"
    )
    p_propose.add_argument(
        "--bot",
        action="store_true",
        help="Mark edit as routine bot edit (hidden from watchlists)",
    )
    p_propose.add_argument(
        "--critical",
        action="store_true",
        help="Mark edit as critical edit (visible on watchlists)",
    )
    p_propose.add_argument("--lang", default="be", help="Wiki language (default: be)")
    p_propose.add_argument("--family", default="wikipedia", help="Wiki family (default: wikipedia)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()
    store = ProposalStore()

    if not args.command:
        # Single entrypoint default: launch interactive dashboard!
        interactive_dashboard_loop(console, store)
        return 0

    handlers = {
        "dashboard": cmd_dashboard,
        "list": cmd_list,
        "show": cmd_show,
        "review": cmd_review,
        "edit": cmd_edit,
        "summary": cmd_summary,
        "approve": cmd_approve,
        "decline": cmd_decline,
        "reopen": cmd_reopen,
        "publish": cmd_publish,
        "fetch": cmd_fetch,
        "propose": cmd_propose,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args, store, console)
    return 1


if __name__ == "__main__":
    sys.exit(main())
