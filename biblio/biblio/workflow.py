from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter, sleep
from typing import Protocol

from biblio.bootstrap import BotRightRequiredError, create_site
from biblio.engine import (
    debug_candidate_lines,
    extract_unknown_variant_infos,
    replace_text,
    variant_review_hash,
    variant_review_key,
)
from biblio.models import BulkRunStatus, RunOptions, RunStats, SourceSpec
from biblio.observability import format_elapsed, get_logger
from biblio.page_analysis import analyze_page, learn_unknown_variants
from biblio.page_execution import execute_page
from biblio.query import build_search_query
from biblio.runtime import RunnerDependencies, WikiClientPool
from biblio.session import RunPolicy, needs_interactive_input
from biblio.specs import discover_source_specs, load_source_spec, project_root
from biblio.state import load_source_state, variant_hash
from biblio.text import entry_matches_page_title, make_review_key
from biblio.transport import (
    is_retryable_transport_error,
    monitor_operation,
    set_transport_wait_reporter,
    transport_retry_delay,
)


class RunUI(Protocol):
    no_color: bool

    def print_sources(self, specs: list[SourceSpec]) -> None: ...

    def print_startup_panel(
        self,
        spec: SourceSpec,
        *,
        query: str,
        limit: int,
        apply: bool,
        summary: str,
        source_label: str | None = None,
    ) -> None: ...

    def print_run_guidance(
        self,
        *,
        apply: bool,
        assume_yes: bool,
        has_review_required_rules: bool,
        skip_review_required: bool,
        learn_variants: bool,
        show_candidates: bool,
    ) -> None: ...

    def print_state_counts(
        self,
        *,
        total_hits: int,
        titles: int,
        base_rules: int,
        review_variants: int,
        active_rules: int,
        ignored_variants: int,
    ) -> None: ...

    def print_processing_page(self, *, index: int, total: int, title: str) -> None: ...

    def print_diff_panel(
        self,
        *,
        title: str,
        result,
        old_text: str,
        context: int,
    ) -> None: ...

    def print_used_rule(self, rule: dict) -> None: ...

    def print_unknown_variant(self, title: str, info, spec: SourceSpec) -> None: ...

    def prompt_review_match_action(self) -> str: ...

    def prompt_variant_action(self) -> str: ...

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str: ...

    def prompt_summary(self, current_summary: str) -> str: ...

    def print_candidate_lines(self, title: str, lines: list[str]) -> None: ...

    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def print_final_summary(self, stats: RunStats) -> None: ...

    def begin_bulk_run(self, status: BulkRunStatus) -> None: ...

    def update_bulk_status(self, status: BulkRunStatus) -> None: ...

    def finish_bulk_run(self) -> None: ...

    def report_transport_wait(self, message: str) -> None: ...

    def status(self, message: str): ...

    def track_titles(self, titles: list[str], description: str): ...


def _build_dependencies() -> RunnerDependencies:
    return RunnerDependencies(
        load_source_spec=load_source_spec,
        load_source_state=load_source_state,
        create_site=create_site,
        load_titles=_load_titles,
        build_search_query=build_search_query,
        replace_text=replace_text,
        extract_unknown_variant_infos=extract_unknown_variant_infos,
        debug_candidate_lines=debug_candidate_lines,
        variant_review_key=variant_review_key,
        variant_review_hash=variant_review_hash,
        variant_hash=variant_hash,
        make_review_key=make_review_key,
        entry_matches_page_title=entry_matches_page_title,
    )


def _load_titles(site, query: str, limit: int) -> tuple[int, list[str]]:
    from pywikibot import pagegenerators

    debug_request = site.simple_request(
        action="query",
        list="search",
        srsearch=query,
        srnamespace=0,
        srinfo="totalhits",
        srlimit=1,
    )
    data = debug_request.submit()
    total_hits = int(data["query"]["searchinfo"]["totalhits"])

    search_gen = pagegenerators.SearchPageGenerator(
        query,
        total=limit,
        namespaces=[0],
        site=site,
        content=False,
        sort="title_natural_asc",
    )
    titles = [page.title() for page in search_gen]
    return total_hits, titles


def list_sources(ui: RunUI) -> int:
    specs = discover_source_specs()
    ui.print_sources(specs)
    return 0


def run_source(
    options: RunOptions,
    ui: RunUI,
    root: Path | None = None,
    *,
    deps: RunnerDependencies | None = None,
) -> int:
    return run_sources(options, ui, root=root, deps=deps)


def _stop_after_error(
    *,
    ui: RunUI,
    policy: RunPolicy,
    stats: RunStats,
    error_message: str,
    warning_message: str,
) -> None:
    stats.errors += 1
    ui.error(error_message)
    ui.warn(warning_message)
    policy.stopped = True


