from __future__ import annotations

import re
import shutil
import sys
import webbrowser
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from agentic_bot.diff import compute_diff_stats, format_diff_lines
from agentic_bot.editor import edit_text_in_editor
from agentic_bot.merge import three_way_merge
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


def confirm_publication(console: Console, proposal: Proposal) -> bool | None:
    if proposal.status not in {"pending", "approved"}:
        console.print("[red]Reopen the proposal before publishing.[/red]")
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
    """Fetch latest live wiki revision; auto-rebase if clean, flag conflict if not."""
    if wiki is None:
        try:
            wiki = WikiClient(
                site_lang=proposal.page.site_lang,
                family=proposal.page.family,
            )
        except Exception:
            return "offline", proposal

    try:
        live = wiki.fetch_page(proposal.page.title)
    except Exception:
        return "offline", proposal

    if live.revid == proposal.page.revid:
        return "synced", proposal

    merged_text, has_conflicts = three_way_merge(
        base_text=proposal.page.content,
        proposed_text=proposal.proposed_content,
        live_text=live.content,
        base_label=f"rev-{proposal.page.revid}",
        proposed_label=f"proposal-v{proposal.current_version}",
        live_label=f"live-rev-{live.revid}",
    )

    if has_conflicts:
        proposal = store.set_status(
            proposal.id,
            "conflict",
            reason=f"Merge conflict with live wiki rev {live.revid}",
        )
        return f"conflict:{live.revid}", proposal

    proposal = store.rebase_base_page(
        proposal.id,
        new_snapshot=live,
        new_proposed_content=merged_text,
    )
    return f"rebased:{live.revid}", proposal


def pull_and_merge_for_edit(
    console: Console,
    proposal: Proposal,
    store: ProposalStore,
    wiki: WikiClient,
) -> tuple[str, bool, PageSnapshot]:
    """Pull latest live revision and 3-way merge before opening editor."""
    try:
        live = wiki.fetch_page(proposal.page.title)
    except Exception:
        return proposal.proposed_content, False, proposal.page

    if live.revid == proposal.page.revid:
        return proposal.proposed_content, False, live

    merged_text, has_conflicts = three_way_merge(
        base_text=proposal.page.content,
        proposed_text=proposal.proposed_content,
        live_text=live.content,
        base_label=f"rev-{proposal.page.revid}",
        proposed_label=f"proposal-v{proposal.current_version}",
        live_label=f"live-rev-{live.revid}",
    )
    return merged_text, True, live


