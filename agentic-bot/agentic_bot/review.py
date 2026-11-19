from __future__ import annotations

import re
import shutil
import sys
import webbrowser
from functools import lru_cache
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from agentic_bot.diff import compute_diff_stats, format_diff_lines
from agentic_bot.editor import edit_text_in_editor
from agentic_bot.merge import has_conflict_markers, three_way_merge
from agentic_bot.models import PageSnapshot, Proposal
from agentic_bot.store import ProposalStore
from agentic_bot.tui import alternate_screen, format_badge, read_key
from agentic_bot.wiki import EditConflictDetectedError, InsufficientPermissionsError, WikiClient


def get_file_suffix_for_page(title: str) -> str:
    if title.endswith(".js"):
        return ".js"
    if title.endswith(".css"):
        return ".css"
    return ".txt"


def approval_block_reason(proposal: Proposal) -> str | None:
    """Return why approval is blocked, or None when the proposal is approvable."""
    if proposal.status != "pending":
        return (
            f"Only pending proposals can be approved (status: {proposal.status.upper()}) "
            "— reopen it first."
        )
    if has_conflict_markers(proposal.proposed_content):
        return (
            "Unresolved conflict markers in the proposed content — "
            "resolve them with [e] before approving."
        )
    return None


def publication_block_reason(proposal: Proposal) -> str | None:
    """Return why publication is blocked, or None when the proposal is publishable."""
    if proposal.status == "pending":
        return "Proposal must be approved before publishing."
    if proposal.status != "approved":
        return "Reopen the proposal before publishing."
    if has_conflict_markers(proposal.proposed_content):
        return (
            "Unresolved conflict markers in the proposed content — "
            "resolve them with [e] before publishing."
        )
    return None


def confirm_publication(console: Console, proposal: Proposal) -> bool | None:
    reason = publication_block_reason(proposal)
    if reason:
        console.print(f"[yellow]{reason}[/yellow]")
        return None
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        console.print("[red]Publication requires an interactive terminal.[/red]")
        return None
    mode_label = "BOT edit" if proposal.mark_as_bot else "CRITICAL edit"
    return Confirm.ask(
        f"[bold red]Publish proposal #{proposal.id} ({mode_label}) to Wikipedia now?[/bold red]",
        default=False,
        console=console,
    )


def attempt_publish(
    console: Console,
    proposal: Proposal,
    store: ProposalStore,
    wiki: WikiClient,
) -> tuple[Proposal, str, bool]:
    """Run the publication flow with explicit feedback.

    Returns (proposal, notice, succeeded). Every outcome leaves a durable
    notice string; the decision log records conflicts and publications.
    """
    try:
        console.print("[cyan]Verifying page freshness and permissions...[/cyan]")
        new_revid, ts = wiki.publish_page(
            title=proposal.page.title,
            text=proposal.proposed_content,
            summary=proposal.edit_summary,
            expected_revid=proposal.page.revid,
            mark_as_bot=proposal.mark_as_bot,
        )
        proposal = store.record_publication(proposal.id, new_revid, ts)
        console.print(
            f"[bold green]SUCCESS: Proposal #{proposal.id} "
            f"published as revision {new_revid}![/bold green]\n"
        )
        notice = f"Published as revision {new_revid}."
    except EditConflictDetectedError as exc:
        console.print(f"[bold red]CONFLICT: {exc}[/bold red]")
        proposal = store.set_status(proposal.id, "conflict", reason=str(exc))
        notice = f"Publication blocked — edit conflict: {exc}"
    except InsufficientPermissionsError as exc:
        console.print(f"[bold red]PERMISSION DENIED: {exc}[/bold red]")
        notice = f"Publication blocked — insufficient permissions: {exc}"
    except Exception as exc:
        console.print(f"[bold red]PUBLICATION ERROR: {exc}[/bold red]\n")
        notice = f"Publication failed: {exc}"
    Prompt.ask("Press Enter to return", default="", console=console)
    return proposal, notice, proposal.status == "published"


