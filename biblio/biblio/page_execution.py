from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from biblio.models import BulkRunStatus, RunOptions, RunStats, SourceSpec
from biblio.page_analysis import PageAnalysis, analyze_page, candidate_debug_lines
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

    def prompt_template_text(self, default_template: str) -> str: ...

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str: ...

    def prompt_summary(self, current_summary: str) -> str: ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def begin_bulk_run(self, status: BulkRunStatus) -> None: ...

    def update_bulk_status(self, status: BulkRunStatus) -> None: ...

    def finish_bulk_run(self) -> None: ...


def _handle_review_learning(
    *,
    analysis: PageAnalysis,
    spec: SourceSpec,
    options: RunOptions,
    ui: PageExecutionUI,
    state,
    stats: RunStats,
    deps: RunnerDependencies,
) -> PageAnalysis | None:
    if not options.learn_variants:
        return analysis

    manual_review_lines = analysis.manual_review_lines
    if not manual_review_lines:
        if analysis.review_required:
            ui.info(
                f"[review-known] {analysis.title}: manual-review lines are already learned or ignored"
            )
        return analysis

    choice = ui.prompt_review_match_action()
    should_reanalyze = False

    if choice == "r":
        added = 0
        for line in manual_review_lines:
            if state.add_review_variant(line):
                added += 1
        if added:
            stats.learned += added
            ui.info(f"[review] Added {added} line(s) to review_variants.json")
            should_reanalyze = options.apply
    elif choice == "e":
        if len(manual_review_lines) != 1 or len(analysis.result.rendered_templates) != 1:
            ui.warn(
                "[edit] Manual template edit requires exactly one review line and one rendered template on the page."
            )
        else:
            replacement = ui.prompt_template_text(analysis.result.rendered_templates[0])
            if not replacement.strip():
                ui.warn("[edit] Empty replacement ignored.")
            else:
                if state.add_exact_rule(manual_review_lines[0], replacement):
                    stats.learned += 1
                    ui.info("[rules] Added exact line rule to rules.json")
                else:
                    ui.info("[rules] Exact line rule already exists in rules.json")
                should_reanalyze = options.apply
    elif choice == "i":
        added = 0
        for line in manual_review_lines:
            if state.add_ignored_hash(deps.variant_hash(deps.make_review_key(line, spec))):
                added += 1
        if added:
            stats.ignored += added
            ui.info(f"[ignore] Added {added} line(s) to ignored_variants.json")
            should_reanalyze = options.apply
    elif choice == "s" and options.apply:
        ui.info(f"[skip] {analysis.title}: not saved")
        stats.skipped += 1
        return None

    if not should_reanalyze:
        return analysis

    return analyze_page(
        analysis.title,
        analysis.old_text,
        spec=spec,
        state=state,
        deps=deps,
    )


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
    source_label: str,
    page_index: int,
    total_pages: int,
    stats: RunStats,
    deps: RunnerDependencies,
) -> None:
    bulk_status = BulkRunStatus(
        source_label=source_label,
        total_pages=total_pages,
        current_index=page_index,
        current_title=analysis.title,
        phase="queue",
        detail="Page queued for evaluation",
        processed=stats.processed,
        matched=stats.matched,
        saved=stats.saved,
        skipped=stats.skipped,
        failed=stats.failed,
        retries=stats.retry_events,
    )

    if analysis.result.replacements == 0:
        if policy.bulk_mode_active:
            ui.update_bulk_status(
                replace(
                    bulk_status,
                    phase="skip",
                    detail="No replacements found",
                )
            )
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

    analysis = _handle_review_learning(
        analysis=analysis,
        spec=spec,
        options=options,
        ui=ui,
        state=state,
        stats=stats,
        deps=deps,
    )
    if analysis is None:
        return

    if not options.apply:
        ui.info("[dry-run] No changes saved")
        return

    was_bulk_mode_active = policy.bulk_mode_active
    if policy.bulk_mode_active and analysis.review_required:
        ui.update_bulk_status(
            replace(
                bulk_status,
                phase="pause",
                detail="Manual review required; waiting for operator",
            )
        )

    save_plan = plan_page_save(
        analysis=analysis,
        spec=spec,
        options=options,
        policy=policy,
        ui=ui,
        stats=stats,
        bulk_status=bulk_status if policy.bulk_mode_active else None,
    )
    if save_plan is None:
        return

    status_for_save = bulk_status if options.apply else None
    if options.apply:
        prepare_status = replace(
            bulk_status,
            phase="prepare-save",
            detail=(
                "Bulk mode activated; preparing current page for save"
                if not was_bulk_mode_active and policy.bulk_mode_active
                else "Preparing current page for save"
            ),
        )
        if not was_bulk_mode_active and policy.bulk_mode_active:
            ui.begin_bulk_run(prepare_status)
        else:
            ui.update_bulk_status(prepare_status)

    outcome = apply_page_save(
        plan=save_plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
        bulk_status=status_for_save,
    )
    if options.apply and not policy.bulk_mode_active:
        ui.finish_bulk_run()
    if not outcome.saved and outcome.fatal:
        policy.stopped = True
        ui.warn("Stopped after save failure.")
