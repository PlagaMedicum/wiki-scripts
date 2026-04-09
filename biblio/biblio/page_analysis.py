from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from biblio.models import ReplacementResult, RunStats, SourceSpec
from biblio.runtime import RunnerDependencies


class VariantLearningUI(Protocol):
    def print_unknown_variant(self, title: str, info, spec: SourceSpec) -> None: ...

    def prompt_variant_action(self) -> str: ...

    def info(self, message: str) -> None: ...


@dataclass(frozen=True)
class PageAnalysis:
    title: str
    old_text: str
    result: ReplacementResult
    review_required: bool
    manual_review_lines: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        return self.result.replacements > 0


def _append_title_review_reasons(
    result: ReplacementResult,
    title: str,
    *,
    entry_matches_page_title_fn,
) -> None:
    if not result.review_reasons:
        return
    seen = set(result.review_reasons)
    for entry in result.entry_arguments:
        if entry_matches_page_title_fn(entry, title):
            continue
        reason = f'Entry differs from page title: "{entry}" vs "{title}".'
        if reason not in seen:
            result.review_reasons.append(reason)
            seen.add(reason)


def _manual_review_candidates(
    result: ReplacementResult,
    spec: SourceSpec,
    state,
    *,
    variant_hash_fn,
    make_review_key_fn,
) -> tuple[str, ...]:
    lines: list[str] = []
    seen_keys: set[str] = set()
    review_keys = getattr(state, "review_keys", set())
    ignored_hashes = getattr(state, "ignored_hashes", set())
    for line in result.matched_review_lines:
        if not line.strip():
            continue
        key = make_review_key_fn(line, spec)
        hashed = variant_hash_fn(key)
        if key in review_keys or hashed in ignored_hashes or key in seen_keys:
            continue
        seen_keys.add(key)
        lines.append(line)
    return tuple(lines)


def analyze_page(
    title: str,
    old_text: str,
    *,
    spec: SourceSpec,
    state,
    deps: RunnerDependencies,
) -> PageAnalysis:
    result = deps.replace_text(
        old_text,
        spec,
        state.active_rules,
        page_title=title,
    )
    _append_title_review_reasons(
        result,
        title,
        entry_matches_page_title_fn=deps.entry_matches_page_title,
    )
    return PageAnalysis(
        title=title,
        old_text=old_text,
        result=result,
        review_required=bool(result.review_reasons),
        manual_review_lines=_manual_review_candidates(
            result,
            spec,
            state,
            variant_hash_fn=deps.variant_hash,
            make_review_key_fn=deps.make_review_key,
        ),
    )


def candidate_debug_lines(
    analysis: PageAnalysis,
    spec: SourceSpec,
    *,
    deps: RunnerDependencies,
) -> list[str]:
    return deps.debug_candidate_lines(analysis.old_text, spec)


def learn_unknown_variants(
    *,
    analysis: PageAnalysis,
    spec: SourceSpec,
    state,
    ui: VariantLearningUI,
    stats: RunStats,
    deps: RunnerDependencies,
) -> PageAnalysis:
    if analysis.has_changes:
        return analysis

    review_keys = getattr(state, "review_keys", set())
    ignored_hashes = getattr(state, "ignored_hashes", set())
    infos = deps.extract_unknown_variant_infos(
        analysis.old_text,
        spec,
        page_title=analysis.title,
    )
    for info in infos:
        key = deps.variant_review_key(info)
        hashed = deps.variant_review_hash(info)

        if key in review_keys:
            ui.info(f"[review-known] {analysis.title}: variant is already in review_variants.json")
            continue
        if hashed in ignored_hashes:
            ui.info(f"[ignored-known] {analysis.title}: variant is already ignored")
            continue

        ui.print_unknown_variant(analysis.title, info, spec)
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

    return analyze_page(
        analysis.title,
        analysis.old_text,
        spec=spec,
        state=state,
        deps=deps,
    )