def extract_test_status(rationale: str) -> str:
    lower = rationale.lower()
    if "тэст" in lower or "test" in lower:
        return "[dim]SEE NOTES[/dim]"
    return "[dim]UNVERIFIED[/dim]"


def draw_frame(console: Console, render_fn: Any) -> None:
    """Render frame into an in-memory buffer and write atomically to screen with zero flicker."""
    if not sys.stdout.isatty():
        render_fn(console)
        return

    buf_console = Console(
        file=sys.stdout,
        force_terminal=True,
        color_system=console.color_system or "auto",
        width=console.width,
        height=console.height,
    )
    with buf_console.capture() as capture:
        render_fn(buf_console)
    frame = capture.get()

    clean_frame = "".join(line + "\033[K\n" for line in frame.splitlines())
    sys.stdout.write("\033[H" + clean_frame + "\033[J")
    sys.stdout.flush()


def sync_proposal_with_wiki(
    proposal: Proposal,
    store: ProposalStore,
    wiki: WikiClient | None,
) -> tuple[str, Proposal]:
    """Check live wiki revision strictly read-only; never rebase or mutate proposal."""
    if wiki is None:
        try:
            wiki = WikiClient(
                site_lang=proposal.page.site_lang,
                family=proposal.page.family,
            )
        except Exception:
            return "unknown", proposal

    try:
        live = wiki.fetch_page(proposal.page.title)
    except Exception:
        return "unknown", proposal

    if live.revid == proposal.page.revid:
        return "synced", proposal

    return f"outdated:{live.revid}", proposal


def merge_with_live(proposal: Proposal, live: PageSnapshot) -> tuple[str, bool]:
    """3-way merge the proposal against a live snapshot.

    Returns (text, has_conflicts). Without a newer live revision the
    proposed text is returned unchanged.
    """
    if live.revid == proposal.page.revid:
        return proposal.proposed_content, False
    return three_way_merge(
        base_text=proposal.page.content,
        proposed_text=proposal.proposed_content,
        live_text=live.content,
        base_label=f"rev-{proposal.page.revid}",
        proposed_label=f"proposal-v{proposal.current_version}",
        live_label=f"live-rev-{live.revid}",
    )


def pull_and_merge_for_edit(
    console: Console,
    proposal: Proposal,
    store: ProposalStore,
    wiki: WikiClient,
) -> tuple[str, bool, PageSnapshot, bool]:
    """Pull latest live revision and 3-way merge before opening editor.

    Returns (text, was_rebased, live, has_conflicts).
    """
    try:
        live = wiki.fetch_page(proposal.page.title)
    except Exception:
        return proposal.proposed_content, False, proposal.page, False

    if live.revid == proposal.page.revid:
        return proposal.proposed_content, False, live, False

    merged_text, has_conflicts = merge_with_live(proposal, live)
    return merged_text, True, live, has_conflicts


def apply_rebase(
    store: ProposalStore,
    proposal: Proposal,
    live: PageSnapshot,
    new_content: str,
) -> tuple[Proposal, str, bool]:
    """Persist a pull-and-merge result; never present unresolved conflicts as success.

    Returns (proposal, message, conflicted). The decision log records
    'rebase_with_conflicts' when markers remain in the saved content.
    """
    proposal = store.rebase_base_page(
        proposal.id, new_snapshot=live, new_proposed_content=new_content
    )
    if has_conflict_markers(new_content):
        message = (
            f"Rebased onto live revision {live.revid} (v{proposal.current_version}) with "
            "UNRESOLVED conflict markers — approval is blocked until they are resolved in the editor."
        )
        return proposal, message, True
    message = f"Rebased onto live revision {live.revid} (v{proposal.current_version})."
    return proposal, message, False


