from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from bewiki_biblio.bootstrap import create_site
from bewiki_biblio.engine import (
    debug_candidate_lines,
    extract_unknown_variant_infos,
    replace_text,
    variant_review_hash,
    variant_review_key,
)
from bewiki_biblio.models import RunOptions, RunStats
from bewiki_biblio.query import build_search_query
from bewiki_biblio.specs import load_source_spec, project_root
from bewiki_biblio.state import load_source_state
from bewiki_biblio.ui import AppUI


def list_sources(ui: AppUI) -> int:
    from bewiki_biblio.specs import discover_source_specs

    specs = discover_source_specs()
    ui.print_sources(specs)
    return 0


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


def _needs_interactive_input(options: RunOptions) -> bool:
    return options.learn_variants or (options.apply and not options.assume_yes)


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


def _is_minor_edit(old_text: str, new_text: str) -> bool:
    return _changed_bytes(old_text, new_text) < 1000


@dataclass
class RunSession:
    accept_all: bool
    summary_override: str | None = None
    stopped: bool = False


def _get_site_bundle(spec, actual_root: Path, site_cache: dict[tuple[str, str], tuple[object, object]]):
    key = (spec.site_lang, spec.family)
    bundle = site_cache.get(key)
    if bundle is None:
        pywikibot_dir = actual_root / ".pywikibot"
        bundle = create_site(spec, pywikibot_dir)
        site_cache[key] = bundle
    return bundle


def _run_single_source(
    spec,
    options: RunOptions,
    ui: AppUI,
    *,
    actual_root: Path,
    session: RunSession,
    site_cache: dict[tuple[str, str], tuple[object, object]],
    source_index: int,
    source_total: int,
) -> RunStats:
    state = load_source_state(spec)
    query = options.query or build_search_query(spec)
    current_summary = session.summary_override or options.summary or spec.render_default_summary()
    stats = RunStats()
    interactive_run = _needs_interactive_input(options)

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
        assume_yes=session.accept_all,
        learn_variants=options.learn_variants,
        show_candidates=options.show_candidates,
    )

    pywikibot, site = _get_site_bundle(spec, actual_root, site_cache)

    with ui.status("Collecting candidate pages from be.wiki..."):
        total_hits, titles = _load_titles(site, query, options.limit)

    ui.print_state_counts(
        total_hits=total_hits,
        titles=len(titles),
        base_rules=len(state.base_rules),
        review_variants=len(state.review_variants),
        active_rules=len(state.active_rules),
        ignored_variants=len(state.ignored_hashes),
    )

    title_iter = titles if interactive_run else ui.track_titles(
        titles,
        description="Processing pages",
    )

    for index, title in enumerate(title_iter, start=1):
        if interactive_run:
            ui.print_processing_page(index=index, total=len(titles), title=title)
        page = pywikibot.Page(site, title)
        stats.processed += 1
        old_text = page.text
        result = replace_text(old_text, spec, state.active_rules)

        if result.replacements == 0 and options.learn_variants:
            infos = extract_unknown_variant_infos(old_text, spec)
            for info in infos:
                key = variant_review_key(info)
                hashed = variant_review_hash(info)

                if key in state.review_keys:
                    ui.info(f"[review-known] {title}: variant is already in review_variants.json")
                    continue
                if hashed in state.ignored_hashes:
                    ui.info(f"[ignored-known] {title}: variant is already ignored")
                    continue

                ui.print_unknown_variant(title, info, spec)
                choice = ui.prompt_variant_action()
                if choice == "r":
                    if state.add_review_variant(info.review_line):
                        stats.learned += 1
                        ui.info("[review] Added candidate to review_variants.json")
                    break
                if choice == "i":
                    if state.add_ignored_hash(hashed):
                        stats.ignored += 1
                        ui.info("[ignore] Added candidate to ignored_variants.json")
                    break

            result = replace_text(old_text, spec, state.active_rules)

        if result.replacements == 0:
            if options.show_candidates:
                ui.print_candidate_lines(title, debug_candidate_lines(old_text, spec))
            ui.info(f"[skip] {title}: no replacements found")
            stats.skipped += 1
            continue

        stats.matched += 1
        ui.print_diff_panel(
            title=title,
            result=result,
            old_text=old_text,
            context=options.context,
        )
        for rule in result.used_line_rules:
            ui.print_used_rule(rule)

        if not options.apply:
            ui.info("[dry-run] No changes saved")
            continue

        if not session.accept_all:
            while True:
                choice = ui.prompt_page_action(current_summary)
                if choice != "e":
                    break
                current_summary = ui.prompt_summary(current_summary)
                session.summary_override = current_summary

            if choice == "q":
                ui.warn("Stopped by user.")
                session.stopped = True
                break
            if choice == "n":
                ui.info(f"[skip] {title}: not saved")
                stats.skipped += 1
                continue
            if choice == "a":
                session.accept_all = True

        try:
            page.text = result.text
            page.save(
                summary=current_summary,
                minor=_is_minor_edit(old_text, result.text),
                bot=True,
                asynchronous=False,
            )
            stats.saved += 1

            promoted = False
            for rule in result.used_line_rules:
                if state.ensure_rule_saved(rule):
                    promoted = True
            if promoted:
                ui.info("[rules] Promoted new review rules into rules.json")
        except Exception as exc:
            stats.errors += 1
            ui.error(f"[error] {title}: {exc}")

    return stats


def run_sources(options: RunOptions, ui: AppUI, root: Path | None = None) -> int:
    actual_root = root or project_root()
    session = RunSession(accept_all=options.assume_yes, summary_override=options.summary)
    site_cache: dict[tuple[str, str], tuple[object, object]] = {}
    overall = RunStats()

    for index, source_id in enumerate(options.source_ids, start=1):
        spec = load_source_spec(source_id, root=actual_root)
        stats = _run_single_source(
            spec,
            options,
            ui,
            actual_root=actual_root,
            session=session,
            site_cache=site_cache,
            source_index=index,
            source_total=len(options.source_ids),
        )
        overall.processed += stats.processed
        overall.matched += stats.matched
        overall.saved += stats.saved
        overall.skipped += stats.skipped
        overall.errors += stats.errors
        overall.learned += stats.learned
        overall.ignored += stats.ignored
        if session.stopped:
            break

    ui.print_final_summary(overall)
    return 0 if overall.errors == 0 else 1


def run_source(options: RunOptions, ui: AppUI, root: Path | None = None) -> int:
    return run_sources(options, ui, root=root)
