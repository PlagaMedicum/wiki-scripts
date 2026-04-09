from __future__ import annotations

from dataclasses import dataclass

from biblio.models import (
    CandidateSpec,
    NormalizationOptions,
    ReplacementResult,
    RunOptions,
    RunStats,
    SourceSpec,
)
from biblio.page_analysis import PageAnalysis
from biblio.page_execution import _changed_bytes, _is_minor_edit, execute_page
from biblio.runtime import PageEdit, RunnerDependencies
from biblio.session import RunPolicy


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
        default_summary_format="Замена {{{template_name}}}",
        page_patterns=(),
        reject_patterns=(),
        regex_rules=(),
        alias_rules=(),
        normalization=NormalizationOptions(),
    )


@dataclass
class FakeState:
    active_rules: list[dict]
    review_variants: list[str] = None
    ignored_hashes: set[str] = None

    def __post_init__(self) -> None:
        self.review_variants = self.review_variants or []
        self.ignored_hashes = self.ignored_hashes or set()
        self.saved_rules: list[dict] = []

    @property
    def review_keys(self) -> set[str]:
        return set(self.review_variants)

    def add_review_variant(self, review_line: str) -> bool:
        if review_line in self.review_variants:
            return False
        self.review_variants.append(review_line)
        return True

    def add_ignored_hash(self, value: str) -> bool:
        if value in self.ignored_hashes:
            return False
        self.ignored_hashes.add(value)
        return True

    def ensure_rule_saved(self, rule: dict) -> bool:
        self.saved_rules.append(rule)
        return True


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.saved_kwargs = None
        self.saved_edits: list[PageEdit] = []

    def save(self, **kwargs) -> None:
        self.saved_kwargs = kwargs


class FakeClient:
    def save_page(self, page: FakePage, edit: PageEdit) -> None:
        page.text = edit.text
        page.saved_edits.append(edit)
        page.save(
            summary=edit.summary,
            minor=edit.minor,
            bot=True,
            asynchronous=False,
        )


class FakeUI:
    def __init__(self, page_action: str = "a", summary: str = "Edited summary") -> None:
        self.page_action = page_action
        self.summary = summary
        self.diff_calls: list[tuple[str, str]] = []
        self.used_rules: list[dict] = []
        self.candidate_lines: list[tuple[str, list[str]]] = []
        self.info_messages: list[str] = []
        self.warn_messages: list[str] = []
        self.error_messages: list[str] = []

    def print_diff_panel(self, *, title: str, result, old_text: str, context: int) -> None:
        self.diff_calls.append((title, result.text))

    def print_used_rule(self, rule: dict) -> None:
        self.used_rules.append(rule)

    def print_candidate_lines(self, title: str, lines: list[str]) -> None:
        self.candidate_lines.append((title, lines))

    def prompt_review_match_action(self) -> str:
        return "r"

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str:
        return self.page_action

    def prompt_summary(self, current_summary: str) -> str:
        return self.summary

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warn(self, message: str) -> None:
        self.warn_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


def _deps() -> RunnerDependencies:
    return RunnerDependencies(
        load_source_spec=lambda *args, **kwargs: None,
        load_source_state=lambda *args, **kwargs: None,
        create_site=lambda *args, **kwargs: (None, None),
        load_titles=lambda *args, **kwargs: (0, []),
        build_search_query=lambda spec: "",
        replace_text=lambda *args, **kwargs: None,
        extract_unknown_variant_infos=lambda *args, **kwargs: [],
        debug_candidate_lines=lambda *args, **kwargs: ["candidate"],
        variant_review_key=lambda info: "",
        variant_review_hash=lambda info: "",
        variant_hash=lambda value: value,
        make_review_key=lambda line, spec: line,
        entry_matches_page_title=lambda entry, title: entry == title,
    )


def test_changed_bytes_and_minor_edit_threshold():
    assert _changed_bytes("abc", "adc") == 2
    assert _is_minor_edit("a" * 400, "b" * 400, 1000)
    assert not _is_minor_edit("a" * 500, "b" * 500, 1000)


def test_execute_page_saves_and_promotes_rules(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(page_action="a", summary="Custom summary")
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=True,
            assume_yes=True,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=False,
            show_candidates=False,
        ),
        accept_all=True,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[{"kind": "line_exact", "replacement": "axc"}],
            used_rule_names=["line_exact"],
            rendered_templates=[],
            page_arguments=[],
            entry_arguments=[],
        ),
        review_required=False,
        manual_review_lines=(),
    )

    execute_page(
        analysis=analysis,
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        state=state,
        client=FakeClient(),
        page=page,
        stats=stats,
        deps=_deps(),
    )

    assert stats.saved == 1
    assert page.saved_edits == [
        PageEdit(
            text="axc",
            summary="Замена {{Крыніцы/Тэст}}",
            minor=True,
        )
    ]
    assert page.saved_kwargs == {
        "summary": "Замена {{Крыніцы/Тэст}}",
        "minor": True,
        "bot": True,
        "asynchronous": False,
    }
    assert state.saved_rules == [{"kind": "line_exact", "replacement": "axc"}]
    assert ui.info_messages == ["[rules] Promoted new review rules into rules.json"]


def test_execute_page_respects_skip_review_required(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI()
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=True,
            assume_yes=True,
            skip_review_required=True,
            summary=None,
            context=3,
            learn_variants=False,
            show_candidates=False,
        ),
        accept_all=True,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=[],
            rendered_templates=[],
            page_arguments=[],
            entry_arguments=[],
            review_reasons=["Heuristic entry match."],
        ),
        review_required=True,
        manual_review_lines=(),
    )

    execute_page(
        analysis=analysis,
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        state=state,
        client=FakeClient(),
        page=page,
        stats=stats,
        deps=_deps(),
    )

    assert stats.skipped == 1
    assert page.saved_edits == []
    assert page.saved_kwargs is None
    assert ui.warn_messages == ["[review-skip] Heuristic entry match."]


def test_execute_page_carries_summary_override_forward_across_pages(tmp_path, monkeypatch):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    client = FakeClient()
    stats = RunStats()
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=True,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=False,
            show_candidates=False,
        ),
        accept_all=False,
    )
    actions = iter(["e", "a"])
    ui = FakeUI(page_action="a", summary="Edited summary")
    monkeypatch.setattr(ui, "prompt_page_action", lambda current_summary, *, review_required=False: next(actions))
    monkeypatch.setattr(ui, "prompt_summary", lambda current_summary: "Edited summary")

    first_page = FakePage("abc")
    second_page = FakePage("abc")
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=[],
            rendered_templates=[],
            page_arguments=[],
            entry_arguments=[],
        ),
        review_required=False,
        manual_review_lines=(),
    )

    execute_page(
        analysis=analysis,
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        state=state,
        client=client,
        page=first_page,
        stats=stats,
        deps=_deps(),
    )
    execute_page(
        analysis=analysis,
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        state=state,
        client=client,
        page=second_page,
        stats=stats,
        deps=_deps(),
    )

    assert policy.summary_override == "Edited summary"
    assert first_page.saved_edits == [
        PageEdit(text="axc", summary="Edited summary", minor=True)
    ]
    assert second_page.saved_edits == [
        PageEdit(text="axc", summary="Edited summary", minor=True)
    ]