def render_dashboard_table(
    console: Console,
    proposals: list[Proposal],
    selected_idx: int = 0,
    filter_status: str = "all",
    notice: str = "",
) -> None:
    """Render proposals dashboard table with an active cursor row."""

    def _draw(c: Console) -> None:
        pending_count = sum(1 for p in proposals if p.status == "pending")
        approved_count = sum(1 for p in proposals if p.status == "approved")
        declined_count = sum(1 for p in proposals if p.status == "declined")
        published_count = sum(1 for p in proposals if p.status == "published")
        conflict_count = sum(1 for p in proposals if p.status == "conflict")

        summary_bar = (
            f"[bold]Total proposals:[/bold] {len(proposals)}  │  "
            f"[yellow]Pending:[/yellow] {pending_count}  │  "
            f"[green]Approved:[/green] {approved_count}  │  "
            f"[red]Declined:[/red] {declined_count}  │  "
            f"[blue]Published:[/blue] {published_count}"
        )
        if conflict_count:
            summary_bar += f"  │  [bold red]Conflicts:[/bold red] {conflict_count}"
        if notice:
            summary_bar += f"\n[bold yellow]NOTICE:[/bold yellow] {escape(notice)}"

        c.print(
            Panel(
                summary_bar,
                title=f"[bold cyan]WIKIPEDIA EDIT PROPOSALS DASHBOARD[/bold cyan] [dim](Filter: {filter_status.upper()})[/dim]",
                border_style="cyan",
            )
        )

        if not proposals:
            c.print(f"\n[dim italic]No proposals matching filter '{filter_status}'.[/dim italic]\n")
        else:
            table = Table(show_header=True, header_style="bold cyan", expand=True)
            table.add_column("Sel", justify="center", width=3)
            table.add_column("ID", style="bold", width=6)
            table.add_column("Status", width=11)
            table.add_column("Mode", justify="center", width=10)
            table.add_column("Diff", justify="center", width=11)
            table.add_column("Tests", justify="center", width=10)
            table.add_column("Affected Page & URL", style="blue")
            table.add_column("Issue & Agent Rationale")

            status_styles = {
                "pending": "yellow",
                "approved": "green",
                "declined": "red",
                "published": "bold blue",
                "conflict": "bold red",
            }

            for idx, p in enumerate(proposals):
                is_selected = idx == selected_idx
                sel_pointer = "[bold cyan]▶[/bold cyan]" if is_selected else " "
                row_style = "bold white on grey23" if is_selected else None

                color = status_styles.get(p.status, "white")
                added, removed = compute_diff_stats(p.page.content, p.proposed_content)
                diff_badge = f"[green]+{added}[/green] / [red]-{removed}[/red]"
                test_badge = extract_test_status(p.rationale)

                mode_badge = (
                    "[dim cyan]BOT[/dim cyan]"
                    if p.mark_as_bot
                    else "[bold yellow]CRITICAL[/bold yellow]"
                )

                first_line_rationale = ""
                for line in p.rationale.splitlines():
                    clean_l = re.sub(r"^#+\s*", "", line).strip()
                    if clean_l and not clean_l.lower().startswith("праблема"):
                        first_line_rationale = clean_l[:60] + ("..." if len(clean_l) > 60 else "")
                        break

                page_cell = f"[bold]{p.page.title}[/bold]\n[dim]https://{p.page.wiki}/wiki/{p.page.title}[/dim]"
                issue_cell = f"[bold]{p.issue}[/bold]"
                if first_line_rationale:
                    issue_cell += f"\n[dim]{first_line_rationale}[/dim]"

                id_str = f"[bold cyan]#{p.id}[/bold cyan]" if is_selected else f"#{p.id}"

                table.add_row(
                    sel_pointer,
                    id_str,
                    f"[{color}]{p.status.upper()}[/{color}]",
                    mode_badge,
                    diff_badge,
                    test_badge,
                    page_cell,
                    issue_cell,
                    style=row_style,
                )

            c.print(table)

        toolbar = (
            f"{format_badge('↑/↓', 'Navigate', 'cyan')}   "
            f"{format_badge('Enter', 'Open', 'green')}   "
            f"{format_badge('f', f'Filter: {filter_status.upper()}', 'magenta')}   "
            f"{format_badge('t', 'Toggle Bot', 'yellow')}   "
            f"{format_badge('p', 'Publish', 'cyan')}   "
            f"{format_badge('d', 'Decline', 'red')}   "
            f"{format_badge('e', 'Vim Edit', 'yellow')}   "
            f"{format_badge('o', 'Browser', 'blue')}   "
            f"{format_badge('q', 'Quit', 'white')}"
        )
        c.print(
            Panel(
                toolbar,
                title="[bold]Controls[/bold]",
                title_align="left",
                border_style="bright_black",
            )
        )

    draw_frame(console, _draw)


