from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Protocol

from biblio.bootstrap import BotRightRequiredError, create_site
from biblio.engine import (
    debug_candidate_lines,
    extract_unknown_variant_infos,
    replace_text,
    variant_review_hash,
    variant_review_key,
)
from biblio.models import RunOptions, RunStats, SourceSpec
from biblio.observability import format_elapsed, get_logger
from biblio.page_analysis import analyze_page, learn_unknown_variants
from biblio.page_execution import execute_page
from biblio.query import build_search_query
from biblio.runtime import RunnerDependencies, WikiClientPool
from biblio.session import RunPolicy, needs_interactive_input
from biblio.specs import discover_source_specs, load_source_spec, project_root
from biblio.state import load_source_state, variant_hash
from biblio.text import entry_matches_page_title, make_review_key


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
        source_label=f"{spec.source_id} ({spec.name}) [{source_index}/{source_total}]",
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

    try:
        with ui.status("Collecting candidate pages from be.wiki..."):
            total_hits, titles = client.load_titles(query, options.limit)
    except Exception as exc:
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
        if interactive_run
        else ui.track_titles(
            titles,
            description="Processing pages",
        )
    )

    for index, title in enumerate(title_iter, start=1):
        ui.print_processing_page(index=index, total=len(titles), title=title)
        page = client.page(title)
        stats.processed += 1
        load_started = perf_counter()
        logger.info("loading page title=%s source_id=%s", title, spec.source_id)
        try:
            analysis = analyze_page(
                title,
                page.text,
                spec=spec,
                state=state,
                deps=deps,
            )
        except Exception as exc:
            _stop_after_error(
                ui=ui,
                policy=policy,
                stats=stats,
                error_message=f"[error] {title}: {exc}",
                warning_message="Stopped after page load failure.",
            )
            break
        load_elapsed = perf_counter() - load_started
        logger.info(
            "loaded page title=%s source_id=%s seconds=%.3f replacements=%s",
            title,
            spec.source_id,
            load_elapsed,
            analysis.result.replacements,
        )
        if load_elapsed >= 5:
            ui.warn(f"[delay] {title}: page load took {format_elapsed(load_elapsed)}")

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
            page=page,
            stats=stats,
            deps=deps,
        )
        if policy.stopped:
            break

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
    policy = RunPolicy(options=options, accept_all=options.assume_yes)
    site_clients = WikiClientPool(
        actual_root=actual_root,
        create_site=resolved_deps.create_site,
        load_titles_func=resolved_deps.load_titles,
    )
    overall = RunStats()
    for index, source_id in enumerate(options.source_ids, start=1):
        spec = resolved_deps.load_source_spec(source_id, root=actual_root)
        try:
            stats = _run_single_source(
                spec,
                options,
                ui,
                policy=policy,
                site_clients=site_clients,
                source_index=index,
                source_total=len(options.source_ids),
                deps=resolved_deps,
            )
        except BotRightRequiredError as exc:
            ui.error(f"{source_id}: {exc}")
            overall.errors += 1
            ui.print_final_summary(overall)
            return 1
        overall.processed += stats.processed
        overall.matched += stats.matched
        overall.saved += stats.saved
        overall.skipped += stats.skipped
        overall.errors += stats.errors
        overall.learned += stats.learned
        overall.ignored += stats.ignored
        if policy.stopped:
            break

    ui.print_final_summary(overall)
    return 0 if overall.errors == 0 else 1
