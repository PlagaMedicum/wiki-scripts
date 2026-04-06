from __future__ import annotations

import difflib
import os
import sys
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.prompt import Confirm
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from bewiki_biblio.models import ReplacementResult, RunStats, SourceSpec, VariantInfo


class AppUI:
    def __init__(self, *, no_color: bool = False, console: Console | None = None) -> None:
        self.no_color = no_color
        self.console = console or Console(
            no_color=no_color,
            highlight=False,
            soft_wrap=False,
        )
        self._shown_variant_controls = False
        self._shown_page_controls = False

    def print(self, renderable) -> None:
        self.console.print(renderable)

    def info(self, message: str) -> None:
        self.console.print(message)

    def warn(self, message: str) -> None:
        style = "" if self.no_color else "yellow"
        self.console.print(message, style=style)

    def error(self, message: str) -> None:
        style = "" if self.no_color else "bold red"
        self.console.print(message, style=style)

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
        learn_variants: bool,
        show_candidates: bool,
    ) -> None:
        rows: list[tuple[str, str]] = []
        if learn_variants:
            rows.extend(
                [
                    ("Unknown candidates", "You will be prompted when a search hit contains a matching-looking bibliography line with no active replacement rule yet."),
                    ("Variant keys", "`r` add to review_variants.json, `i` add to ignored_variants.json, `s` skip for this run."),
                ]
            )
        if apply and not assume_yes:
            rows.extend(
                [
                    ("Matched pages", "You will be prompted before saving each matched page."),
                    ("Save keys", "`y` save, `n` skip, `a` save all remaining safe matches, `e` edit summary, `q` quit the run."),
                ]
            )
        if apply and has_review_required_rules:
            rows.append(
                (
                    "Manual review",
                    "Heuristic matches or entry/title mismatches still stop for confirmation even after `a` or `--yes`.",
                )
            )
        if show_candidates:
            rows.append(
                ("Debug output", "Pages without replacements will also print the candidate lines that still match the source filters.")
            )
        if rows:
            rows.append(
                ("Input", "Interactive prompts accept one key directly. Press `r`, `i`, `s`, `y`, `n`, `a`, `e`, or `q` without Enter.")
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
        self.info(f"Processing page {index}/{total}: {title}")

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

    def build_diff_text(
        self,
        *,
        old_text: str,
        new_text: str,
        context: int,
        rendered_templates: list[str],
        page_arguments: list[str],
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
        highlight_terms = [item for item in rendered_templates + page_arguments if item]

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
            "Rules",
            ", ".join(dict.fromkeys(result.used_rule_names)) or "n/a",
        )
        meta.add_row(
            "Templates",
            ", ".join(dict.fromkeys(result.rendered_templates)) or "n/a",
        )
        meta.add_row(
            "Page args",
            ", ".join(dict.fromkeys(result.page_arguments)) or "none",
        )
        meta.add_row(
            "Entry args",
            ", ".join(dict.fromkeys(result.entry_arguments)) or "none",
        )
        meta.add_row(
            "Review",
            "required" if result.review_reasons else "automatic",
        )
        if result.review_reasons:
            meta.add_row("Review reasons", " ".join(dict.fromkeys(result.review_reasons)))
        for key, values in sorted(result.extra_argument_values.items()):
            meta.add_row(
                f"{key.replace('_', ' ').title()} args",
                ", ".join(dict.fromkeys(values)) or "none",
            )

        diff_text = self.build_diff_text(
            old_text=old_text,
            new_text=result.text,
            context=context,
            rendered_templates=result.rendered_templates,
            page_arguments=result.page_arguments,
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
        self.info(
            f"[rule] {rule.get('kind')} -> {rule.get('replacement')}"
        )

    def print_unknown_variant(self, title: str, info: VariantInfo, spec: SourceSpec) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("Page", title)
        table.add_row("Full line", info.full_line)
        table.add_row("Review line", info.review_line)
        table.add_row("Normalized line", info.normalized_line)
        table.add_row(
            "Suggested template",
            spec.render_template(info.pages, info.entry, **info.extra_arguments),
        )
        table.add_row("Extracted pages", info.pages or "none")
        table.add_row("Extracted entry", info.entry or "none")
        for key, value in sorted(info.extra_arguments.items()):
            table.add_row(
                f"Extracted {key.replace('_', ' ')}",
                value or "none",
            )
        self.print(Panel(table, title="Unknown candidate variant", border_style="yellow"))

    def print_variant_controls(self) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("r", "Add this variant to review_variants.json for future promotion.")
        table.add_row("i", "Ignore this variant in future runs.")
        table.add_row("s", "Skip this candidate and continue.")
        self.print(Panel(table, title="Variant review controls", border_style="yellow"))

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
    ) -> str:
        normalized_choices = {choice.casefold(): choice for choice in choices}
        if not self._supports_single_key_input():
            return Prompt.ask(
                label,
                choices=choices,
                default=default,
                console=self.console,
            )

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

    def prompt_variant_action(self) -> str:
        if not self._shown_variant_controls:
            self.print_variant_controls()
            self._shown_variant_controls = True
        return self.prompt_choice(
            "Choose variant action [r=review, i=ignore, s=skip]",
            choices=["r", "i", "s"],
            default="s",
        )

    def prompt_text(self, label: str, *, default: str | None = None) -> str:
        if default is None:
            return Prompt.ask(label, console=self.console)
        return Prompt.ask(label, default=default, console=self.console)

    def prompt_csv(
        self,
        label: str,
        *,
        default: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        if default:
            raw = Prompt.ask(label, default=", ".join(default), console=self.console)
        else:
            raw = Prompt.ask(label, console=self.console)
        items = [item.strip() for item in raw.split(",") if item.strip()]
        return tuple(items)

    def confirm(self, label: str, *, default: bool = True) -> bool:
        return Confirm.ask(label, default=default, console=self.console)

    def print_page_controls(self) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="" if self.no_color else "bold cyan")
        table.add_column()
        table.add_row("y", "Save this page.")
        table.add_row("n", "Skip this page.")
        table.add_row("a", "Save this page and all remaining non-review-required pages.")
        table.add_row("e", "Edit the summary for the rest of the run.")
        table.add_row("q", "Stop the run immediately.")
        self.print(Panel(table, title="Save controls", border_style="green"))

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str:
        if not self._shown_page_controls:
            self.print_page_controls()
            self._shown_page_controls = True
        self.info(f"Current edit summary: {current_summary}")
        if review_required:
            self.warn("Manual review is required for this change. Bulk apply is paused.")
        return self.prompt_choice(
            "Choose page action [y=save, n=skip, a=save all, e=edit summary, q=quit]",
            choices=["y", "n", "a", "e", "q"],
            default="n",
        )

    def prompt_summary(self, current_summary: str) -> str:
        return Prompt.ask(
            "New edit summary",
            default=current_summary,
            console=self.console,
        )

    def print_candidate_lines(self, title: str, lines: list[str]) -> None:
        if not lines:
            self.warn(
                f"[debug] {title}: the source no longer contains any candidate lines."
            )
            return

        table = Table(title=f"Candidate lines still matching search in {title}")
        table.add_column("Line")
        for line in lines:
            table.add_row(line)
        self.print(table)

    def build_final_summary(self, stats: RunStats) -> Table:
        table = Table(title="Run summary")
        table.add_column("Metric", style="" if self.no_color else "bold cyan")
        table.add_column("Value", justify="right")
        table.add_row("Processed", str(stats.processed))
        table.add_row("Matched", str(stats.matched))
        table.add_row("Saved", str(stats.saved))
        table.add_row("Skipped", str(stats.skipped))
        table.add_row("Errors", str(stats.errors))
        table.add_row("Learned variants", str(stats.learned))
        table.add_row("Ignored variants", str(stats.ignored))
        return table

    def print_final_summary(self, stats: RunStats) -> None:
        self.print(self.build_final_summary(stats))
