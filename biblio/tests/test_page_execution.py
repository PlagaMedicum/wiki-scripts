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
        self.exact_rules: list[tuple[str, str]] = []

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

    def add_exact_rule(self, review_line: str, replacement: str) -> bool:
        rule = (review_line, replacement)
        if rule in self.exact_rules:
            return False
        self.exact_rules.append(rule)
        return True


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.saved_kwargs = None
        self.saved_edits: list[PageEdit] = []

    def save(self, **kwargs) -> None:
        self.saved_kwargs = kwargs


class FakeClient:
    def __init__(self) -> None:
        self.reconnect_calls = 0
        self.prime_calls = 0

    def prime_write_session(self) -> bool:
        self.prime_calls += 1
        return self.prime_calls == 1

    def save_page(self, page_or_title, edit: PageEdit) -> None:
        assert not isinstance(page_or_title, str)
        page_or_title.text = edit.text
        page_or_title.saved_edits.append(edit)
        page_or_title.save(
            summary=edit.summary,
            minor=edit.minor,
            bot=True,
            asynchronous=False,
        )

    def reconnect(self) -> None:
        self.reconnect_calls += 1


class FakeUI:
    def __init__(
        self,
        page_action: str = "a",
        summary: str = "Edited summary",
        review_action: str = "r",
        template_text: str = "{{Крыніцы/Тэст}}",
    ) -> None:
        self.page_action = page_action
        self.summary = summary
        self.review_action = review_action
        self.template_text = template_text
        self.diff_calls: list[tuple[str, str]] = []
        self.used_rules: list[dict] = []
        self.candidate_lines: list[tuple[str, list[str]]] = []
        self.info_messages: list[str] = []
        self.warn_messages: list[str] = []
        self.error_messages: list[str] = []
        self.page_prompts: list[tuple[str, bool]] = []
        self.bulk_started: list[object] = []
        self.bulk_updates: list[object] = []

    def print_diff_panel(self, *, title: str, result, old_text: str, context: int) -> None:
        self.diff_calls.append((title, result.text))

    def print_used_rule(self, rule: dict) -> None:
        self.used_rules.append(rule)

    def print_candidate_lines(self, title: str, lines: list[str]) -> None:
        self.candidate_lines.append((title, lines))

    def prompt_review_match_action(self) -> str:
        return self.review_action

    def prompt_template_text(self, default_template: str) -> str:
        return self.template_text

    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str:
        self.page_prompts.append((current_summary, review_required))
        return self.page_action

    def prompt_summary(self, current_summary: str) -> str:
        return self.summary

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warn(self, message: str) -> None:
        self.warn_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def begin_bulk_run(self, status) -> None:
        self.bulk_started.append(status)

    def update_bulk_status(self, status) -> None:
        self.bulk_updates.append(status)

    def finish_bulk_run(self) -> None:
        self.bulk_updates.append("finished")


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
        bulk_mode_active=True,
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
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
    assert ui.info_messages[0] == "[prepare-save] Demo page: building edit payload..."
    assert ui.info_messages[1] == "[save-preflight] Demo page: verifying write session..."
    assert ui.info_messages[2] == "[save] Demo page: publishing edit..."
    assert ui.info_messages[3].startswith("[saved] Demo page: edit published in ")
    assert ui.info_messages[4] == "[rules] Promoted new review rules into rules.json"


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
        bulk_mode_active=True,
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert stats.skipped == 1
    assert page.saved_edits == []
    assert page.saved_kwargs is None
    assert ui.warn_messages == [
        "[skip] Demo page: review required; skipped in bulk mode. Heuristic entry match."
    ]


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
    monkeypatch.setattr(
        ui, "prompt_page_action", lambda current_summary, *, review_required=False: next(actions)
    )
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=2,
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
        source_label="demo (Demo) [1/1]",
        page_index=2,
        total_pages=2,
        stats=stats,
        deps=_deps(),
    )

    assert policy.summary_override == "Edited summary"
    assert first_page.saved_edits == [PageEdit(text="axc", summary="Edited summary", minor=True)]
    assert second_page.saved_edits == [PageEdit(text="axc", summary="Edited summary", minor=True)]
    assert (
        ui.info_messages[0]
        == "[bulk] Safe pages will now save automatically. Manual-review pages will still pause."
    )
    assert len(ui.bulk_started) == 1


