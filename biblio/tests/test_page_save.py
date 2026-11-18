from __future__ import annotations

import inspect
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
from biblio.page_save import (
    PageSavePlan,
    _changed_bytes,
    _is_minor_edit,
    apply_page_save,
    plan_page_save,
)
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
        self.bulk_statuses = []

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

    def update_bulk_status(self, status) -> None:
        self.bulk_statuses.append(status)


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
        self.reconnect_calls = 0
        self.prime_calls = 0

    def save_page(self, page_or_title, edit: PageEdit) -> None:
        self.calls.append((page_or_title, edit))

    def prime_write_session(self) -> bool:
        self.prime_calls += 1
        return self.prime_calls == 1

    def reconnect(self) -> None:
        self.reconnect_calls += 1


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
        old_text="abc",
        new_text="axc",
        summary="Edited summary",
        minor_threshold=1000,
        used_line_rules=({"kind": "line_exact", "replacement": "axc"},),
    )
    assert policy.summary_override == "Edited summary"
    assert policy.accept_all
    assert policy.bulk_mode_active


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


def test_plan_page_save_skips_page_when_requested(tmp_path):
    spec = _spec(tmp_path)
    ui = FakeUI(actions=["n"])
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

    assert plan is None
    assert stats.skipped == 1
    assert policy.stopped is False
    assert ui.info_messages == ["[skip] Demo page: not saved"]


def test_plan_page_save_stops_run_when_requested(tmp_path):
    spec = _spec(tmp_path)
    ui = FakeUI(actions=["q"])
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

    assert plan is None
    assert stats.skipped == 0
    assert policy.stopped is True
    assert ui.warn_messages == ["Stopped by user."]


def test_apply_page_save_uses_client_transport_and_promotes_rules():
    state = FakeState(saved_rules=[])
    ui = FakeUI()
    stats = RunStats()
    page = FakePage()
    client = FakeClient()
    plan = PageSavePlan(
        title="Demo page",
        old_text="abc",
        new_text="axc",
        summary="Edited summary",
        minor_threshold=1000,
        used_line_rules=({"kind": "line_exact", "replacement": "axc"},),
    )

    outcome = apply_page_save(
        plan=plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )

    assert outcome.saved is True
    assert outcome.fatal is False
    assert client.calls == [(page, PageEdit(text="axc", summary="Edited summary", minor=True))]
    assert client.prime_calls == 1
    assert state.saved_rules == [{"kind": "line_exact", "replacement": "axc"}]
    assert stats.saved == 1
    assert ui.info_messages[0] == "[prepare-save] Demo page: building edit payload..."
    assert ui.info_messages[1] == "[save-preflight] Demo page: verifying write session..."
    assert ui.info_messages[2] == "[save] Demo page: publishing edit..."
    assert ui.info_messages[3].startswith("[saved] Demo page: edit published in ")
    assert ui.info_messages[4] == "[rules] Promoted new review rules into rules.json"


def test_apply_page_save_reports_error_and_returns_false():
    state = FakeState(saved_rules=[])
    ui = FakeUI()
    stats = RunStats()
    page = FakePage()
    plan = PageSavePlan(
        title="Demo page",
        old_text="abc",
        new_text="axc",
        summary="Edited summary",
        minor_threshold=1000,
        used_line_rules=({"kind": "line_exact", "replacement": "axc"},),
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

    outcome = apply_page_save(
        plan=plan,
        client=FailingClient(),
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )

    assert outcome.saved is False
    assert outcome.fatal is True
    assert state.saved_rules == []
    assert stats.saved == 0
    assert stats.errors == 1
    assert ui.info_messages == [
        "[prepare-save] Demo page: building edit payload...",
        "[save-preflight] Demo page: verifying write session...",
        "[save] Demo page: publishing edit...",
    ]
    assert ui.error_messages == ["[error] Demo page: connection reset"]


def test_apply_page_save_retries_transient_save_failure():
    state = FakeState(saved_rules=[])
    ui = FakeUI()
    stats = RunStats()
    page = FakePage()
    plan = PageSavePlan(
        title="Demo page",
        old_text="abc",
        new_text="axc",
        summary="Edited summary",
        minor_threshold=1000,
        used_line_rules=(),
    )

    class FlakyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[object, PageEdit]] = []
            self.reconnect_calls = 0
            self.prime_calls = 0

        def prime_write_session(self) -> bool:
            self.prime_calls += 1
            return self.prime_calls == 1

        def save_page(self, page_or_title, edit: PageEdit) -> None:
            self.calls.append((page_or_title, edit))
            if len(self.calls) == 1:
                raise ConnectionError("connection reset")

        def reconnect(self) -> None:
            self.reconnect_calls += 1

    client = FlakyClient()

    outcome = apply_page_save(
        plan=plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )

    assert outcome.saved is True
    assert outcome.fatal is False
    assert client.reconnect_calls == 1
    assert client.prime_calls == 2
    assert client.calls == [
        (page, PageEdit(text="axc", summary="Edited summary", minor=True)),
        (page, PageEdit(text="axc", summary="Edited summary", minor=True)),
    ]
    assert stats.saved == 1
    assert stats.retry_events == 1
    assert any(message.startswith("[retry] Demo page: save failed") for message in ui.warn_messages)