def _run_single_source(
    spec: SourceSpec,
    options: RunOptions,
    ui: RunUI,
    *,
    policy: RunPolicy,
    site_clients: WikiClientPool,
    source_index: int,
    source_total: int,
    deps: RunnerDependencies,
) -> RunStats:
    logger = get_logger()
    state = deps.load_source_state(spec)
    query = options.query or deps.build_search_query(spec)
    current_summary = policy.current_summary(spec)
    stats = RunStats()
    source_label = f"{spec.source_id} ({spec.name}) [{source_index}/{source_total}]"
    can_require_manual_review = any(rule.review_required for rule in spec.regex_rules)
    interactive_run = needs_interactive_input(
        options,
        accept_all=policy.accept_all,
        has_review_required_rules=can_require_manual_review,
    )

    ui.print_startup_panel(
        spec,
        query=query,
        limit=options.limit,
        apply=options.apply,
        summary=current_summary,
        source_label=source_label,
    )
    ui.print_run_guidance(
        apply=options.apply,
        assume_yes=policy.accept_all,
        has_review_required_rules=can_require_manual_review,
        skip_review_required=options.skip_review_required,
        learn_variants=options.learn_variants,
        show_candidates=options.show_candidates,
    )

    client = site_clients.get(spec)
    bulk_started = False

    if options.apply:
        try:
            _run_transport_operation(
                client=client,
                ui=ui,
                label=spec.source_id,
                operation_name="prime write session",
                start_message=f"[save-preflight] {spec.source_id}: priming write session...",
                pending_message=f"[wait] {spec.source_id}: still priming write session",
                operation=client.prime_write_session,
                stats=stats,
                bulk_status=(
                    _make_bulk_status(
                        source_label=source_label,
                        total_pages=0,
                        current_index=0,
                        current_title="",
                        phase="save-preflight",
                        detail="Priming write session and caching CSRF token",
                        stats=stats,
                    )
                    if policy.bulk_mode_active
                    else None
                ),
            )
            config = getattr(client.pywikibot, "config", None)
            ui.info(
                "[session] "
                f"{spec.source_id}: write session ready "
                f"user={client.current_user() or 'unknown'} "
                f"bot_right={'yes' if client.has_bot_right() else 'no'} "
                f"put_throttle={getattr(config, 'put_throttle', 0.0):.2f}s "
                f"min_throttle={getattr(config, 'minthrottle', 0.0):.2f}s "
                f"max_retries={getattr(config, 'max_retries', 0)} "
                f"retry_wait={getattr(config, 'retry_wait', 0)}s "
                f"retry_max={getattr(config, 'retry_max', 0)}s "
                f"maxlag={getattr(config, 'maxlag', 0)}s"
            )
        except Exception as exc:
            if is_retryable_transport_error(exc):
                stats.errors += 1
                ui.error(
                    f"[failed] {spec.source_id}: write session priming failed after retries ({exc})"
                )
                ui.warn("Skipping this source after repeated transport failure.")
                return stats
            _stop_after_error(
                ui=ui,
                policy=policy,
                stats=stats,
                error_message=f"[error] {spec.source_id}: {exc}",
                warning_message="Stopped after write-session setup failure.",
            )
            return stats

    try:
        with ui.status("Collecting candidate pages from be.wiki..."):
            total_hits, titles = _run_transport_operation(
                client=client,
                ui=ui,
                label=spec.source_id,
                operation_name="collect candidate pages",
                start_message=f"[search] {spec.source_id}: collecting candidate pages...",
                pending_message=f"[wait] {spec.source_id}: still collecting candidate pages",
                operation=lambda: client.load_titles(query, options.limit),
                stats=stats,
                bulk_status=(
                    _make_bulk_status(
                        source_label=source_label,
                        total_pages=0,
                        current_index=0,
                        current_title="",
                        phase="load",
                        detail="Collecting candidate pages",
                        stats=stats,
                    )
                    if policy.bulk_mode_active
                    else None
                ),
            )
    except Exception as exc:
        if is_retryable_transport_error(exc):
            stats.errors += 1
            ui.error(
                f"[failed] {spec.source_id}: candidate page collection failed after retries ({exc})"
            )
            ui.warn("Skipping this source after repeated transport failure.")
            return stats
        _stop_after_error(
            ui=ui,
            policy=policy,
            stats=stats,
            error_message=f"[error] {spec.source_id}: {exc}",
            warning_message="Stopped after title collection failure.",
        )
        return stats

    ui.print_state_counts(
        total_hits=total_hits,
        titles=len(titles),
        base_rules=len(state.base_rules),
        review_variants=len(state.review_variants),
        active_rules=len(state.active_rules),
        ignored_variants=len(state.ignored_hashes),
    )

    title_iter = (
        titles
        if interactive_run or options.apply
        else ui.track_titles(
            titles,
            description="Processing pages",
        )
    )

    for index, title in enumerate(title_iter, start=1):
        if policy.bulk_mode_active:
            status = _make_bulk_status(
                source_label=source_label,
                total_pages=len(titles),
                current_index=index,
                current_title=title,
                phase="queue",
                detail="Queued page for processing",
                stats=stats,
            )
            if not bulk_started:
                ui.begin_bulk_run(status)
                logger.info("bulk mode activated source=%s page=%s", source_label, title)
                bulk_started = True
            else:
                ui.update_bulk_status(status)
        ui.print_processing_page(index=index, total=len(titles), title=title)
        stats.processed += 1
        logger.info("loading page title=%s source_id=%s", title, spec.source_id)
        try:
            load_started = perf_counter()
            load_status = _make_bulk_status(
                source_label=source_label,
                total_pages=len(titles),
                current_index=index,
                current_title=title,
                phase="load",
                detail="Fetching page text from the wiki",
                stats=stats,
            )
            if policy.bulk_mode_active:
                ui.update_bulk_status(load_status)
            loaded_page = _run_transport_operation(
                client=client,
                ui=ui,
                label=title,
                operation_name="load page",
                start_message=f"[load] {title}: fetching page text...",
                pending_message=f"[wait] {title}: still fetching page text",
                operation=lambda: client.load_page(title),
                stats=stats,
                bulk_status=load_status if policy.bulk_mode_active else None,
            )
            load_elapsed = perf_counter() - load_started
            logger.info(
                "loaded page title=%s source_id=%s seconds=%.3f",
                title,
                spec.source_id,
                load_elapsed,
            )
            if load_elapsed >= 5:
                ui.warn(f"[delay] {title}: page load took {format_elapsed(load_elapsed)}")
        except Exception as exc:
            if is_retryable_transport_error(exc):
                stats.failed += 1
                stats.failed_titles.append(title)
                logger.error("page load failed after retries title=%s error=%s", title, exc)
                ui.error(f"[failed] {title}: page load failed after retries ({exc})")
                if policy.bulk_mode_active:
                    ui.update_bulk_status(
                        _make_bulk_status(
                            source_label=source_label,
                            total_pages=len(titles),
                            current_index=index,
                            current_title=title,
                            phase="failed",
                            detail=f"Page load failed after retries: {exc}",
                            stats=stats,
                        )
                    )
                continue
            _stop_after_error(
                ui=ui,
                policy=policy,
                stats=stats,
                error_message=f"[error] {title}: {exc}",
                warning_message="Stopped after page load failure.",
            )
            break

        try:
            analyze_started = perf_counter()
            analyze_status = _make_bulk_status(
                source_label=source_label,
                total_pages=len(titles),
                current_index=index,
                current_title=title,
                phase="analyze",
                detail="Applying bibliography replacement rules",
                stats=stats,
            )
            if policy.bulk_mode_active:
                ui.update_bulk_status(analyze_status)
            with monitor_operation(
                ui,
                start_message=f"[analyze] {title}: applying replacement rules...",
                pending_message=f"[wait] {title}: still applying replacement rules",
                on_heartbeat=(
                    None
                    if not policy.bulk_mode_active
                    else lambda elapsed: ui.update_bulk_status(
                        replace(
                            analyze_status,
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
                analysis = analyze_page(
                    title,
                    loaded_page.text,
                    spec=spec,
                    state=state,
                    deps=deps,
                )
            analyze_elapsed = perf_counter() - analyze_started
            logger.info(
                "analyzed page title=%s source_id=%s seconds=%.3f replacements=%s",
                title,
                spec.source_id,
                analyze_elapsed,
                analysis.result.replacements,
            )
            if analyze_elapsed >= 5:
                ui.warn(f"[delay] {title}: analysis took {format_elapsed(analyze_elapsed)}")
        except Exception as exc:
            _stop_after_error(
                ui=ui,
                policy=policy,
                stats=stats,
                error_message=f"[error] {title}: {exc}",
                warning_message="Stopped after page analysis failure.",
            )
            break

        if analysis.result.replacements == 0 and options.learn_variants:
            analysis = learn_unknown_variants(
                analysis=analysis,
                spec=spec,
                state=state,
                ui=ui,
                stats=stats,
                deps=deps,
            )

        execute_page(
            analysis=analysis,
            spec=spec,
            options=options,
            policy=policy,
            ui=ui,
            state=state,
            client=client,
            page=loaded_page.page,
            source_label=source_label,
            page_index=index,
            total_pages=len(titles),
            stats=stats,
            deps=deps,
        )
        if policy.bulk_mode_active and not bulk_started:
            bulk_started = True
        if policy.stopped:
            break

    if bulk_started:
        ui.finish_bulk_run()
    return stats


def run_sources(
    options: RunOptions,
    ui: RunUI,
    root: Path | None = None,
    *,
    deps: RunnerDependencies | None = None,
) -> int:
    actual_root = root or project_root()
    resolved_deps = deps or _build_dependencies()
    logger = get_logger()
    policy = RunPolicy(
        options=options,
        accept_all=options.assume_yes,
        bulk_mode_active=options.assume_yes,
    )
    site_clients = WikiClientPool(
        actual_root=actual_root,
        create_site=resolved_deps.create_site,
        load_titles_func=resolved_deps.load_titles,
    )
    overall = RunStats()
    set_transport_wait_reporter(ui.report_transport_wait)
    try:
        selected_specs: list[SourceSpec] = []
        for source_id in options.source_ids:
            selected_spec = resolved_deps.load_source_spec(source_id, root=actual_root)
            selected_specs.extend(selected_spec.operational_specs)

        for index, spec in enumerate(selected_specs, start=1):
            try:
                stats = _run_single_source(
                    spec,
                    options,
                    ui,
                    policy=policy,
                    site_clients=site_clients,
                    source_index=index,
                    source_total=len(selected_specs),
                    deps=resolved_deps,
                )
            except BotRightRequiredError as exc:
                ui.error(f"{spec.source_id}: {exc}")
                overall.errors += 1
                ui.print_final_summary(overall)
                return 1
            overall.processed += stats.processed
            overall.matched += stats.matched
            overall.saved += stats.saved
            overall.skipped += stats.skipped
            overall.failed += stats.failed
            overall.errors += stats.errors
            overall.learned += stats.learned
            overall.ignored += stats.ignored
            overall.retry_events += stats.retry_events
            overall.failed_titles.extend(stats.failed_titles)
            if policy.stopped:
                break
    finally:
        set_transport_wait_reporter(None)
        ui.finish_bulk_run()

    logger.info(
        "run summary processed=%s matched=%s saved=%s skipped=%s failed=%s errors=%s retries=%s failed_titles=%s",
        overall.processed,
        overall.matched,
        overall.saved,
        overall.skipped,
        overall.failed,
        overall.errors,
        overall.retry_events,
        ",".join(overall.failed_titles),
    )
    ui.print_final_summary(overall)
    return 0 if overall.errors == 0 and overall.failed == 0 else 1


def _run_transport_operation(
    *,
    client,
    ui,
    label: str,
    operation_name: str,
    start_message: str,
    pending_message: str,
    operation,
    stats: RunStats,
    bulk_status: BulkRunStatus | None = None,
):
    logger = get_logger()
    max_attempts = 4

    for attempt in range(1, max_attempts + 1):
        started = perf_counter()
        try:
            with monitor_operation(
                ui,
                start_message=start_message,
                pending_message=pending_message,
                on_heartbeat=(
                    None
                    if bulk_status is None
                    else lambda elapsed: ui.update_bulk_status(
                        replace(
                            bulk_status,
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
                return operation()
        except Exception as exc:
            elapsed = perf_counter() - started
            if is_retryable_transport_error(exc) and attempt < max_attempts:
                delay = transport_retry_delay(attempt)
                stats.retry_events += 1
                logger.warning(
                    "transport retry label=%s operation=%s seconds=%.3f attempt=%s delay=%.3f error=%s",
                    label,
                    operation_name,
                    elapsed,
                    attempt,
                    delay,
                    exc,
                )
                ui.warn(
                    f"[retry] {label}: {operation_name} failed ({exc}). Reconnecting and retrying in {format_elapsed(delay)} "
                    f"[attempt {attempt}/{max_attempts - 1}]"
                )
                try:
                    client.reconnect()
                except Exception as reconnect_exc:
                    logger.warning(
                        "transport reconnect failed label=%s operation=%s attempt=%s error=%s",
                        label,
                        operation_name,
                        attempt,
                        reconnect_exc,
                    )
                    ui.warn(f"[retry] {label}: reconnect failed ({reconnect_exc})")
                if bulk_status is not None:
                    ui.update_bulk_status(
                        replace(
                            bulk_status,
                            phase="retry",
                            detail=f"Retrying {operation_name} in {format_elapsed(delay)}",
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
            raise


def _make_bulk_status(
    *,
    source_label: str,
    total_pages: int,
    current_index: int,
    current_title: str,
    phase: str,
    detail: str,
    stats: RunStats,
    phase_elapsed: float = 0.0,
) -> BulkRunStatus:
    return BulkRunStatus(
        source_label=source_label,
        total_pages=total_pages,
        current_index=current_index,
        current_title=current_title,
        phase=phase,
        detail=detail,
        phase_elapsed=phase_elapsed,
        processed=stats.processed,
        matched=stats.matched,
        saved=stats.saved,
        skipped=stats.skipped,
        failed=stats.failed,
        retries=stats.retry_events,
    )
