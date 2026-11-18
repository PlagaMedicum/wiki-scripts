from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter, sleep
from typing import Protocol

from biblio.models import BulkRunStatus, RunOptions, RunStats, SourceSpec
from biblio.observability import format_elapsed, get_logger
from biblio.page_analysis import PageAnalysis
from biblio.runtime import PageEdit, WikiClient
from biblio.session import RunPolicy, prompt_page_decision
from biblio.transport import (
    is_retryable_transport_error,
    monitor_operation,
    transport_retry_delay,
)


class PageSaveUI(Protocol):
    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str: ...

    def prompt_summary(self, current_summary: str) -> str: ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def update_bulk_status(self, status: BulkRunStatus) -> None: ...


@dataclass(frozen=True)
class PageSavePlan:
    title: str
    old_text: str
    new_text: str
    summary: str
    minor_threshold: int
    used_line_rules: tuple[dict, ...]


@dataclass(frozen=True)
class PageSaveOutcome:
    saved: bool
    fatal: bool = False


def _changed_bytes(old_text: str, new_text: str) -> int:
    old_bytes = old_text.encode("utf-8")
    new_bytes = new_text.encode("utf-8")
    prefix = _common_prefix_length(old_bytes, new_bytes)
    suffix = _common_suffix_length(old_bytes, new_bytes, prefix)
    return len(old_bytes) - prefix - suffix + len(new_bytes) - prefix - suffix


def _common_prefix_length(old_bytes: bytes, new_bytes: bytes) -> int:
    length = min(len(old_bytes), len(new_bytes))
    index = 0
    while index < length and old_bytes[index] == new_bytes[index]:
        index += 1
    return index


def _common_suffix_length(old_bytes: bytes, new_bytes: bytes, prefix: int) -> int:
    max_suffix = min(len(old_bytes) - prefix, len(new_bytes) - prefix)
    index = 0
    while index < max_suffix and old_bytes[-(index + 1)] == new_bytes[-(index + 1)]:
        index += 1
    return index


def _is_minor_edit(old_text: str, new_text: str, threshold: int) -> bool:
    return _changed_bytes(old_text, new_text) < threshold


def _build_page_edit(
    *,
    old_text: str,
    new_text: str,
    summary: str,
    minor_threshold: int,
) -> PageEdit:
    return PageEdit(
        text=new_text,
        summary=summary,
        minor=_is_minor_edit(old_text, new_text, minor_threshold),
    )


def plan_page_save(
    *,
    analysis: PageAnalysis,
    spec: SourceSpec,
    options: RunOptions,
    policy: RunPolicy,
    ui: PageSaveUI,
    stats: RunStats,
    bulk_status: BulkRunStatus | None = None,
) -> PageSavePlan | None:
    current_summary = policy.current_summary(spec)
    if policy.should_skip_review_required(review_required=analysis.review_required):
        if policy.bulk_mode_active and bulk_status is not None:
            ui.update_bulk_status(
                replace(
                    bulk_status,
                    phase="skip",
                    detail="Review-required page skipped in bulk mode",
                )
            )
            ui.warn(
                f"[skip] {analysis.title}: review required; skipped in bulk mode. "
                + " ".join(analysis.result.review_reasons)
            )
        else:
            ui.warn("[review-skip] " + " ".join(analysis.result.review_reasons))
        stats.skipped += 1
        return None

    if policy.should_prompt_page(review_required=analysis.review_required):
        if analysis.review_required:
            if policy.bulk_mode_active:
                ui.warn(f"[pause] {analysis.title}: manual review required; waiting for operator.")
                if bulk_status is not None:
                    ui.update_bulk_status(
                        replace(
                            bulk_status,
                            phase="pause",
                            detail="Manual review required; waiting for operator",
                        )
                    )
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
        if decision.is_accept_all:
            ui.info(
                "[bulk] Safe pages will now save automatically. Manual-review pages will still pause."
            )
        if decision.is_skip:
            ui.info(f"[skip] {analysis.title}: not saved")
            stats.skipped += 1
            return None

    return PageSavePlan(
        title=analysis.title,
        old_text=analysis.old_text,
        new_text=analysis.result.text,
        summary=current_summary,
        minor_threshold=options.minor_threshold,
        used_line_rules=tuple(analysis.result.used_line_rules),
    )