def test_execute_page_stops_run_after_save_failure(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(page_action="a")
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
        bulk_mode_active=True,
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
        ),
        review_required=False,
        manual_review_lines=(),
    )

    class FailingClient:
        def __init__(self) -> None:
            self.prime_calls = 0

        def prime_write_session(self) -> bool:
            self.prime_calls += 1
            return self.prime_calls == 1

        def save_page(self, page_or_title, edit: PageEdit) -> None:
            raise RuntimeError("connection reset")

        def reconnect(self) -> None:
            raise AssertionError("reconnect should not be called for non-retryable errors")

    execute_page(
        analysis=analysis,
        spec=spec,
        options=policy.options,
        policy=policy,
        ui=ui,
        state=state,
        client=FailingClient(),
        page=page,
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert policy.stopped is True
    assert stats.errors == 1
    assert ui.info_messages == [
        "[prepare-save] Demo page: building edit payload...",
        "[save-preflight] Demo page: verifying write session...",
        "[save] Demo page: publishing edit...",
    ]
    assert ui.error_messages == ["[error] Demo page: connection reset"]
    assert ui.warn_messages == ["Stopped after save failure."]


def test_execute_page_learns_review_match_when_requested(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(review_action="r")
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=False,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=True,
            show_candidates=False,
        ),
        accept_all=False,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=[],
            page_arguments=[],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        ),
        review_required=True,
        manual_review_lines=("Demo entry // Demo encyclopedia",),
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert state.review_variants == ["Demo entry // Demo encyclopedia"]
    assert stats.learned == 1
    assert stats.ignored == 0
    assert ui.info_messages == [
        "[review] Added 1 line(s) to review_variants.json",
        "[dry-run] No changes saved",
    ]


def test_execute_page_ignores_review_match_when_requested(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(review_action="i")
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=False,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=True,
            show_candidates=False,
        ),
        accept_all=False,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=[],
            page_arguments=[],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        ),
        review_required=True,
        manual_review_lines=("Demo entry // Demo encyclopedia",),
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert state.review_variants == []
    assert state.ignored_hashes == {"Demo entry // Demo encyclopedia"}
    assert stats.learned == 0
    assert stats.ignored == 1
    assert ui.info_messages == [
        "[ignore] Added 1 line(s) to ignored_variants.json",
        "[dry-run] No changes saved",
    ]


def test_execute_page_skips_review_match_without_mutating_state(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(review_action="s")
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=False,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=True,
            show_candidates=False,
        ),
        accept_all=False,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=[],
            page_arguments=[],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        ),
        review_required=True,
        manual_review_lines=("Demo entry // Demo encyclopedia",),
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert state.review_variants == []
    assert state.ignored_hashes == set()
    assert stats.learned == 0
    assert stats.ignored == 0
    assert ui.info_messages == ["[dry-run] No changes saved"]