def render_dashboard_table(
    console: Console,
    proposals: list[Proposal],
    selected_idx: int = 0,
    filter_status: str = "all",
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


def build_proposal_content_lines(
    proposal: Proposal,
    view_mode: str = "all",
    width: int = 80,
    color_system: str = "auto",
) -> list[str]:
    """Build formatted, colorized content lines for the scrollable viewport."""
    buf = Console(force_terminal=True, color_system=color_system or "auto", width=width)
    lines: list[str] = []

    def _render(obj: Any) -> list[str]:
        with buf.capture() as cap:
            buf.print(obj)
        return cap.get().splitlines()

    # Rationale
    if view_mode in ("all", "rationale") and proposal.rationale.strip():
        lines.extend(
            _render(
                "[bold cyan]── Agent Rationale & Verification ──────────────────────────────────────[/bold cyan]"
            )
        )
        for rl in proposal.rationale.strip().splitlines():
            lines.extend(_render(escape(rl)))
        lines.append("")

    # Diff
    if view_mode in ("all", "diff"):
        added, removed = compute_diff_stats(proposal.page.content, proposal.proposed_content)
        lines.extend(
            _render(
                f"[bold cyan]── Proposed Changes (Diff: [green]+{added}[/green] / [red]-{removed}[/red] lines) ──────────────────────────[/bold cyan]"
            )
        )
        diff_lines = format_diff_lines(
            proposal.page.content,
            proposal.proposed_content,
            title=proposal.page.title,
        )
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
        lines.extend(_render(f'[bold green]"{escape(proposal.edit_summary)}"[/bold green]'))

    return lines


def render_proposal_view(
    console: Console,
    proposal: Proposal,
    scroll_offset: int = 0,
    view_mode: str = "all",
    sync_status: str = "offline",
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

    if sync_status.startswith("rebased"):
        sync_badge = f"[bold yellow]REBASED to live rev {page.revid}[/bold yellow]"
    elif sync_status.startswith("conflict"):
        sync_badge = "[bold red]CONFLICT WITH LIVE WIKI[/bold red]"
    elif sync_status == "synced":
        sync_badge = f"[green]SYNCHRONIZED (rev {page.revid})[/green]"
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
        f"{format_badge('p', 'Publish', 'cyan')}   "
        f"{format_badge('d', 'Decline', 'red')}   "
        f"{format_badge('e', 'Vim Edit', 'yellow')}   "
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

    while True:
        current_view = view_modes[view_idx]
        scroll_offset, max_scroll, viewport_height = render_proposal_view(
            console,
            proposal,
            scroll_offset=scroll_offset,
            view_mode=current_view,
            sync_status=sync_status,
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
                text_to_edit, was_rebased, live = pull_and_merge_for_edit(
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
                    proposal = store.rebase_base_page(
                        proposal.id,
                        new_snapshot=live,
                        new_proposed_content=new_content,
                    )
                    sync_status = f"rebased:{live.revid}"
                else:
                    proposal = store.update_content(
                        proposal.id,
                        new_content=new_content,
                        action="edit_content_vim",
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

        # Publish
        if key == "p":
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
                        f"[bold green]SUCCESS: Proposal #{proposal.id} published as revision {new_revid}![/bold green]\n"
                    )
                    Prompt.ask("Press Enter to return", default="", console=console)
                    return "back"
                except EditConflictDetectedError as exc:
                    console.print(f"[bold red]CONFLICT: {exc}[/bold red]")
                    proposal = store.set_status(proposal.id, "conflict", reason=str(exc))
                    Prompt.ask("Press Enter to return", default="", console=console)
                except InsufficientPermissionsError as exc:
                    console.print(f"[bold red]PERMISSION DENIED: {exc}[/bold red]")
                    Prompt.ask("Press Enter to return", default="", console=console)
                except Exception as exc:
                    console.print(f"[bold red]PUBLICATION ERROR: {exc}[/bold red]\n")
                    Prompt.ask("Press Enter to return", default="", console=console)
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

            # Open proposal: auto-fetch latest version from wiki
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
                    text_to_edit, was_rebased, live = pull_and_merge_for_edit(
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
                        store.rebase_base_page(
                            current_proposal.id,
                            new_snapshot=live,
                            new_proposed_content=new_content,
                        )
                    else:
                        store.update_content(
                            current_proposal.id,
                            new_content=new_content,
                            action="edit_content_vim",
                        )
                continue

            if key == "p":
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
                        try:
                            console.print(
                                "[cyan]Verifying page freshness and permissions...[/cyan]"
                            )
                            new_revid, ts = wiki.publish_page(
                                title=current_proposal.page.title,
                                text=current_proposal.proposed_content,
                                summary=current_proposal.edit_summary,
                                expected_revid=current_proposal.page.revid,
                                mark_as_bot=current_proposal.mark_as_bot,
                            )
                            store.record_publication(current_proposal.id, new_revid, ts)
                            console.print(
                                f"[bold green]SUCCESS: Proposal #{current_proposal.id} published as revision {new_revid}![/bold green]"
                            )
                        except Exception as exc:
                            console.print(f"[bold red]Publication error: {exc}[/bold red]")
                        Prompt.ask("Press Enter to continue", default="", console=console)
                finally:
                    if sys.stdout.isatty():
                        sys.stdout.write("\033[?1049h\033[?25l")
                        sys.stdout.flush()
                continue
