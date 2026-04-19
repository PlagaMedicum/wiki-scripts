from __future__ import annotations

import difflib
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, replace
from threading import RLock

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    track,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from biblio.models import BulkRunStatus, ReplacementResult, RunStats, SourceSpec, VariantInfo
from biblio.observability import format_elapsed


@dataclass(frozen=True)
class ChecklistOption:
    value: str
    label: str
    detail: str = ""


class AppUI:
    def __init__(self, *, no_color: bool = False, console: Console | None = None) -> None:
        self.no_color = no_color
        self.console = console or Console(
            no_color=no_color,
            highlight=False,
            soft_wrap=False,
        )
        self._shown_variant_controls = False
        self._shown_review_match_controls = False
        self._shown_page_controls = False
        self._bulk_status: BulkRunStatus | None = None
        self._run_progress: Progress | None = None
        self._run_progress_task: TaskID | None = None
        self._last_bulk_status_line: str | None = None
        self._screen_ui_suspend_depth = 0
        self._console_lock = RLock()

    @contextmanager
    def _suspend_screen_ui(self):
        should_resume_progress = (
            self._screen_ui_suspend_depth == 0 and self._run_progress is not None
        )
        self._screen_ui_suspend_depth += 1
        if should_resume_progress:
            self._stop_run_progress()
        try:
            yield
        finally:
            self._screen_ui_suspend_depth -= 1
            if (
                should_resume_progress
                and self._screen_ui_suspend_depth == 0
                and self._bulk_status is not None
            ):
                self._ensure_bulk_live()

    def _print_message(self, message: str, *, style: str = "") -> None:
        with self._console_lock:
            self.console.print(message, style=style, markup=False)

    def _supports_screen_ui(self) -> bool:
        return self._supports_single_key_input() and self.console.is_terminal

    @contextmanager
    def _live_screen(self, renderable):
        if not self.console.is_terminal:
            yield None
            return
        with Live(
            renderable,
            console=self.console,
            auto_refresh=False,
            screen=True,
            transient=True,
        ) as live:
            yield live

    def print(self, renderable) -> None:
        with self._console_lock:
            self.console.print(renderable)

    def begin_bulk_run(self, status: BulkRunStatus) -> None:
        self._bulk_status = status
        self._ensure_bulk_live()

    def update_bulk_status(self, status: BulkRunStatus) -> None:
        self._bulk_status = status
        self._ensure_bulk_live()

    def finish_bulk_run(self) -> None:
        self._stop_bulk_live()
        self._bulk_status = None

    def report_transport_wait(self, message: str) -> None:
        self.warn(message)
        if self._bulk_status is None:
            return
        phase = self._bulk_status.phase
        if message.startswith("[retry]"):
            phase = "retry"
        elif message.startswith("[throttle]") or message.startswith("[maxlag]"):
            phase = "throttle"
        self.update_bulk_status(
            replace(
                self._bulk_status,
                phase=phase,
                detail=message,
            )
        )

    def info(self, message: str) -> None:
        self._print_message(message)

    def warn(self, message: str) -> None:
        style = "" if self.no_color else "yellow"
        self._print_message(message, style=style)

    def error(self, message: str) -> None:
        style = "" if self.no_color else "bold red"
        self._print_message(message, style=style)

    def build_source_table(self, specs: list[SourceSpec]) -> Table:
        table = Table(title="Available bibliography sources")
        table.add_column("Source ID", style="" if self.no_color else "bold cyan")
        table.add_column("Name")
        table.add_column("Template", style="" if self.no_color else "green")
        for spec in specs:
            table.add_row(spec.source_id, spec.name, spec.template_name)
        return table

    def print_sources(self, specs: list[SourceSpec]) -> None:
        self.print(self.build_source_table(specs))

    def print_startup_wizard_intro(self, source_count: int) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("Mode", "Startup wizard")
        table.add_row("Sources", str(source_count))
        table.add_row("Flow", "Select sources, choose the run mode, pick flags, and start the run.")
        table.add_row(
            "Input",
            "Use single-key prompts where available. Press `q` in checklist screens to cancel.",
        )
        self.print(Panel(table, title="Interactive startup", border_style="blue"))

    def build_startup_panel(
        self,
        spec: SourceSpec,
        *,
        query: str,
        limit: int,
        apply: bool,
        summary: str,
        source_label: str | None = None,
    ) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("Source", source_label or f"{spec.source_id} ({spec.name})")
        table.add_row("Wiki", f"{spec.site_lang}.{spec.family}")
        table.add_row("Mode", "apply" if apply else "dry-run")
        table.add_row("Limit", str(limit))
        table.add_row("Query", query)
        table.add_row("Edit summary", summary)
        return Panel(table, title="Run configuration", border_style="blue")

    def print_startup_panel(
        self,
        spec: SourceSpec,
        *,
        query: str,
        limit: int,
        apply: bool,
        summary: str,
        source_label: str | None = None,
    ) -> None:
        self.print(
            self.build_startup_panel(
                spec,
                query=query,
                limit=limit,
                apply=apply,
                summary=summary,
                source_label=source_label,
            )
        )

    def print_run_guidance(
        self,
        *,
        apply: bool,
        assume_yes: bool,
        has_review_required_rules: bool,
        skip_review_required: bool,
        learn_variants: bool,
        show_candidates: bool,
    ) -> None:
        rows: list[tuple[str, str]] = []
        if learn_variants:
            rows.extend(
                [
                    (
                        "Unknown candidates",
                        "You will be prompted when a search hit contains a matching-looking bibliography line with no active replacement rule yet.",
                    ),
                    (
                        "Variant keys",
                        "`r` add to review_variants.json, `i` add to ignored_variants.json, `s` skip for this run.",
                    ),
                ]
            )
            if has_review_required_rules:
                rows.append(
                    (
                        "Manual-review matches",
                        "With Learn variants enabled, heuristic/manual-review matches can be learned or edited before saving, or promoted to review_variants.json for future exact replacement.",
                    )
                )
        if apply and not assume_yes:
            rows.extend(
                [
                    ("Matched pages", "You will be prompted before saving each matched page."),
                    (
                        "Save keys",
                        "`y` save, `n` skip, `a` save all remaining safe matches, `e` edit summary, `q` quit the run.",
                    ),
                ]
            )
        if apply and has_review_required_rules:
            rows.append(
                (
                    "Manual review",
                    "Heuristic matches or entry/title mismatches still stop for confirmation even after `a` or `--yes`.",
                )
            )
        if apply and skip_review_required:
            rows.append(
                (
                    "Skip review-required",
                    "Matches that still need manual verification are skipped automatically instead of prompting.",
                )
            )
        if show_candidates:
            rows.append(
                (
                    "Debug output",
                    "Pages without replacements will also print the candidate lines that still match the source filters.",
                )
            )
        if rows:
            rows.append(
                (
                    "Input",
                    "Interactive prompts accept one key directly. Press `r`, `i`, `s`, `y`, `n`, `a`, `e`, or `q` without Enter.",
                )
            )

        if not rows:
            return

        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        for label, detail in rows:
            table.add_row(label, detail)
        self.print(Panel(table, title="Interactive guidance", border_style="magenta"))

    def print_processing_page(self, *, index: int, total: int, title: str) -> None:
        self.info(f"[queue] {index}/{total}: {title}")

    def print_state_counts(
        self,
        *,
        total_hits: int,
        titles: int,
        base_rules: int,
        review_variants: int,
        active_rules: int,
        ignored_variants: int,
    ) -> None:
        table = Table(title="Source state")
        table.add_column("Metric", style="" if self.no_color else "bold cyan")
        table.add_column("Value", justify="right")
        table.add_row("Search total hits", str(total_hits))
        table.add_row("Collected titles", str(titles))
        table.add_row("JSON rules", str(base_rules))
        table.add_row("Review variants", str(review_variants))
        table.add_row("Active rules this run", str(active_rules))
        table.add_row("Ignored variants", str(ignored_variants))
        self.print(table)

    def track_titles(self, titles: list[str], description: str):
        return track(
            titles,
            description=description,
            console=self.console,
            disable=not titles,
        )

    @contextmanager
    def status(self, message: str):
        with self.console.status(message):
            yield

    def build_bulk_status_panel(self, status: BulkRunStatus) -> Panel:
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        phase_value = status.phase
        if status.phase_elapsed > 0:
            phase_value = f"{phase_value} ({format_elapsed(status.phase_elapsed)})"
        table.add_row("Source", status.source_label)
        table.add_row("Page", f"{status.current_index}/{status.total_pages}")
        table.add_row("Title", status.current_title or "n/a")
        table.add_row("Phase", phase_value)
        table.add_row("Detail", status.detail or "running")
        table.add_row("Processed", str(status.processed))
        table.add_row("Matched", str(status.matched))
        table.add_row("Saved", str(status.saved))
        table.add_row("Skipped", str(status.skipped))
        table.add_row("Failed", str(status.failed))
        table.add_row("Retries", str(status.retries))
        return Panel(table, title="Bulk apply status", border_style="cyan")

    def _bulk_status_line(self, status: BulkRunStatus) -> str:
        return (
            f"[bulk-status] {status.source_label} | "
            f"{status.current_index}/{status.total_pages} | "
            f"{status.phase} | "
            f"{status.current_title or 'n/a'} | "
            f"{status.detail or 'running'} | "
            f"processed={status.processed} matched={status.matched} saved={status.saved} "
            f"skipped={status.skipped} failed={status.failed} retries={status.retries}"
        )

    def _decision_label(self, result: ReplacementResult) -> str:
        if result.review_reasons:
            return "manual review required"
        return "safe to auto-apply"

    def _decision_reason(self, result: ReplacementResult) -> str:
        if result.review_reasons:
            return (
                "At least one value was inferred heuristically or disagrees with the page context, "
                "so operator confirmation is required."
            )
        return "All extracted values came from exact or already approved rules with no remaining ambiguity."

    def _bulk_progress_completed(self, status: BulkRunStatus) -> int:
        if status.phase in {"saved", "skip", "failed"}:
            return min(status.processed, status.total_pages)
        return min(max(status.processed - 1, 0), status.total_pages)

    def _ensure_run_progress(self, status: BulkRunStatus) -> None:
        if not self.console.is_terminal or self._screen_ui_suspend_depth > 0:
            return

        if self._run_progress is None:
            self._run_progress = Progress(
                SpinnerColumn(style="" if self.no_color else "cyan"),
                TextColumn("[progress]", style="" if self.no_color else "bold cyan"),
                BarColumn(bar_width=None),
                TextColumn("{task.completed}/{task.total}"),
                TextColumn("{task.fields[phase]}", style="" if self.no_color else "green"),
                TextColumn("{task.fields[title]}"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,
                auto_refresh=False,
            )
            self._run_progress.start()
            self._run_progress_task = self._run_progress.add_task(
                "bulk-apply",
                total=max(status.total_pages, 1),
                completed=self._bulk_progress_completed(status),
                phase=status.phase,
                title=status.current_title or "n/a",
            )
        elif self._run_progress_task is not None:
            self._run_progress.update(
                self._run_progress_task,
                total=max(status.total_pages, 1),
                completed=self._bulk_progress_completed(status),
                phase=status.phase,
                title=status.current_title or "n/a",
            )
        if self._run_progress is not None:
            self._run_progress.refresh()

    def _ensure_bulk_live(self) -> None:
        if self._bulk_status is None:
            return
        self._ensure_run_progress(self._bulk_status)
        line = self._bulk_status_line(self._bulk_status)
        if line == self._last_bulk_status_line:
            return
        self._last_bulk_status_line = line
        self.info(line)

    def _stop_run_progress(self) -> None:
        if self._run_progress is None:
            return
        self._run_progress.stop()
        self._run_progress = None
        self._run_progress_task = None

    def _stop_bulk_live(self) -> None:
        self._stop_run_progress()
        self._last_bulk_status_line = None

    def build_diff_text(
        self,
        *,
        old_text: str,
        new_text: str,
        context: int,
        highlight_terms: list[str] | None = None,
    ) -> Text:
        diff = difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
            n=context,
        )
        text = Text()
        highlight_terms = [item for item in (highlight_terms or []) if item]

        for line in diff:
            if line.startswith("@@"):
                style = "" if self.no_color else "bold cyan"
            elif line.startswith("+") and not line.startswith("+++"):
                style = "" if self.no_color else "green"
            elif line.startswith("-") and not line.startswith("---"):
                style = "" if self.no_color else "red"
            elif line.startswith("---") or line.startswith("+++"):
                style = "" if self.no_color else "bold white"
            else:
                style = "" if self.no_color else "dim"

            row = Text(line, style=style)
            for term in highlight_terms:
                row.highlight_words(
                    [term],
                    style="" if self.no_color else "bold yellow",
                    case_sensitive=True,
                )
            text.append(row)
            text.append("\n")

        return text

    def build_diff_panel(
        self,
        *,
        title: str,
        result: ReplacementResult,
        old_text: str,
        context: int,
    ) -> Panel:
        meta = Table.grid(padding=(0, 1))
        meta.add_column(style="" if self.no_color else "bold cyan")
        meta.add_column()
        meta.add_row("Page", title)
        meta.add_row("Replacements", str(result.replacements))
        meta.add_row(
            "Matched rules",
            ", ".join(dict.fromkeys(result.used_rule_names)) or "n/a",
        )
        meta.add_row(
            "Templates",
            ", ".join(dict.fromkeys(result.rendered_templates)) or "n/a",
        )
        meta.add_row(
            "Inferred pages",
            ", ".join(dict.fromkeys(result.page_arguments)) or "none",
        )
        meta.add_row(
            "Inferred entry",
            ", ".join(dict.fromkeys(result.entry_arguments)) or "none",
        )
        meta.add_row(
            "Decision",
            self._decision_label(result),
        )
        meta.add_row("Reason", self._decision_reason(result))
        if result.review_reasons:
            meta.add_row("Manual reasons", " ".join(dict.fromkeys(result.review_reasons)))
        for key, values in sorted(result.extra_argument_values.items()):
            meta.add_row(
                f"Inferred {key.replace('_', ' ')}",
                ", ".join(dict.fromkeys(values)) or "none",
            )

        diff_text = self.build_diff_text(
            old_text=old_text,
            new_text=result.text,
            context=context,
            highlight_terms=[
                *result.rendered_templates,
                *result.page_arguments,
                *result.entry_arguments,
                *[value for values in result.extra_argument_values.values() for value in values],
            ],
        )
        layout = Table.grid(padding=(0, 1))
        layout.add_row(meta)
        layout.add_row(diff_text)
        return Panel(layout, title="Proposed change", border_style="green")

    def print_diff_panel(
        self,
        *,
        title: str,
        result: ReplacementResult,
        old_text: str,
        context: int,
    ) -> None:
        self.print(
            self.build_diff_panel(
                title=title,
                result=result,
                old_text=old_text,
                context=context,
            )
        )

    def print_used_rule(self, rule: dict) -> None:
        self.info(f"[rule] {rule.get('kind')} -> {rule.get('replacement')}")

    def resolve_variant_excerpt(self, info: VariantInfo) -> tuple[str, int, int]:
        excerpt = info.source_excerpt or info.full_line
        match_start = info.excerpt_match_start
        match_end = info.excerpt_match_end
        if (
            not excerpt
            or match_start < 0
            or match_end < match_start
            or match_end > len(excerpt)
            or match_end == match_start
        ):
            excerpt = info.full_line
            match_start = 0
            match_end = len(info.full_line)
        return excerpt, match_start, match_end

    def build_variant_excerpt_text(self, info: VariantInfo) -> Text:
        excerpt, match_start, match_end = self.resolve_variant_excerpt(info)
        surrounding_style = "" if self.no_color else "white"
        matched_style = "" if self.no_color else "bold yellow"

        text = Text(excerpt[:match_start], style=surrounding_style)
        text.append(excerpt[match_start:match_end], style=matched_style)
        text.append(excerpt[match_end:], style=surrounding_style)
        return text

    def build_unknown_variant_panel(
        self,
        *,
        title: str,
        info: VariantInfo,
        spec: SourceSpec,
    ) -> Panel:
        suggested_template = spec.render_template(info.pages, info.entry, **info.extra_arguments)
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("Page", title)
        table.add_row("Review line", info.review_line)
        table.add_row("Normalized line", info.normalized_line)
        table.add_row("Suggested template", suggested_template)
        table.add_row("Extracted pages", info.pages or "none")
        table.add_row("Extracted entry", info.entry or "none")
        for key, value in sorted(info.extra_arguments.items()):
            table.add_row(
                f"Extracted {key.replace('_', ' ')}",
                value or "none",
            )

        preview_old, match_start, match_end = self.resolve_variant_excerpt(info)
        preview_new = f"{preview_old[:match_start]}{suggested_template}{preview_old[match_end:]}"
        preview_diff = self.build_diff_text(
            old_text=preview_old,
            new_text=preview_new,
            context=max(len(preview_old.splitlines()), len(preview_new.splitlines()), 1),
            highlight_terms=[
                suggested_template,
                *(item for item in [info.pages, info.entry] if item),
                *info.extra_arguments.values(),
            ],
        )

        body = Group(
            table,
            Text(""),
            Text("Source excerpt", style="" if self.no_color else "bold cyan"),
            self.build_variant_excerpt_text(info),
            Text(""),
            Text("Example diff", style="" if self.no_color else "bold cyan"),
            preview_diff,
        )
        return Panel(body, title="Unknown candidate variant", border_style="yellow")

    def print_unknown_variant(self, title: str, info: VariantInfo, spec: SourceSpec) -> None:
        self.print(
            self.build_unknown_variant_panel(
                title=title,
                info=info,
                spec=spec,
            )
        )

    def print_variant_controls(self) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("r", "Add this variant to review_variants.json for future promotion.")
        table.add_row("e", "Edit the replacement template and save an exact rule to rules.json.")
        table.add_row("i", "Ignore this variant in future runs.")
        table.add_row("s", "Skip this candidate and continue.")
        self.print(Panel(table, title="Variant review controls", border_style="yellow"))

    def print_review_match_controls(self) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row(
            "r",
            "Add the matched review-required line(s) to review_variants.json for future exact replacement.",
        )
        table.add_row("e", "Edit the replacement template and save an exact rule to rules.json.")
        table.add_row("i", "Ignore this review-required match in future learn runs.")
        table.add_row("s", "Skip this page for now.")
        self.print(Panel(table, title="Manual review controls", border_style="yellow"))

    def _supports_single_key_input(self) -> bool:
        return sys.stdin.isatty()

    def _read_single_key(self) -> str:
        if os.name == "nt":
            import msvcrt

            while True:
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()
                    continue
                return key

        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        original = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)
            if key == "\x1b":
                while select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.read(1)
            return key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)

    def prompt_choice(
        self,
        label: str,
        *,
        choices: list[str],
        default: str | None = None,
        screen_renderable=None,
    ) -> str:
        with self._suspend_screen_ui():
            normalized_choices = {choice.casefold(): choice for choice in choices}
            if not self._supports_single_key_input():
                if screen_renderable is not None:
                    self.print(screen_renderable)
                return Prompt.ask(
                    label,
                    choices=choices,
                    default=default,
                    console=self.console,
                )

            if screen_renderable is not None and self._supports_screen_ui():
                notice: str | None = None
                with self._live_screen(
                    self.build_choice_screen(
                        body=screen_renderable,
                        prompt=label,
                        notice=notice,
                    )
                ) as live:
                    while True:
                        if live is not None:
                            live.update(
                                self.build_choice_screen(
                                    body=screen_renderable,
                                    prompt=label,
                                    notice=notice,
                                ),
                                refresh=True,
                            )
                        raw = self._read_single_key()
                        if raw == "\x03":
                            raise KeyboardInterrupt
                        if raw in ("\r", "\n"):
                            if default is None:
                                notice = f"Press one of: {', '.join(choices)}"
                                continue
                            return default
                        choice = normalized_choices.get(raw.casefold())
                        if choice is None:
                            notice = f"Press one of: {', '.join(choices)}"
                            continue
                        return choice

            if screen_renderable is not None:
                self.print(screen_renderable)
            while True:
                self.console.print(
                    Text(label, style="" if self.no_color else "bold cyan"),
                    end=" ",
                )
                raw = self._read_single_key()
                if raw == "\x03":
                    raise KeyboardInterrupt
                if raw in ("\r", "\n"):
                    if default is None:
                        self.warn(f"Press one of: {', '.join(choices)}")
                        continue
                    choice = default
                else:
                    choice = normalized_choices.get(raw.casefold())
                    if choice is None:
                        self.warn(f"Press one of: {', '.join(choices)}")
                        continue
                self.console.print(choice)
                return choice

    def build_choice_screen(self, *, body, prompt: str, notice: str | None = None):
        footer = Table.grid(expand=True, padding=(0, 1))
        footer.add_column(style="" if self.no_color else "bold cyan")
        footer.add_column()
        footer.add_row("Prompt", prompt)
        if notice:
            footer.add_row("Notice", notice)
        return Group(
            body,
            Panel(footer, title="Input", border_style="cyan"),
        )

    def _checklist_window(
        self,
        *,
        option_count: int,
        cursor: int,
        notice: str | None,
    ) -> tuple[int, int]:
        footer_rows = 5 if notice else 4
        panel_chrome = 2
        visible_rows = max(6, self.console.size.height - footer_rows - panel_chrome)
        visible_rows = min(visible_rows, option_count)
        start = max(0, min(cursor - (visible_rows // 2), option_count - visible_rows))
        end = start + visible_rows
        return start, end

    def build_checklist_panel(
        self,
        title: str,
        options: list[ChecklistOption],
        *,
        selected: set[str],
        cursor: int,
        notice: str | None = None,
    ) -> Panel:
        start, end = self._checklist_window(
            option_count=len(options),
            cursor=cursor,
            notice=notice,
        )
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=1)
        table.add_column(width=4)
        table.add_column(no_wrap=True)
        table.add_column()

        for index in range(start, end):
            option = options[index]
            focused = index == cursor
            checked = option.value in selected

            marker = Text(">" if focused else " ")
            checkbox = Text(
                "[x]" if checked else "[ ]",
                style="" if self.no_color else ("bold green" if checked else "dim"),
            )
            label = Text(option.label)
            detail = Text(option.detail)

            if checked:
                label.stylize("" if self.no_color else "bold green")
            if focused:
                focus_style = "" if self.no_color else "black on bright_cyan"
                marker.stylize(focus_style)
                checkbox.stylize(focus_style)
                label.stylize(focus_style)
                detail.stylize(focus_style)
            elif not checked:
                detail.stylize("" if self.no_color else "dim")

            table.add_row(marker, checkbox, label, detail)

        footer = Table.grid(expand=True, padding=(0, 1))
        footer.add_column(style="" if self.no_color else "bold cyan")
        footer.add_column()
        footer.add_row(
            "Controls",
            "space toggle, j/k move, a select all, x clear, Enter continue, q cancel",
        )
        footer.add_row("Selected", f"{len(selected)}/{len(options)}")
        footer.add_row("Window", f"{start + 1}-{end} of {len(options)}")
        if start > 0 or end < len(options):
            footer.add_row(
                "Scroll",
                ("up/down available" if self.no_color else "j/k scroll through the full list"),
            )
        if notice:
            footer.add_row("Notice", notice)

        layout = Table.grid(expand=True)
        layout.add_row(table)
        layout.add_row(footer)
        return Panel(layout, title=title, border_style="cyan")

    def prompt_checklist(
        self,
        title: str,
        options: list[ChecklistOption],
        *,
        default_selected: tuple[str, ...] = (),
        allow_empty: bool = False,
    ) -> tuple[str, ...] | None:
        with self._suspend_screen_ui():
            if not options:
                return ()

            selected = {option.value for option in options if option.value in set(default_selected)}
            ordered_values = [option.value for option in options]

            if not self._supports_single_key_input():
                self.print(
                    self.build_checklist_panel(
                        title,
                        options,
                        selected=selected,
                        cursor=0,
                    )
                )
                valid = {option.value for option in options}
                while True:
                    raw = Prompt.ask(
                        f"{title} (comma-separated values, `all`, or `q` to cancel)",
                        console=self.console,
                    ).strip()
                    lowered = raw.casefold()
                    if lowered == "q":
                        return None
                    if lowered == "all":
                        return tuple(ordered_values)
                    chosen = [item.strip() for item in raw.split(",") if item.strip()]
                    unknown = [item for item in chosen if item not in valid]
                    if unknown:
                        self.warn(f"Unknown values: {', '.join(unknown)}")
                        continue
                    if not chosen and not allow_empty:
                        self.warn("Select at least one item or type q to cancel.")
                        continue
                    chosen_set = set(chosen)
                    return tuple(value for value in ordered_values if value in chosen_set)

            cursor = 0
            notice: str | None = None
            with self._live_screen(
                self.build_checklist_panel(
                    title,
                    options,
                    selected=selected,
                    cursor=cursor,
                    notice=notice,
                )
            ) as live:
                while True:
                    panel = self.build_checklist_panel(
                        title,
                        options,
                        selected=selected,
                        cursor=cursor,
                        notice=notice,
                    )
                    if live is not None:
                        live.update(panel, refresh=True)
                    else:
                        self.print(panel)

                    raw = self._read_single_key()
                    if raw == "\x03":
                        raise KeyboardInterrupt
                    key = raw.casefold()
                    notice = None

                    if key == "j":
                        cursor = (cursor + 1) % len(options)
                        continue
                    if key == "k":
                        cursor = (cursor - 1) % len(options)
                        continue
                    if raw == " ":
                        value = options[cursor].value
                        if value in selected:
                            selected.remove(value)
                        else:
                            selected.add(value)
                        continue
                    if key == "a":
                        selected = set(ordered_values)
                        continue
                    if key == "x":
                        selected.clear()
                        continue
                    if key == "q":
                        return None
                    if raw in ("\r", "\n"):
                        if selected or allow_empty:
                            return tuple(value for value in ordered_values if value in selected)
                        notice = "Select at least one item or press q to cancel."
                        continue

                    notice = "Use space, j, k, a, x, Enter, or q."

    def prompt_source_selection(self, specs: list[SourceSpec]) -> tuple[str, ...] | None:
        options = [
            ChecklistOption(
                value=spec.source_id,
                label=spec.source_id,
                detail=f"{spec.name} [{spec.template_name}]",
            )
            for spec in specs
        ]
        return self.prompt_checklist(
            "Select sources",
            options,
            allow_empty=False,
        )

    def prompt_run_mode(self) -> str | None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("d", "Dry-run: inspect matches without saving.")
        table.add_row("i", "Interactive apply: save with per-page confirmation.")
        table.add_row(
            "b", "Background apply: save safe matches automatically and skip review-required ones."
        )
        table.add_row("q", "Cancel the startup wizard.")
        panel = Panel(table, title="Run mode", border_style="magenta")
        choice = self.prompt_choice(
            "Choose run mode [d=dry-run, i=interactive apply, b=background apply, q=quit]",
            choices=["d", "i", "b", "q"],
            default="d",
            screen_renderable=panel,
        )
        if choice == "q":
            return None
        return choice

    def prompt_variant_action(self) -> str:
        with self._suspend_screen_ui():
            if not self._shown_variant_controls:
                self.print_variant_controls()
                self._shown_variant_controls = True
            return self.prompt_choice(
                "Choose variant action [r=review, e=edit, i=ignore, s=skip]",
                choices=["r", "e", "i", "s"],
                default="s",
            )

    def prompt_review_match_action(self) -> str:
        with self._suspend_screen_ui():
            if not self._shown_review_match_controls:
                self.print_review_match_controls()
                self._shown_review_match_controls = True
            return self.prompt_choice(
                "Choose review action [r=learn exact, e=edit, i=ignore, s=skip]",
                choices=["r", "e", "i", "s"],
                default="s",
            )

    def prompt_template_text(self, default_template: str) -> str:
        return self.prompt_text("Replacement template", default=default_template)

    def prompt_text(self, label: str, *, default: str | None = None) -> str:
        with self._suspend_screen_ui():
            if default is None:
                return Prompt.ask(label, console=self.console)
            return Prompt.ask(label, default=default, console=self.console)

    def prompt_optional_text(self, label: str, *, default: str = "") -> str | None:
        with self._suspend_screen_ui():
            value = Prompt.ask(label, default=default, console=self.console).strip()
            return value or None

    def prompt_int(
        self,
        label: str,
        *,
        default: int,
        minimum: int = 0,
    ) -> int:
        with self._suspend_screen_ui():
            while True:
                raw = Prompt.ask(label, default=str(default), console=self.console).strip()
                try:
                    value = int(raw)
                except ValueError:
                    self.warn("Enter a whole number.")
                    continue
                if value < minimum:
                    self.warn(f"Enter a value >= {minimum}.")
                    continue
                return value

    def prompt_csv(
        self,
        label: str,
        *,
        default: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        with self._suspend_screen_ui():
            if default:
                raw = Prompt.ask(label, default=", ".join(default), console=self.console)
            else:
                raw = Prompt.ask(label, console=self.console)
            items = [item.strip() for item in raw.split(",") if item.strip()]
            return tuple(items)

    def confirm(self, label: str, *, default: bool = True) -> bool:
        with self._suspend_screen_ui():
            return Confirm.ask(label, default=default, console=self.console)

    def print_page_controls(self) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("y", "Save this page.")
        table.add_row("n", "Skip this page.")
        table.add_row(
            "a",
            "Save this page and all remaining safe pages. Review-required pages will still pause.",
        )
        table.add_row("e", "Edit the summary for the rest of the run.")
        table.add_row("q", "Stop the run immediately.")
        self.print(Panel(table, title="Save controls", border_style="green"))

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str:
        with self._suspend_screen_ui():
            if not self._shown_page_controls:
                self.print_page_controls()
                self._shown_page_controls = True
            self.info(f"Current edit summary: {current_summary}")
            if review_required:
                self.warn(
                    "Manual review is required for this change. `a` saves this page now, but later "
                    "manual-review changes will still pause."
                )
            return self.prompt_choice(
                "Choose page action [y=save, n=skip, a=save all safe, e=edit summary, q=quit]",
                choices=["y", "n", "a", "e", "q"],
                default="n",
            )

    def prompt_summary(self, current_summary: str) -> str:
        with self._suspend_screen_ui():
            return Prompt.ask(
                "New edit summary",
                default=current_summary,
                console=self.console,
            )

    def print_candidate_lines(self, title: str, lines: list[str]) -> None:
        if not lines:
            self.warn(f"[debug] {title}: the source no longer contains any candidate lines.")
            return

        table = Table(title=f"Candidate lines still matching search in {title}")
        table.add_column("Line")
        for line in lines:
            table.add_row(line)
        self.print(table)

    def build_final_summary(self, stats: RunStats):
        table = Table(title="Run summary")
        table.add_column("Metric", style="" if self.no_color else "bold cyan")
        table.add_column("Value", justify="right")
        table.add_row("Processed", str(stats.processed))
        table.add_row("Matched", str(stats.matched))
        table.add_row("Saved", str(stats.saved))
        table.add_row("Skipped", str(stats.skipped))
        table.add_row("Failed", str(stats.failed))
        table.add_row("Errors", str(stats.errors))
        table.add_row("Retry attempts", str(stats.retry_events))
        table.add_row("Learned variants", str(stats.learned))
        table.add_row("Ignored variants", str(stats.ignored))
        if not stats.failed_titles:
            return table

        failures = Table(title="Failed pages")
        failures.add_column("Title", style="" if self.no_color else "bold red")
        for title in stats.failed_titles:
            failures.add_row(title)
        return Group(table, failures)

    def print_final_summary(self, stats: RunStats) -> None:
        self.print(self.build_final_summary(stats))

    def print_startup_run_summary(
        self,
        *,
        source_ids: tuple[str, ...],
        mode_label: str,
        options: dict[str, str],
        command_preview: str,
    ) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("Sources", ", ".join(source_ids))
        table.add_row("Mode", mode_label)
        for key, value in options.items():
            table.add_row(key, value)
        table.add_row("Command", command_preview)
        self.print(Panel(table, title="Startup run summary", border_style="green"))