def render_dashboard(
    console: Console, store: ProposalStore, filter_status: str = "all"
) -> list[Proposal]:
    proposals = store.list_proposals(status=filter_status)
    render_dashboard_table(console, proposals, selected_idx=-1, filter_status=filter_status)
    return proposals


@lru_cache(maxsize=64)
def _content_lines(
    page_content: str,
    proposed_content: str,
    rationale: str,
    edit_summary: str,
    page_title: str,
    view_mode: str,
    width: int,
    color_system: str,
) -> tuple[str, ...]:
    """Build content lines for a fixed set of proposal texts (cacheable)."""
    buf = Console(force_terminal=True, color_system=color_system, width=width)
    lines: list[str] = []

    def _render(obj: Any) -> list[str]:
        with buf.capture() as cap:
            buf.print(obj)
        return cap.get().splitlines()

    # Rationale
    if view_mode in ("all", "rationale") and rationale.strip():
        lines.extend(
            _render(
                "[bold cyan]── Agent Rationale & Verification ──────────────────────────────────────[/bold cyan]"
            )
        )
        for rl in rationale.strip().splitlines():
            lines.extend(_render(escape(rl)))
        lines.append("")

    # Diff
    if view_mode in ("all", "diff"):
        added, removed = compute_diff_stats(page_content, proposed_content)
        lines.extend(
            _render(
                f"[bold cyan]── Proposed Changes (Diff: [green]+{added}[/green] / [red]-{removed}[/red] lines) ──────────────────────────[/bold cyan]"
            )
        )
        diff_lines = format_diff_lines(page_content, proposed_content, title=page_title)
        for dl in diff_lines:
            lines.extend(_render(dl))
        lines.append("")

    # Summary
    if view_mode in ("all", "rationale"):
        lines.extend(
            _render(
                "[bold cyan]── Proposed Edit Summary ─────────────────────────────────────────────[/bold cyan]"
            )
        )
        lines.extend(_render(f'[bold green]"{escape(edit_summary)}"[/bold green]'))

    return tuple(lines)


def build_proposal_content_lines(
    proposal: Proposal,
    view_mode: str = "all",
    width: int = 80,
    color_system: str = "auto",
) -> list[str]:
    """Build formatted, colorized content lines for the scrollable viewport.

    Cached per content values so per-key frame redraws skip the recompute.
    """
    return list(
        _content_lines(
            proposal.page.content,
            proposal.proposed_content,
            proposal.rationale,
            proposal.edit_summary,
            proposal.page.title,
            view_mode,
            width,
            color_system or "auto",
        )
    )


