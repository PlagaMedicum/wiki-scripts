from __future__ import annotations

from pathlib import Path

from biblio.bootstrap import create_site
from biblio.engine import (
    debug_candidate_lines,
    extract_unknown_variant_infos,
    replace_text,
    variant_review_hash,
    variant_review_key,
)
from biblio.models import RunOptions
from biblio.query import build_search_query
from biblio.runtime import RunnerDependencies
from biblio.session import needs_interactive_input as _needs_interactive_input
from biblio.specs import discover_source_specs, load_source_spec, project_root
from biblio.state import load_source_state, variant_hash
from biblio.text import entry_matches_page_title, make_review_key
from biblio.page_execution import _changed_bytes, _is_minor_edit
from biblio.workflow import run_source as _run_source
from biblio.workflow import run_sources as _run_sources


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


def _build_runner_dependencies() -> RunnerDependencies:
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


def list_sources(ui) -> int:
    specs = discover_source_specs()
    ui.print_sources(specs)
    return 0


def run_sources(options: RunOptions, ui, root: Path | None = None) -> int:
    actual_root = root or project_root()
    return _run_sources(
        options,
        ui,
        root=actual_root,
        deps=_build_runner_dependencies(),
    )


def run_source(options: RunOptions, ui, root: Path | None = None) -> int:
    actual_root = root or project_root()
    return _run_source(
        options,
        ui,
        root=actual_root,
        deps=_build_runner_dependencies(),
    )
