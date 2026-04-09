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
from biblio.page_save import PageSavePlan, apply_page_save, plan_page_save
from biblio.runtime import PageEdit
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


def _options(**kwargs) -> RunOptions:
    defaults = dict(
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
    )
    defaults.update(kwargs)
    return RunOptions(**defaults)


def _analysis(*, review_required: bool = False) -> PageAnalysis:
    return PageAnalysis(
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
            review_reasons=["Heuristic entry match."] if review_required else [],
        ),
        review_required=review_required,
        manual_review_lines=(),
    )


class FakeUI:
    def __init__(self, actions: list[str] | None = None, summary: str = "Edited summary") -> None:
        self.actions = iter(actions or ["a"])
        self.summary = summary
        self.info_messages: list[str] = []
        self.warn_messages: list[str] = []
        self.error_messages: list[str] = []

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str:
        return next(self.actions)

    def prompt_summary(self, current_summary: str) -> str:
        return self.summary

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warn(self, message: str) -> None:
        self.warn_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


@dataclass
class FakeState:
    saved_rules: list[dict]

    def ensure_rule_saved(self, rule: dict) -> bool:
        self.saved_rules.append(rule)
        return True


class FakePage:
    pass


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, PageEdit]] = []

    def save_page(self, page, edit: PageEdit) -> None:
        self.calls.append((page, edit))


def test_plan_page_save_applies_summary_override_and_accept_all(tmp_path):
    spec = _spec(tmp_path)
    ui = FakeUI(actions=["e", "a"], summary="Edited summary")
    policy = RunPolicy(options=_options(), accept_all=False)
    stats = RunStats()

    plan = plan_page_save(
        analysis=_analysis(),
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        stats=stats,
    )

    assert plan == PageSavePlan(
        title="Demo page",
        edit=PageEdit(text="axc", summary="Edited summary", minor=True),
        used_line_rules=({"kind": "line_exact", "replacement": "axc"},),
    )
    assert policy.summary_override == "Edited summary"
    assert policy.accept_all


def test_plan_page_save_respects_skip_review_required(tmp_path):
    spec = _spec(tmp_path)
    ui = FakeUI()
    policy = RunPolicy(
        options=_options(skip_review_required=True, assume_yes=True),
        accept_all=True,
    )
    stats = RunStats()

    plan = plan_page_save(
        analysis=_analysis(review_required=True),
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        stats=stats,
    )

    assert plan is None
    assert stats.skipped == 1
    assert ui.warn_messages == ["[review-skip] Heuristic entry match."]


def test_apply_page_save_uses_client_transport_and_promotes_rules():
    state = FakeState(saved_rules=[])
    ui = FakeUI()
    stats = RunStats()
    page = FakePage()
    client = FakeClient()
    plan = PageSavePlan(
        title="Demo page",
        edit=PageEdit(text="axc", summary="Edited summary", minor=True),
        used_line_rules=({"kind": "line_exact", "replacement": "axc"},),
    )

    apply_page_save(
        plan=plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )

    assert client.calls == [(page, PageEdit(text="axc", summary="Edited summary", minor=True))]
    assert state.saved_rules == [{"kind": "line_exact", "replacement": "axc"}]
    assert stats.saved == 1
    assert ui.info_messages == ["[rules] Promoted new review rules into rules.json"]