def test_apply_page_save_marks_retryable_failure_as_failed_page():
    state = FakeState(saved_rules=[])
    ui = FakeUI()
    stats = RunStats()
    page = FakePage()
    plan = PageSavePlan(
        title="Demo page",
        old_text="abc",
        new_text="axc",
        summary="Edited summary",
        minor_threshold=1000,
        used_line_rules=(),
    )

    class AlwaysFailingClient:
        def __init__(self) -> None:
            self.reconnect_calls = 0
            self.prime_calls = 0

        def prime_write_session(self) -> bool:
            self.prime_calls += 1
            return self.prime_calls == 1

        def save_page(self, page_or_title, edit: PageEdit) -> None:
            raise ConnectionError("connection reset")

        def reconnect(self) -> None:
            self.reconnect_calls += 1

    client = AlwaysFailingClient()

    outcome = apply_page_save(
        plan=plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )

    assert outcome.saved is False
    assert outcome.fatal is False
    assert stats.failed == 1
    assert stats.failed_titles == ["Demo page"]
    assert stats.retry_events == 3
    assert client.reconnect_calls == 3
    assert ui.error_messages == ["[failed] Demo page: save failed after retries (connection reset)"]


def test_changed_bytes_uses_linear_window_heuristic():
    assert "SequenceMatcher" not in inspect.getsource(_changed_bytes)
    assert _is_minor_edit("prefix old suffix", "prefix new suffix", 20)
    assert not _is_minor_edit("a" * 500, "b" * 500, 1000)
    assert _changed_bytes("abc123xyz", "abcZZZxyz") == 6


def test_apply_page_save_reports_prepare_save_before_hidden_work(monkeypatch):
    state = FakeState(saved_rules=[])
    ui = FakeUI()
    stats = RunStats()
    page = FakePage()
    client = FakeClient()
    plan = PageSavePlan(
        title="Demo page",
        old_text="abc",
        new_text="axc",
        summary="Edited summary",
        minor_threshold=1000,
        used_line_rules=(),
    )
    heartbeat_messages = []

    class FakeMonitor:
        def __init__(self, _ui, *, start_message, pending_message, on_heartbeat=None, **kwargs):
            self.start_message = start_message
            self.pending_message = pending_message
            self.on_heartbeat = on_heartbeat

        def __enter__(self):
            ui.info(self.start_message)
            if self.start_message.startswith("[prepare-save]"):
                heartbeat_messages.append(self.pending_message)
                if self.on_heartbeat is not None:
                    self.on_heartbeat(2.0)
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("biblio.page_save.monitor_operation", FakeMonitor)

    outcome = apply_page_save(
        plan=plan,
        client=client,
        page=page,
        state=state,
        stats=stats,
        ui=ui,
    )

    assert outcome.saved is True
    assert heartbeat_messages == ["[wait] Demo page: still building edit payload"]
    assert ui.info_messages[:3] == [
        "[prepare-save] Demo page: building edit payload...",
        "[save-preflight] Demo page: verifying write session...",
        "[save] Demo page: publishing edit...",
    ]