def test_execute_page_can_store_manual_exact_rule_for_review_match(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(review_action="e", template_text="{{Крыніцы/Тэст|Demo entry|42}}")
    policy = RunPolicy(
        options=RunOptions(
            source_ids=("demo",),
            query=None,
            limit=1,
            minor_threshold=1000,
            apply=False,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=True,
            show_candidates=False,
        ),
        accept_all=False,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=["{{Крыніцы/Тэст|Demo entry|42}}"],
            page_arguments=["42"],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        ),
        review_required=True,
        manual_review_lines=("Demo entry // Demo encyclopedia",),
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert state.exact_rules == [
        ("Demo entry // Demo encyclopedia", "{{Крыніцы/Тэст|Demo entry|42}}")
    ]
    assert stats.learned == 1
    assert stats.ignored == 0
    assert ui.info_messages == [
        "[rules] Added exact line rule to rules.json",
        "[dry-run] No changes saved",
    ]


def test_execute_page_apply_can_learn_review_match_before_save(tmp_path):
    spec = _spec(tmp_path)

    class LearningState:
        def __init__(self) -> None:
            self.review_variants: list[str] = []
            self.ignored_hashes: set[str] = set()
            self.saved_rules: list[dict] = []
            self.exact_rules: list[tuple[str, str]] = []

        @property
        def review_keys(self) -> set[str]:
            return set(self.review_variants)

        @property
        def active_rules(self) -> list[dict]:
            rules: list[dict] = []
            if self.review_variants:
                rules.append(
                    {
                        "kind": "line_exact",
                        "match": self.review_variants[0],
                        "replacement": "{{Крыніцы/Тэст|Demo entry|42}}",
                    }
                )
            for review_line, replacement in self.exact_rules:
                rules.append(
                    {
                        "kind": "line_exact",
                        "match": review_line,
                        "replacement": replacement,
                    }
                )
            return rules

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

        def add_exact_rule(self, review_line: str, replacement: str) -> bool:
            rule = (review_line, replacement)
            if rule in self.exact_rules:
                return False
            self.exact_rules.append(rule)
            return True

    def replace_text(*args, **kwargs):
        active_rules = kwargs.get("active_rules")
        if active_rules is None and len(args) >= 3:
            active_rules = args[2]
        active_rules = active_rules or []
        if active_rules:
            replacement = active_rules[-1]["replacement"]
            return ReplacementResult(
                text=replacement,
                replacements=1,
                used_line_rules=list(active_rules),
                used_rule_names=["line_exact"],
                rendered_templates=[replacement],
                page_arguments=["42"],
                entry_arguments=["Demo entry"],
            )
        return ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=["{{Крыніцы/Тэст|Demo entry|42}}"],
            page_arguments=["42"],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        )

    state = LearningState()
    page = FakePage("abc")
    ui = FakeUI(page_action="y", review_action="r")
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
            learn_variants=True,
            show_candidates=False,
        ),
        accept_all=False,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=["{{Крыніцы/Тэст|Demo entry|42}}"],
            page_arguments=["42"],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        ),
        review_required=True,
        manual_review_lines=("Demo entry // Demo encyclopedia",),
    )

    deps = RunnerDependencies(
        load_source_spec=lambda *args, **kwargs: None,
        load_source_state=lambda *args, **kwargs: None,
        create_site=lambda *args, **kwargs: (None, None),
        load_titles=lambda *args, **kwargs: (0, []),
        build_search_query=lambda spec: "",
        replace_text=replace_text,
        extract_unknown_variant_infos=lambda *args, **kwargs: [],
        debug_candidate_lines=lambda *args, **kwargs: ["candidate"],
        variant_review_key=lambda info: "",
        variant_review_hash=lambda info: "",
        variant_hash=lambda value: value,
        make_review_key=lambda line, spec: line,
        entry_matches_page_title=lambda entry, title: True,
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=deps,
    )

    assert state.review_variants == ["Demo entry // Demo encyclopedia"]
    assert stats.learned == 1
    assert ui.page_prompts == [("Замена {{Крыніцы/Тэст}}", False)]
    assert page.saved_edits == [
        PageEdit(
            text="{{Крыніцы/Тэст|Demo entry|42}}",
            summary="Замена {{Крыніцы/Тэст}}",
            minor=True,
        )
    ]
    assert ui.info_messages[:4] == [
        "[review] Added 1 line(s) to review_variants.json",
        "[prepare-save] Demo page: building edit payload...",
        "[save-preflight] Demo page: verifying write session...",
        "[save] Demo page: publishing edit...",
    ]


def test_execute_page_apply_review_skip_skips_page_without_save(tmp_path):
    spec = _spec(tmp_path)
    state = FakeState(active_rules=[])
    page = FakePage("abc")
    ui = FakeUI(page_action="y", review_action="s")
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
            learn_variants=True,
            show_candidates=False,
        ),
        accept_all=False,
    )
    stats = RunStats()
    analysis = PageAnalysis(
        title="Demo page",
        old_text="abc",
        result=ReplacementResult(
            text="axc",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=["{{Крыніцы/Тэст|Demo entry|42}}"],
            page_arguments=["42"],
            entry_arguments=["Demo entry"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Demo entry // Demo encyclopedia"],
        ),
        review_required=True,
        manual_review_lines=("Demo entry // Demo encyclopedia",),
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
        source_label="demo (Demo) [1/1]",
        page_index=1,
        total_pages=1,
        stats=stats,
        deps=_deps(),
    )

    assert stats.skipped == 1
    assert ui.page_prompts == []
    assert page.saved_edits == []
    assert ui.info_messages == ["[skip] Demo page: not saved"]
