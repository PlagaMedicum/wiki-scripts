from __future__ import annotations

import difflib
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from biblio.models import RunOptions, RunStats, SourceSpec
from biblio.observability import format_elapsed, get_logger
from biblio.page_analysis import PageAnalysis
from biblio.runtime import PageEdit, WikiClient
from biblio.session import RunPolicy, prompt_page_decision


class PageSaveUI(Protocol):
    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str: ...

    def prompt_summary(self, current_summary: str) -> str: ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...


@dataclass(frozen=True)
class PageSavePlan:
    title: str
    edit: PageEdit
    used_line_rules: tuple[dict, ...]


def _changed_bytes(old_text: str, new_text: str) -> int:
    old_bytes = old_text.encode("utf-8")
    new_bytes = new_text.encode("utf-8")
    matcher = difflib.SequenceMatcher(None, old_bytes, new_bytes, autojunk=False)
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += (i2 - i1) + (j2 - j1)
    return changed


def _is_minor_edit(old_text: str, new_text: str, threshold: int) -> bool:
    return _changed_bytes(old_text, new_text) < threshold


def _build_page_edit(
    *,
    analysis: PageAnalysis,
    summary: str,
    minor_threshold: int,
) -> PageEdit:
    return PageEdit(
        text=analysis.result.text,
        summary=summary,
        minor=_is_minor_edit(analysis.old_text, analysis.result.text, minor_threshold),
    )


def plan_page_save(
    *,
    analysis: PageAnalysis,
    spec: SourceSpec,
    options: RunOptions,
    policy: RunPolicy,
    ui: PageSaveUI,
    stats: RunStats,
) -> PageSavePlan | None:
    current_summary = policy.current_summary(spec)
    if policy.should_skip_review_required(review_required=analysis.review_required):
        ui.warn("[review-skip] " + " ".join(analysis.result.review_reasons))
        stats.skipped += 1
        return None

    if policy.should_prompt_page(review_required=analysis.review_required):
        if analysis.review_required:
            ui.warn("[review-required] " + " ".join(analysis.result.review_reasons))
        decision = prompt_page_decision(
            ui,
            current_summary,
            review_required=analysis.review_required,
        )
        policy.apply_page_decision(decision)
        current_summary = policy.current_summary(spec)
        if decision.is_quit:
            ui.warn("Stopped by user.")
            return None
        if decision.is_skip:
            ui.info(f"[skip] {analysis.title}: not saved")
            stats.skipped += 1
            return None

    return PageSavePlan(
        title=analysis.title,
        edit=_build_page_edit(
            analysis=analysis,
            summary=current_summary,
            minor_threshold=options.minor_threshold,
        ),
        used_line_rules=tuple(analysis.result.used_line_rules),
    )


def apply_page_save(
    *,
    plan: PageSavePlan,
    client: WikiClient,
    page,
    state,
    stats: RunStats,
    ui: PageSaveUI,
) -> bool:
    logger = get_logger()
    ui.info(f"[save] {plan.title}: saving...")
    started = perf_counter()
    try:
        client.save_page(page, plan.edit)
        elapsed = perf_counter() - started
        stats.saved += 1
        logger.info(
            "saved page title=%s seconds=%.3f minor=%s",
            plan.title,
            elapsed,
            plan.edit.minor,
        )
        if elapsed >= 5:
            ui.warn(f"[delay] {plan.title}: save finished in {format_elapsed(elapsed)}")

        promoted = False
        for rule in plan.used_line_rules:
            if state.ensure_rule_saved(rule):
                promoted = True
        if promoted:
            ui.info("[rules] Promoted new review rules into rules.json")
        return True
    except Exception as exc:
        elapsed = perf_counter() - started
        stats.errors += 1
        logger.error(
            "save failed title=%s seconds=%.3f error=%s",
            plan.title,
            elapsed,
            exc,
        )
        ui.error(f"[error] {plan.title}: {exc}")
        return False