def apply_page_save(
    *,
    plan: PageSavePlan,
    client: WikiClient,
    page=None,
    state,
    stats: RunStats,
    ui: PageSaveUI,
    bulk_status: BulkRunStatus | None = None,
) -> PageSaveOutcome:
    logger = get_logger()
    max_attempts = 4
    edit: PageEdit | None = None

    prepare_status = (
        None
        if bulk_status is None
        else replace(
            bulk_status,
            phase="prepare-save",
            detail="Building save payload and minor flag",
            phase_elapsed=0.0,
            processed=stats.processed,
            matched=stats.matched,
            saved=stats.saved,
            skipped=stats.skipped,
            failed=stats.failed,
            retries=stats.retry_events,
        )
    )
    if prepare_status is not None:
        ui.update_bulk_status(prepare_status)
    with monitor_operation(
        ui,
        start_message=f"[prepare-save] {plan.title}: building edit payload...",
        pending_message=f"[wait] {plan.title}: still building edit payload",
        on_heartbeat=(
            None
            if prepare_status is None
            else lambda elapsed: ui.update_bulk_status(
                replace(
                    prepare_status,
                    phase_elapsed=elapsed,
                    processed=stats.processed,
                    matched=stats.matched,
                    saved=stats.saved,
                    skipped=stats.skipped,
                    failed=stats.failed,
                    retries=stats.retry_events,
                )
            )
        ),
    ):
        edit = _build_page_edit(
            old_text=plan.old_text,
            new_text=plan.new_text,
            summary=plan.summary,
            minor_threshold=plan.minor_threshold,
        )

    for attempt in range(1, max_attempts + 1):
        started = perf_counter()
        try:
            preflight_status = (
                None
                if bulk_status is None
                else replace(
                    bulk_status,
                    phase="save-preflight",
                    detail="Verifying write session state",
                    phase_elapsed=0.0,
                    processed=stats.processed,
                    matched=stats.matched,
                    saved=stats.saved,
                    skipped=stats.skipped,
                    failed=stats.failed,
                    retries=stats.retry_events,
                )
            )
            if preflight_status is not None:
                ui.update_bulk_status(preflight_status)
            with monitor_operation(
                ui,
                start_message=f"[save-preflight] {plan.title}: verifying write session...",
                pending_message=f"[wait] {plan.title}: still verifying write session",
                on_heartbeat=(
                    None
                    if preflight_status is None
                    else lambda elapsed: ui.update_bulk_status(
                        replace(
                            preflight_status,
                            phase_elapsed=elapsed,
                            processed=stats.processed,
                            matched=stats.matched,
                            saved=stats.saved,
                            skipped=stats.skipped,
                            failed=stats.failed,
                            retries=stats.retry_events,
                        )
                    )
                ),
            ):
                client.prime_write_session()
            if bulk_status is not None:
                ui.update_bulk_status(
                    replace(
                        bulk_status,
                        phase="save",
                        detail="Publishing edit to the wiki",
                        phase_elapsed=0.0,
                        processed=stats.processed,
                        matched=stats.matched,
                        saved=stats.saved,
                        skipped=stats.skipped,
                        failed=stats.failed,
                        retries=stats.retry_events,
                    )
                )
            with monitor_operation(
                ui,
                start_message=f"[save] {plan.title}: publishing edit...",
                pending_message=f"[wait] {plan.title}: still publishing edit",
                on_heartbeat=(
                    None
                    if bulk_status is None
                    else lambda elapsed: ui.update_bulk_status(
                        replace(
                            bulk_status,
                            phase="save",
                            detail="Publishing edit to the wiki",
                            phase_elapsed=elapsed,
                            processed=stats.processed,
                            matched=stats.matched,
                            saved=stats.saved,
                            skipped=stats.skipped,
                            failed=stats.failed,
                            retries=stats.retry_events,
                        )
                    )
                ),
            ):
                target = page if page is not None else plan.title
                client.save_page(target, edit)
            elapsed = perf_counter() - started
            stats.saved += 1
            logger.info(
                "saved page title=%s seconds=%.3f minor=%s attempt=%s",
                plan.title,
                elapsed,
                edit.minor,
                attempt,
            )
            ui.info(f"[saved] {plan.title}: edit published in {format_elapsed(elapsed)}")
            if elapsed >= 5:
                ui.warn(f"[delay] {plan.title}: save finished in {format_elapsed(elapsed)}")
            if bulk_status is not None:
                ui.update_bulk_status(
                    replace(
                        bulk_status,
                        phase="saved",
                        detail=f"Edit published in {format_elapsed(elapsed)}",
                        phase_elapsed=elapsed,
                        processed=stats.processed,
                        matched=stats.matched,
                        saved=stats.saved,
                        skipped=stats.skipped,
                        failed=stats.failed,
                        retries=stats.retry_events,
                    )
                )

            promoted = False
            for rule in plan.used_line_rules:
                if state.ensure_rule_saved(rule):
                    promoted = True
            if promoted:
                ui.info("[rules] Promoted new review rules into rules.json")
            return PageSaveOutcome(saved=True)
        except Exception as exc:
            elapsed = perf_counter() - started
            if is_retryable_transport_error(exc) and attempt < max_attempts:
                delay = transport_retry_delay(attempt)
                stats.retry_events += 1
                logger.warning(
                    "save retry title=%s seconds=%.3f attempt=%s delay=%.3f error=%s",
                    plan.title,
                    elapsed,
                    attempt,
                    delay,
                    exc,
                )
                ui.warn(
                    f"[retry] {plan.title}: save failed ({exc}). Reconnecting and retrying in {format_elapsed(delay)} "
                    f"[attempt {attempt}/{max_attempts - 1}]"
                )
                try:
                    client.reconnect()
                except Exception as reconnect_exc:
                    logger.warning(
                        "save reconnect failed title=%s attempt=%s error=%s",
                        plan.title,
                        attempt,
                        reconnect_exc,
                    )
                    ui.warn(f"[retry] {plan.title}: reconnect failed ({reconnect_exc})")
                if bulk_status is not None:
                    ui.update_bulk_status(
                        replace(
                            bulk_status,
                            phase="retry",
                            detail=f"Retrying save in {format_elapsed(delay)}",
                            phase_elapsed=elapsed,
                            processed=stats.processed,
                            matched=stats.matched,
                            saved=stats.saved,
                            skipped=stats.skipped,
                            failed=stats.failed,
                            retries=stats.retry_events,
                        )
                    )
                sleep(delay)
                continue

            if is_retryable_transport_error(exc):
                stats.failed += 1
                stats.failed_titles.append(plan.title)
                logger.error(
                    "save failed after retries title=%s seconds=%.3f attempt=%s error=%s",
                    plan.title,
                    elapsed,
                    attempt,
                    exc,
                )
                ui.error(f"[failed] {plan.title}: save failed after retries ({exc})")
                if bulk_status is not None:
                    ui.update_bulk_status(
                        replace(
                            bulk_status,
                            phase="failed",
                            detail=f"Save failed after retries: {exc}",
                            phase_elapsed=elapsed,
                            processed=stats.processed,
                            matched=stats.matched,
                            saved=stats.saved,
                            skipped=stats.skipped,
                            failed=stats.failed,
                            retries=stats.retry_events,
                        )
                    )
                return PageSaveOutcome(saved=False, fatal=False)

            stats.errors += 1
            logger.error(
                "save failed title=%s seconds=%.3f attempt=%s error=%s",
                plan.title,
                elapsed,
                attempt,
                exc,
            )
            ui.error(f"[error] {plan.title}: {exc}")
            return PageSaveOutcome(saved=False, fatal=True)
