from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from biblio.models import ReplacementResult, SourceSpec, VariantInfo


@dataclass(frozen=True)
class PageEdit:
    text: str
    summary: str
    minor: bool


@dataclass(frozen=True)
class WikiClient:
    pywikibot: object
    site: object
    load_titles_func: Callable[[object, str, int], tuple[int, list[str]]]

    def page(self, title: str):
        return self.pywikibot.Page(self.site, title)

    def load_titles(self, query: str, limit: int) -> tuple[int, list[str]]:
        return self.load_titles_func(self.site, query, limit)

    def save_page(self, page, edit: PageEdit) -> None:
        page.text = edit.text
        page.save(
            summary=edit.summary,
            minor=edit.minor,
            bot=True,
            asynchronous=False,
        )


@dataclass
class WikiClientPool:
    actual_root: Path
    create_site: Callable[[SourceSpec, Path], tuple[object, object]]
    load_titles_func: Callable[[object, str, int], tuple[int, list[str]]]
    _clients: dict[tuple[str, str], WikiClient] = field(default_factory=dict, repr=False)

    def get(self, spec: SourceSpec) -> WikiClient:
        key = (spec.site_lang, spec.family)
        client = self._clients.get(key)
        if client is None:
            pywikibot_dir = self.actual_root / ".pywikibot"
            pywikibot, site = self.create_site(spec, pywikibot_dir)
            client = WikiClient(
                pywikibot=pywikibot,
                site=site,
                load_titles_func=self.load_titles_func,
            )
            self._clients[key] = client
        return client


@dataclass(frozen=True)
class RunnerDependencies:
    load_source_spec: Callable[[str, Path | None], SourceSpec]
    load_source_state: Callable[[SourceSpec], object]
    create_site: Callable[[SourceSpec, Path], tuple[object, object]]
    load_titles: Callable[[object, str, int], tuple[int, list[str]]]
    build_search_query: Callable[[SourceSpec], str]
    replace_text: Callable[..., ReplacementResult]
    extract_unknown_variant_infos: Callable[..., list[VariantInfo]]
    debug_candidate_lines: Callable[..., list[str]]
    variant_review_key: Callable[[VariantInfo], str]
    variant_review_hash: Callable[[VariantInfo], str]
    variant_hash: Callable[[str], str]
    make_review_key: Callable[[str, SourceSpec], str]
    entry_matches_page_title: Callable[[str, str], bool]


def load_search_titles(site, query: str, limit: int) -> tuple[int, list[str]]:
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


def build_runner_dependencies(
    *,
    load_source_spec: Callable[[str, Path | None], SourceSpec],
    load_source_state: Callable[[SourceSpec], object],
    create_site: Callable[[SourceSpec, Path], tuple[object, object]],
    load_titles: Callable[[object, str, int], tuple[int, list[str]]],
    build_search_query: Callable[[SourceSpec], str],
    replace_text: Callable[..., ReplacementResult],
    extract_unknown_variant_infos: Callable[..., list[VariantInfo]],
    debug_candidate_lines: Callable[..., list[str]],
    variant_review_key: Callable[[VariantInfo], str],
    variant_review_hash: Callable[[VariantInfo], str],
    variant_hash: Callable[[str], str],
    make_review_key: Callable[[str, SourceSpec], str],
    entry_matches_page_title: Callable[[str, str], bool],
) -> RunnerDependencies:
    return RunnerDependencies(
        load_source_spec=load_source_spec,
        load_source_state=load_source_state,
        create_site=create_site,
        load_titles=load_titles,
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
