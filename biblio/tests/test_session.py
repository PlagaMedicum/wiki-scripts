from __future__ import annotations

from biblio.models import CandidateSpec, NormalizationOptions, RunOptions, SourceSpec
from biblio.session import RunPolicy, needs_interactive_input, prompt_page_decision


class FakePromptUI:
    def __init__(self, actions: list[str], summaries: list[str] | None = None) -> None:
        self._actions = iter(actions)
        self._summaries = iter(summaries or [])

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str:
        return next(self._actions)

    def prompt_summary(self, current_summary: str) -> str:
        return next(self._summaries)


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


def _options(**kwargs) -> RunOptions:
    defaults = dict(
        source_ids=("demo",),
        query=None,
        limit=1,
        minor_threshold=1000,
        apply=False,
        assume_yes=False,
        skip_review_required=False,
        summary=None,
        context=3,
        learn_variants=False,
        show_candidates=False,
    )
    defaults.update(kwargs)
    return RunOptions(**defaults)


def test_prompt_page_decision_tracks_summary_override():
    ui = FakePromptUI(actions=["e", "a"], summaries=["Edited summary"])

    decision = prompt_page_decision(
        ui,
        "Initial summary",
        review_required=False,
    )

    assert decision.choice == "a"
    assert decision.summary_override == "Edited summary"


def test_run_policy_prompts_review_required_pages_even_after_accept_all(tmp_path):
    spec = _spec(tmp_path)
    policy = RunPolicy(options=_options(apply=True), accept_all=True)

    assert policy.current_summary(spec) == "Замена {{Крыніцы/Тэст}}"
    assert not policy.should_prompt_page(review_required=False)
    assert policy.should_prompt_page(review_required=True)


def test_run_policy_accept_all_turns_on_bulk_mode(tmp_path):
    policy = RunPolicy(options=_options(apply=True), accept_all=False, bulk_mode_active=False)

    policy.apply_page_decision(
        prompt_page_decision(FakePromptUI(actions=["a"]), "Summary", review_required=False)
    )

    assert policy.accept_all is True
    assert policy.bulk_mode_active is True
    assert policy.is_bulk_mode() is True


def test_needs_interactive_input_respects_skip_review_required():
    assert needs_interactive_input(
        _options(apply=True, assume_yes=True, skip_review_required=False),
        accept_all=True,
        has_review_required_rules=True,
    )
    assert not needs_interactive_input(
        _options(apply=True, assume_yes=True, skip_review_required=True),
        accept_all=True,
        has_review_required_rules=True,
    )
