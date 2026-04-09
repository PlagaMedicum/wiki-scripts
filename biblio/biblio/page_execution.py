from __future__ import annotations

from typing import Protocol

from biblio.models import RunOptions, RunStats, SourceSpec
from biblio.page_analysis import PageAnalysis, candidate_debug_lines
from biblio.page_save import (
    _changed_bytes,
    _is_minor_edit,
    apply_page_save,
    plan_page_save,
)
from biblio.runtime import RunnerDependencies, WikiClient
from biblio.session import RunPolicy

__all__ = ["_changed_bytes", "_is_minor_edit", "execute_page"]


class PageExecutionUI(Protocol):
    def print_diff_panel(
        self,
        *,
        title: str,
        result,
        old_text: str,
        context: int,
    ) -> None: ...

    def print_used_rule(self, rule: dict) -> None: ...

    def print_candidate_lines(self, title: str, lines: list[str]) -> None: ...

    def prompt_review_match_action(self) -> str: ...

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str: ...

    def prompt_summary(self, current_summary: str) -> str: ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...


def execute_page(
    *,
    analysis: PageAnalysis,
    spec: SourceSpec,
    options: RunOptions,
    policy: RunPolicy,
    ui: PageExecutionUI,
    state,
    client: WikiClient,
    page,
    stats: RunStats,
    deps: RunnerDependencies,
) -> None:
    if analysis.result.replacements == 0:
        if options.show_candidates:
            ui.print_candidate_lines(
                analysis.title,
                candidate_debug_lines(analysis, spec, deps=deps),
            )
        ui.info(f"[skip] {analysis.title}: no replacements found")
        stats.skipped += 1
        return

    stats.matched += 1
    ui.print_diff_panel(
        title=analysis.title,
        result=analysis.result,
        old_text=analysis.old_text,
        context=options.context,
    )
    for rule in analysis.result.used_line_rules:
        ui.print_used_rule(rule)

    if options.learn_variants and not options.apply:
        manual_review_lines = analysis.manual_review_lines
        if manual_review_lines:
            choice = ui.prompt_review_match_action()
            if choice == "r":
                added = 0
                for line in manual_review_lines:
                    if state.add_review_variant(line):
                        added += 1
                if added:
                    stats.learned += added
                    ui.info(f"[review] Added {added} line(s) to review_variants.json")
            elif choice == "i":
                added = 0
                for line in manual_review_lines:
                    if state.add_ignored_hash(deps.variant_hash(deps.make_review_key(line, spec))):
                        added += 1
                if added:
                    stats.ignored += added
                    ui.info(f"[ignore] Added {added} line(s) to ignored_variants.json")
        elif analysis.review_required:
            ui.info(
                f"[review-known] {analysis.title}: manual-review lines are already learned or ignored"
            )
    if not options.apply:
        ui.info("[dry-run] No changes saved")
        return

    save_plan = plan_page_save(
        analysis=analysis,
        spec=spec,
        options=options,
        policy=policy,
        ui=ui,
        stats=stats,
    )
    if save_plan is None:
        return

    apply_page_save(
        plan=save_plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )
