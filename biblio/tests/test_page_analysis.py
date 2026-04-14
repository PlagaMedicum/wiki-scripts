from __future__ import annotations

from types import SimpleNamespace

from biblio.models import (
    CandidateSpec,
    NormalizationOptions,
    ReplacementResult,
    SourceSpec,
    VariantInfo,
)
from biblio.page_analysis import analyze_page, learn_unknown_variants
from biblio.runtime import RunnerDependencies


class FakeState:
    def __init__(self) -> None:
        self.active_rules = []
        self.review_variants: list[str] = []
        self.ignored_hashes: set[str] = set()

    @property
    def review_keys(self) -> set[str]:
        return set(self.review_variants)

    def add_review_variant(self, review_line: str) -> bool:
        if review_line in self.review_variants:
            return False
        self.review_variants.append(review_line)
        return True

    def add_ignored_hash(self, hashed: str) -> bool:
        if hashed in self.ignored_hashes:
            return False
        self.ignored_hashes.add(hashed)
        return True


class FakeUI:
    def __init__(self, action: str) -> None:
        self.action = action
        self.messages: list[str] = []

    def print_unknown_variant(self, title: str, info, spec) -> None:
        self.messages.append(f"show:{title}:{info.review_line}")

    def prompt_variant_action(self) -> str:
        return self.action

    def info(self, message: str) -> None:
        self.messages.append(message)


def _spec(tmp_path) -> SourceSpec:
    return SourceSpec(
        source_dir=tmp_path / "sources" / "demo",
        source_id="demo",
        name="Demo",
        site_lang="be",
        family="wikipedia",
        insource_terms=("term",),
        isbns=(),
        keywords=(),
        candidate=CandidateSpec(must_contain_all=("term",), must_contain_any=()),
        template_name="Крыніцы/Тэст",
        template_without_pages="{{Крыніцы/Тэст}}",
        template_with_pages="{{Крыніцы/Тэст||{pages}}}",
        default_summary_format="Замена {{Крыніцы/Тэст}}",
        page_patterns=(),
        reject_patterns=(),
        regex_rules=(),
        alias_rules=(),
        normalization=NormalizationOptions(),
    )


def _deps(
    *, replace_results: list[ReplacementResult], infos: list[VariantInfo] | None = None
) -> RunnerDependencies:
    remaining = iter(replace_results)
    return RunnerDependencies(
        load_source_spec=lambda *args, **kwargs: None,
        load_source_state=lambda *args, **kwargs: None,
        create_site=lambda *args, **kwargs: (None, None),
        load_titles=lambda *args, **kwargs: (0, []),
        build_search_query=lambda spec: "",
        replace_text=lambda *args, **kwargs: next(remaining),
        extract_unknown_variant_infos=lambda *args, **kwargs: infos or [],
        debug_candidate_lines=lambda *args, **kwargs: [],
        variant_review_key=lambda info: info.review_line,
        variant_review_hash=lambda info: f"hash::{info.review_line}",
        variant_hash=lambda key: f"hash::{key}",
        make_review_key=lambda line, spec: line,
        entry_matches_page_title=lambda entry, title: entry == title,
    )


def test_analyze_page_keeps_manual_review_candidates_for_matched_pages(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState()
    deps = _deps(
        replace_results=[
            ReplacementResult(
                text="{{Крыніцы/Тэст|Mismatch}}",
                replacements=1,
                used_line_rules=[],
                used_rule_names=["entry_only"],
                rendered_templates=["{{Крыніцы/Тэст|Mismatch}}"],
                page_arguments=[],
                entry_arguments=["Mismatch"],
                review_reasons=["Heuristic entry match."],
                matched_review_lines=["Mismatch // Demo encyclopedia"],
            )
        ]
    )

    analysis = analyze_page("Page Title", "Old text", spec=spec, state=state, deps=deps)

    assert analysis.review_required is True
    assert analysis.manual_review_lines == ("Mismatch // Demo encyclopedia",)
    assert any(
        "Entry differs from page title" in reason for reason in analysis.result.review_reasons
    )


def test_learn_unknown_variants_reanalyzes_after_review_choice(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState()
    ui = FakeUI(action="r")
    stats = SimpleNamespace(learned=0, ignored=0)
    deps = _deps(
        replace_results=[
            ReplacementResult(
                text="Old text",
                replacements=0,
                used_line_rules=[],
                page_arguments=[],
                entry_arguments=[],
            ),
            ReplacementResult(
                text="{{Крыніцы/Тэст}}",
                replacements=1,
                used_line_rules=[],
                used_rule_names=["line_exact"],
                rendered_templates=["{{Крыніцы/Тэст}}"],
                page_arguments=[],
                entry_arguments=[],
            ),
        ],
        infos=[
            VariantInfo(
                full_line="Old text",
                review_line="Old text",
                normalized_line="Old text",
            )
        ],
    )

    initial = analyze_page("Demo", "Old text", spec=spec, state=state, deps=deps)
    updated = learn_unknown_variants(
        analysis=initial,
        spec=spec,
        state=state,
        ui=ui,
        stats=stats,
        deps=deps,
    )

    assert state.review_variants == ["Old text"]
    assert stats.learned == 1
    assert updated.has_changes