def render_proposal_view(
    console: Console,
    proposal: Proposal,
    scroll_offset: int = 0,
    view_mode: str = "all",
    sync_status: str = "offline",
    notice: str = "",
) -> tuple[int, int, int]:
    """Render proposal card with pinned header/footer and middle scrollable viewport.

    Returns:
        tuple[int, int, int]: (clamped_scroll_offset, max_scroll, viewport_height)
    """
    term_cols, term_lines = shutil.get_terminal_size((80, 24))
    term_cols = max(40, term_cols)
    term_lines = max(16, term_lines)

    page = proposal.page
    status_color = {
        "pending": "yellow",
        "approved": "green",
        "declined": "red",
        "published": "blue",
        "conflict": "bold red",
    }.get(proposal.status, "white")

    added, removed = compute_diff_stats(page.content, proposal.proposed_content)
    test_badge = extract_test_status(proposal.rationale)

    mode_badge = (
        "[dim cyan]ROUTINE (Bot Flag)[/dim cyan]"
        if proposal.mark_as_bot
        else "[bold yellow]CRITICAL (Watchlist Visible)[/bold yellow]"
    )

    if sync_status.startswith("outdated"):
        live_revid = sync_status.split(":", 1)[1] if ":" in sync_status else "newer"
        sync_badge = f"[bold yellow]OUTDATED (live rev {live_revid})[/bold yellow]"
    elif sync_status.startswith("rebased"):
        sync_badge = f"[bold yellow]REBASED to live rev {page.revid}[/bold yellow]"
    elif sync_status.startswith("conflict"):
        sync_badge = "[bold red]CONFLICT WITH LIVE WIKI[/bold red]"
    elif sync_status == "synced":
        sync_badge = f"[green]SYNCHRONIZED (rev {page.revid})[/green]"
    elif sync_status == "unknown":
        sync_badge = "[bold yellow]UNKNOWN[/bold yellow]"
    else:
        sync_badge = f"[dim]LOCAL BASE (rev {page.revid})[/dim]"

    header_text = (
        f"[bold]Proposal:[/bold] #{proposal.id}  │  "
        f"[bold]Status:[/bold] [{status_color}]{proposal.status.upper()}[/{status_color}]  │  "
        f"[bold]Mode:[/bold] {mode_badge}  │  "
        f"[bold]Diff:[/bold] [green]+{added}[/green] / [red]-{removed}[/red]  │  "
        f"[bold]Tests:[/bold] {test_badge}\n"
        f"[bold]Page:[/bold]     {page.title}  │  "
        f"[bold]Live Sync:[/bold] {sync_badge}  │  "
        f"[bold]Version:[/bold] {proposal.current_version} of {len(proposal.versions)}\n"
        f"[bold]Issue:[/bold]    {proposal.issue}"
    )
    if notice:
        header_text += f"\n[bold yellow]NOTICE:[/bold yellow] {escape(notice)}"

    buf = Console(force_terminal=True, color_system=console.color_system or "auto", width=term_cols)

    with buf.capture() as cap:
        buf.print(
            Panel(header_text, title="[bold cyan]PROPOSAL DETAILS[/bold cyan]", border_style="cyan")
        )
    header_lines = cap.get().splitlines()
    header_height = len(header_lines)

    all_lines = build_proposal_content_lines(
        proposal,
        view_mode=view_mode,
        width=term_cols - 2,
        color_system=console.color_system or "auto",
    )
    total_lines = len(all_lines)

    footer_height = 4
    viewport_height = max(3, term_lines - header_height - footer_height - 1)

    max_scroll = max(0, total_lines - viewport_height)
    clamped_scroll = max(0, min(scroll_offset, max_scroll))

    visible_lines = all_lines[clamped_scroll : clamped_scroll + viewport_height]
    if len(visible_lines) < viewport_height:
        visible_lines.extend([""] * (viewport_height - len(visible_lines)))

    view_labels = {
        "all": "ALL",
        "diff": "DIFF ONLY",
        "rationale": "RATIONALE ONLY",
    }
    view_label = view_labels.get(view_mode, view_mode.upper())

    if total_lines <= viewport_height:
        scroll_info = "Scroll: All content visible"
    else:
        current_bottom = min(clamped_scroll + viewport_height, total_lines)
        pct = int(100 * current_bottom / total_lines)
        scroll_info = f"Scroll: lines {clamped_scroll + 1}-{current_bottom} of {total_lines} ({pct}%) [↑/↓ or j/k to scroll]"

    status_row = f"[bold cyan]{scroll_info}[/bold cyan]  │  [bold magenta]View: {view_label} ([v] to switch)[/bold magenta]"

    toolbar_row = (
        f"{format_badge('↑/↓', 'Scroll', 'cyan')}   "
        f"{format_badge('v', 'View', 'magenta')}   "
        f"{format_badge('a', 'Approve', 'green')}   "
        f"{format_badge('p', 'Publish', 'cyan')}   "
        f"{format_badge('d', 'Decline', 'red')}   "
        f"{format_badge('e', 'Vim Edit', 'yellow')}   "
        f"{format_badge('r', 'Rebase', 'yellow')}   "
        f"{format_badge('m', 'Summary', 'magenta')}   "
        f"{format_badge('t', 'Toggle Bot', 'yellow')}   "
        f"{format_badge('o', 'Browser', 'blue')}   "
        f"{format_badge('b', 'Back', 'white')}"
    )
    footer_text = f"{status_row}\n{toolbar_row}"
    with buf.capture() as cap:
        buf.print(Panel(footer_text, title="[bold]Actions[/bold]", border_style="bright_black"))
    footer_lines = cap.get().splitlines()

    screen_lines = header_lines + visible_lines + footer_lines
    if sys.stdout.isatty():
        clean_screen = "".join(line + "\033[K\n" for line in screen_lines)
        sys.stdout.write("\033[H" + clean_screen + "\033[J")
        sys.stdout.flush()
    else:
        for line in screen_lines:
            console.print(line)

    return clamped_scroll, max_scroll, viewport_height


def render_proposal_card(console: Console, proposal: Proposal) -> None:
    render_proposal_view(console, proposal, scroll_offset=0)


def review_proposal_interactive(
    console: Console,
    proposal: Proposal,
    store: ProposalStore,
    wiki: WikiClient | None = None,
    sync_status: str = "offline",
) -> str:
    """Run interactive review for a proposal with scrollable diff and instant actions."""
    scroll_offset = 0
    view_modes = ["all", "diff", "rationale"]
    view_idx = 0
    notice = ""

    while True:
        current_view = view_modes[view_idx]
        scroll_offset, max_scroll, viewport_height = render_proposal_view(
            console,
            proposal,
            scroll_offset=scroll_offset,
            view_mode=current_view,
            sync_status=sync_status,
            notice=notice,
        )

        key = read_key()

        if key in ("b", "left", "escape", "q"):
            return "back"

        if key in ("ctrl-c",):
            return "quit"

        # Toggle view mode (ALL / DIFF ONLY / RATIONALE ONLY)
        if key == "v":
            view_idx = (view_idx + 1) % len(view_modes)
            scroll_offset = 0
            if sys.stdout.isatty():
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
            continue

        # Scroll controls
        if key in ("down", "j"):
            scroll_offset = min(max_scroll, scroll_offset + 1)
            continue

        if key in ("up", "k"):
            scroll_offset = max(0, scroll_offset - 1)
            continue

        if key in ("page_down", "space", "J"):
            scroll_offset = min(max_scroll, scroll_offset + max(1, viewport_height - 2))
            continue

        if key in ("page_up", "K"):
            scroll_offset = max(0, scroll_offset - max(1, viewport_height - 2))
            continue

        if key in ("home", "g"):
            scroll_offset = 0
            continue

        if key in ("end", "G"):
            scroll_offset = max_scroll
            continue

        # Toggle bot flag
        if key == "t":
            proposal = store.toggle_mark_as_bot(proposal.id)
            continue

        # Browser
        if key == "o":
            url = f"https://{proposal.page.wiki}/wiki/{proposal.page.title}"
            console.print(f"[cyan]Opening {url} in browser...[/cyan]")
            webbrowser.open(url)
            continue

        # Approve
        if key == "a":
            reason = approval_block_reason(proposal)
            if reason:
                notice = reason
                continue
            if sys.stdout.isatty():
                sys.stdout.write("\033[?1049l\033[?25h")
                sys.stdout.flush()
            try:
                confirmed = Confirm.ask(
                    f"[bold green]Approve proposal #{proposal.id} for publication?[/bold green]",
                    default=False,
                    console=console,
                )
                if confirmed:
                    proposal = store.set_status(
                        proposal.id, "approved", reason="Approved in review"
                    )
                    notice = f"Proposal #{proposal.id} approved — press [p] to publish."
                else:
                    notice = "Approval cancelled."
            finally:
                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049h\033[?25l")
                    sys.stdout.flush()
            continue

        # Decline
        if key == "d":
            if sys.stdout.isatty():
                sys.stdout.write("\033[?1049l\033[?25h")
                sys.stdout.flush()
            try:
                reason = Prompt.ask(
                    "Reason for declining (optional)", default="", console=console
                ).strip()
                proposal = store.set_status(proposal.id, "declined", reason=reason)
            finally:
                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049h\033[?25l")
                    sys.stdout.flush()
            return "back"

        # Edit in Vim
        if key == "e":
            if wiki is None:
                try:
                    wiki = WikiClient(
                        site_lang=proposal.page.site_lang,
                        family=proposal.page.family,
                    )
                except Exception:
                    wiki = None

            if wiki is not None:
                text_to_edit, was_rebased, live, _has_conflicts = pull_and_merge_for_edit(
                    console, proposal, store, wiki
                )
            else:
                text_to_edit, was_rebased, live = (
                    proposal.proposed_content,
                    False,
                    proposal.page,
                )

            suffix = get_file_suffix_for_page(proposal.page.title)

            if sys.stdout.isatty():
                sys.stdout.write("\033[?1049l\033[?25h")
                sys.stdout.flush()
            try:
                new_content, modified = edit_text_in_editor(text_to_edit, suffix=suffix)
            finally:
                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049h\033[?25l")
                    sys.stdout.flush()

            if modified or was_rebased:
                if was_rebased:
                    proposal, notice, _conflicted = apply_rebase(store, proposal, live, new_content)
                    sync_status = f"rebased:{live.revid}"
                else:
                    proposal = store.update_content(
                        proposal.id,
                        new_content=new_content,
                        action="edit_content_vim",
                    )
                    notice = (
                        f"Saved version v{proposal.current_version} — renewed approval required."
                    )
            continue

        # Edit summary
        if key == "m":
            if sys.stdout.isatty():
                sys.stdout.write("\033[?1049l\033[?25h")
                sys.stdout.flush()
            try:
                new_summary, modified = edit_text_in_editor(proposal.edit_summary, suffix=".txt")
            finally:
                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049h\033[?25l")
                    sys.stdout.flush()

            if modified and new_summary.strip():
                proposal = store.update_summary(proposal.id, new_summary.strip())
            continue

        # Explicit rebase onto the live revision
        if key == "r":
            if has_conflict_markers(proposal.proposed_content):
                notice = "Resolve the conflict markers with [e] before rebasing."
                continue
            if wiki is None:
                try:
                    wiki = WikiClient(
                        site_lang=proposal.page.site_lang,
                        family=proposal.page.family,
                    )
                except Exception:
                    wiki = None
            if wiki is None:
                notice = "Cannot rebase: wiki client unavailable."
                continue
            try:
                live = wiki.fetch_page(proposal.page.title)
            except Exception as exc:
                notice = f"Cannot rebase: failed to fetch the live page ({exc})."
                continue
            if live.revid == proposal.page.revid:
                notice = f"Already on live revision {live.revid} — nothing to rebase."
                continue
            merged_text, _has_conflicts = merge_with_live(proposal, live)
            proposal, notice, _conflicted = apply_rebase(store, proposal, live, merged_text)
            sync_status = f"rebased:{live.revid}"
            continue

        # Publish
        if key == "p":
            reason = publication_block_reason(proposal)
            if reason:
                notice = reason
                continue

            if sys.stdout.isatty():
                sys.stdout.write("\033[?1049l\033[?25h")
                sys.stdout.flush()

            try:
                confirmed = confirm_publication(console, proposal)
                if not confirmed:
                    continue

                if wiki is None:
                    wiki = WikiClient(
                        site_lang=proposal.page.site_lang,
                        family=proposal.page.family,
                    )

                proposal, notice, succeeded = attempt_publish(console, proposal, store, wiki)
                if succeeded:
                    return "back"
            finally:
                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049h\033[?25l")
                    sys.stdout.flush()


def interactive_dashboard_loop(
    console: Console,
    store: ProposalStore,
    wiki: WikiClient | None = None,
) -> None:
    """Single-entrypoint dashboard loop with arrow navigation in alternate screen."""
    filter_cycles = ["all", "pending", "approved", "declined"]
    filter_idx = 0
    selected_idx = 0
    notice = ""

    with alternate_screen():
        while True:
            current_filter = filter_cycles[filter_idx]
            proposals = store.list_proposals(status=current_filter)

            if proposals:
                selected_idx = max(0, min(selected_idx, len(proposals) - 1))
            else:
                selected_idx = 0

            render_dashboard_table(
                console,
                proposals,
                selected_idx=selected_idx,
                filter_status=current_filter,
                notice=notice,
            )

            key = read_key()

            if key in ("q", "ctrl-c"):
                break

            if key == "escape":
                continue

            if key in ("up", "k"):
                if proposals:
                    selected_idx = (selected_idx - 1) % len(proposals)
                continue

            if key in ("down", "j"):
                if proposals:
                    selected_idx = (selected_idx + 1) % len(proposals)
                continue

            if key == "f":
                filter_idx = (filter_idx + 1) % len(filter_cycles)
                selected_idx = 0
                continue

            if not proposals:
                continue

            current_proposal = proposals[selected_idx]

            # Toggle bot flag from dashboard
            if key == "t":
                store.toggle_mark_as_bot(current_proposal.id)
                continue

            # Open proposal: read-only live-revision check (rebase explicitly with [r])
            if key in ("enter", "space", "right"):
                if sys.stdout.isatty():
                    sys.stdout.write("\033[2J\033[H")
                    sys.stdout.flush()
                sync_status, updated_proposal = sync_proposal_with_wiki(
                    current_proposal, store, wiki
                )
                action = review_proposal_interactive(
                    console,
                    updated_proposal,
                    store,
                    wiki=wiki,
                    sync_status=sync_status,
                )
                if sys.stdout.isatty():
                    sys.stdout.write("\033[2J\033[H")
                    sys.stdout.flush()
                if action == "quit":
                    break
                continue

            if key == "o":
                url = f"https://{current_proposal.page.wiki}/wiki/{current_proposal.page.title}"
                webbrowser.open(url)
                continue

            if key == "d":
                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049l\033[?25h")
                    sys.stdout.flush()
                try:
                    reason = Prompt.ask(
                        "Reason for declining (optional)", default="", console=console
                    ).strip()
                    store.set_status(current_proposal.id, "declined", reason=reason)
                finally:
                    if sys.stdout.isatty():
                        sys.stdout.write("\033[?1049h\033[?25l")
                        sys.stdout.flush()
                continue

            if key == "e":
                if wiki is None:
                    try:
                        wiki = WikiClient(
                            site_lang=current_proposal.page.site_lang,
                            family=current_proposal.page.family,
                        )
                    except Exception:
                        wiki = None

                if wiki is not None:
                    text_to_edit, was_rebased, live, _has_conflicts = pull_and_merge_for_edit(
                        console, current_proposal, store, wiki
                    )
                else:
                    text_to_edit, was_rebased, live = (
                        current_proposal.proposed_content,
                        False,
                        current_proposal.page,
                    )

                suffix = get_file_suffix_for_page(current_proposal.page.title)

                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049l\033[?25h")
                    sys.stdout.flush()
                try:
                    new_content, modified = edit_text_in_editor(text_to_edit, suffix=suffix)
                finally:
                    if sys.stdout.isatty():
                        sys.stdout.write("\033[?1049h\033[?25l")
                        sys.stdout.flush()

                if modified or was_rebased:
                    if was_rebased:
                        _, notice, _conflicted = apply_rebase(
                            store, current_proposal, live, new_content
                        )
                    else:
                        store.update_content(
                            current_proposal.id,
                            new_content=new_content,
                            action="edit_content_vim",
                        )
                        notice = "Content saved — renewed approval required."
                continue

            if key == "p":
                reason = publication_block_reason(current_proposal)
                if reason:
                    notice = reason
                    continue

                if sys.stdout.isatty():
                    sys.stdout.write("\033[?1049l\033[?25h")
                    sys.stdout.flush()
                try:
                    confirmed = confirm_publication(console, current_proposal)
                    if confirmed:
                        if wiki is None:
                            wiki = WikiClient(
                                site_lang=current_proposal.page.site_lang,
                                family=current_proposal.page.family,
                            )
                        _, notice, _succeeded = attempt_publish(
                            console, current_proposal, store, wiki
                        )
                finally:
                    if sys.stdout.isatty():
                        sys.stdout.write("\033[?1049h\033[?25l")
                        sys.stdout.flush()
                continue
