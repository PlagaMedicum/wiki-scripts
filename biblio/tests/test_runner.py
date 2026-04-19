from __future__ import annotations

import io
from dataclasses import replace

from biblio.bootstrap import BotRightRequiredError
from biblio.models import (
    CandidateSpec,
    NormalizationOptions,
    ReplacementResult,
    RunOptions,
    SourceSpec,
)
from biblio.runner import (
    _changed_bytes,
    _is_minor_edit,
    _needs_interactive_input,
    run_source,
    run_sources,
)
from biblio.ui import AppUI
from rich.console import Console


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


def test_needs_interactive_input_only_when_run_can_prompt():
    assert _needs_interactive_input(
        RunOptions(
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
        has_review_required_rules=False,
    )
    assert _needs_interactive_input(
        RunOptions(
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
        has_review_required_rules=False,
    )
    assert not _needs_interactive_input(
        RunOptions(
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
            show_candidates=True,
        ),
        accept_all=False,
        has_review_required_rules=False,
    )
    assert _needs_interactive_input(
        RunOptions(
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
        has_review_required_rules=True,
    )
    assert not _needs_interactive_input(
        RunOptions(
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
        has_review_required_rules=True,
    )


def test_minor_edit_threshold_uses_changed_utf8_bytes():
    assert _changed_bytes("abc", "adc") == 2
    assert _is_minor_edit("a" * 400, "b" * 400, 1000)
    assert not _is_minor_edit("a" * 500, "b" * 500, 1000)
    assert _is_minor_edit("a" * 500, "b" * 500, 1001)


def test_interactive_run_does_not_use_live_progress(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

        def ensure_rule_saved(self, rule):
            return False

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = "No matching replacement here."

    class FakePywikibot:
        Page = FakePage

    spec = _spec(tmp_path)
    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site",
        lambda *args, **kwargs: (FakePywikibot, FakeSite()),
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (1, ["Test page"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="No matching replacement here.",
            replacements=0,
            used_line_rules=[],
            used_rule_names=[],
            rendered_templates=[],
            page_arguments=[],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ui,
        "track_titles",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("interactive runs should not use live progress")
        ),
    )

    exit_code = run_source(
        RunOptions(
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert '[q] 1/1 title="Test page"' in stream.getvalue()


def test_multi_source_apply_accept_all_carries_across_sources(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

    saved = []
    prompts = []
    title_batches = {
        "first": ["First page"],
        "second": ["Second page"],
    }

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved.append((self.title_value, kwargs["summary"], kwargs["minor"]))

    class FakePywikibot:
        Page = FakePage

    def fake_load_source_spec(source_id, root=None):
        return replace(_spec(tmp_path), source_id=source_id, name=source_id)

    def fake_load_titles(site, query, limit):
        source_id = query.split()[-1]
        return len(title_batches[source_id]), title_batches[source_id]

    def fake_build_search_query(spec):
        return f"query for {spec.source_id}"

    def fake_replace_text(*args, **kwargs):
        return ReplacementResult(
            text="{{Крыніцы/Тэст}}",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["line_exact"],
            rendered_templates=["{{Крыніцы/Тэст}}"],
            page_arguments=[],
            entry_arguments=[],
        )

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", fake_load_source_spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", fake_load_titles)
    monkeypatch.setattr("biblio.runner.build_search_query", fake_build_search_query)
    monkeypatch.setattr("biblio.runner.replace_text", fake_replace_text)
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])

    def fake_prompt_page_action(current_summary, *, review_required=False):
        prompts.append(current_summary)
        return "a"

    monkeypatch.setattr(ui, "prompt_page_action", fake_prompt_page_action)

    exit_code = run_sources(
        RunOptions(
            source_ids=("first", "second"),
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert prompts == ["Замена {{Крыніцы/Тэст}}"]
    assert saved == [
        ("First page", "Замена {{Крыніцы/Тэст}}", True),
        ("Second page", "Замена {{Крыніцы/Тэст}}", True),
    ]


def test_run_sources_reports_missing_bot_right_cleanly(monkeypatch, tmp_path):
    spec = _spec(tmp_path)
    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    def raise_bot_right_required(*args, **kwargs):
        raise BotRightRequiredError(
            "Authenticated account 'User Bot' lacks the local wiki `bot` right in this API "
            "session; biblio saves request bot=True for every edit. For BotPasswords, grant "
            "High-volume (bot) access."
        )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("biblio.runner.create_site", raise_bot_right_required)

    exit_code = run_sources(
        RunOptions(
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 1
    output = stream.getvalue()
    assert "demo: Authenticated account 'User Bot' lacks the local wiki `bot` right" in output
    assert "High-volume (bot) access" in output


def test_run_sources_expands_merged_source_into_volume_variants(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

    class FakeSite:
        pass

    base = _spec(tmp_path)
    volume_one = replace(base, source_id="belen", name="Т. 1", volume="1")
    volume_two = replace(base, source_id="belen", name="Т. 2", volume="2")
    merged = replace(
        base,
        source_id="belen",
        name="Беларуская энцыклапедыя",
        volume_variants=(volume_one, volume_two),
    )
    seen_queries = []

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: merged)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr("biblio.runner.create_site", lambda *args, **kwargs: (object, FakeSite()))
    monkeypatch.setattr(
        "biblio.runner.build_search_query",
        lambda spec: seen_queries.append(spec.volume or "") or f"query-{spec.volume}",
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (0, []))
    monkeypatch.setattr("biblio.runner.replace_text", lambda *args, **kwargs: None)
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    exit_code = run_sources(
        RunOptions(
            source_ids=("belen",),
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
        ),
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert seen_queries == ["1", "2"]


def test_run_sources_stops_after_first_bot_right_failure(monkeypatch, tmp_path):
    spec = _spec(tmp_path)
    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )
    seen = []

    def fake_load_source_spec(source_id, root=None):
        seen.append(source_id)
        return replace(spec, source_id=source_id, name=source_id)

    def raise_bot_right_required(*args, **kwargs):
        raise BotRightRequiredError(
            "Authenticated account 'User Bot' lacks the local wiki `bot` right in this API "
            "session; biblio saves request bot=True for every edit. For BotPasswords, grant "
            "High-volume (bot) access."
        )

    monkeypatch.setattr("biblio.runner.load_source_spec", fake_load_source_spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("biblio.runner.create_site", raise_bot_right_required)

    exit_code = run_sources(
        RunOptions(
            source_ids=("first", "second"),
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 1
    assert seen == ["first", "second"]
    output = stream.getvalue()
    assert "first: Authenticated account 'User Bot' lacks the local wiki `bot` right" in output
    assert "second:" not in output


def test_run_source_stops_after_first_non_retryable_save_failure(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

        def ensure_rule_saved(self, rule):
            return False

    saved_attempts = []

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved_attempts.append(self.title_value)
            raise RuntimeError("connection reset")

    class FakePywikibot:
        Page = FakePage

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: _spec(tmp_path))
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (2, ["One", "Two"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="{{Крыніцы/Тэст}}",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["line_exact"],
            rendered_templates=["{{Крыніцы/Тэст}}"],
            page_arguments=[],
            entry_arguments=[],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ui, "prompt_page_action", lambda current_summary, *, review_required=False: "a"
    )

    exit_code = run_source(
        RunOptions(
            source_ids=("demo",),
            query=None,
            limit=2,
            minor_threshold=1000,
            apply=True,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=False,
            show_candidates=False,
        ),
        ui,
        root=tmp_path,
    )

    assert exit_code == 1
    assert saved_attempts == ["One"]
    output = stream.getvalue()
    assert "[q] 1/2 title=One" in output
    assert "[q] 2/2 title=Two" not in output
    assert "[error] One: connection reset" in output
    assert "Stopped after save failure." in output


def test_run_source_continues_after_retryable_save_failure(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

        def ensure_rule_saved(self, rule):
            return False

    saved_attempts = []

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved_attempts.append(self.title_value)
            if self.title_value == "One":
                raise ConnectionError("connection reset")

    class FakePywikibot:
        Page = FakePage

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: _spec(tmp_path))
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (2, ["One", "Two"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="{{Крыніцы/Тэст}}",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["line_exact"],
            rendered_templates=["{{Крыніцы/Тэст}}"],
            page_arguments=[],
            entry_arguments=[],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ui, "prompt_page_action", lambda current_summary, *, review_required=False: "a"
    )

    exit_code = run_source(
        RunOptions(
            source_ids=("demo",),
            query=None,
            limit=2,
            minor_threshold=1000,
            apply=True,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=False,
            show_candidates=False,
        ),
        ui,
        root=tmp_path,
    )

    assert exit_code == 1
    assert saved_attempts == ["One", "One", "One", "One", "Two"]
    output = stream.getvalue()
    assert "[q] 1/2 title=One" in output
    assert "[failed] One: save failed after retries (connection reset)" in output
    assert "[q] 2/2 title=Two" in output
    assert "[saved] Two: edit published in " in output
    assert "Failed" in output
    assert "One" in output


def test_run_source_stops_cleanly_after_page_load_failure_post_skip(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

        def ensure_rule_saved(self, rule):
            return False

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self._text = f"content for {title}"

        @property
        def text(self):
            if self.title_value == "Two":
                raise ConnectionError("connection reset")
            return self._text

    class FakePywikibot:
        Page = FakePage

    replacements = iter(
        [
            ReplacementResult(
                text="{{Крыніцы/Тэст|Mismatch One}}",
                replacements=1,
                used_line_rules=[],
                used_rule_names=["entry_only"],
                rendered_templates=["{{Крыніцы/Тэст|Mismatch One}}"],
                page_arguments=[],
                entry_arguments=["Mismatch One"],
                review_reasons=["Heuristic entry match."],
                matched_review_lines=["Mismatch One // Demo encyclopedia"],
            ),
        ]
    )

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: _spec(tmp_path))
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (2, ["One", "Two"]))
    monkeypatch.setattr("biblio.runner.replace_text", lambda *args, **kwargs: next(replacements))
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])
    monkeypatch.setattr(ui, "prompt_review_match_action", lambda: "s")

    exit_code = run_source(
        RunOptions(
            source_ids=("demo",),
            query=None,
            limit=2,
            minor_threshold=1000,
            apply=False,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=True,
            show_candidates=False,
        ),
        ui,
        root=tmp_path,
    )

    assert exit_code == 1
    output = stream.getvalue()
    assert "[q] 1/2 title=One" in output
    assert "[dry-run] No changes saved" in output
    assert "[q] 2/2 title=Two" in output
    assert "[failed] Two: page load failed after retries (connection reset)" in output


def test_multi_source_run_reuses_site_bundle_for_same_wiki(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

    create_site_calls = 0

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

    class FakePywikibot:
        Page = FakePage

    def fake_load_source_spec(source_id, root=None):
        return replace(_spec(tmp_path), source_id=source_id, name=source_id)

    def fake_create_site(*args, **kwargs):
        nonlocal create_site_calls
        create_site_calls += 1
        return FakePywikibot, FakeSite()

    monkeypatch.setattr("biblio.runner.load_source_spec", fake_load_source_spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr("biblio.runner.create_site", fake_create_site)
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (1, ["Page"]))
    monkeypatch.setattr(
        "biblio.runner.build_search_query", lambda spec: f"query for {spec.source_id}"
    )
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="unchanged",
            replacements=0,
            used_line_rules=[],
            page_arguments=[],
            entry_arguments=[],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])

    ui = AppUI(
        no_color=True,
        console=Console(file=io.StringIO(), force_terminal=False, no_color=True, highlight=False),
    )

    exit_code = run_sources(
        RunOptions(
            source_ids=("first", "second"),
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
        ),
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert create_site_calls == 1


def test_accept_all_still_prompts_review_required_matches(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

    prompts = []
    saved = []

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved.append(self.title_value)

    class FakePywikibot:
        Page = FakePage

    spec = replace(
        _spec(tmp_path),
        template_without_pages="{{Крыніцы/Тэст|{entry}}}",
        template_with_pages="{{Крыніцы/Тэст|{entry}|{pages}}}",
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (2, ["One", "Two"]))
    monkeypatch.setattr("biblio.runner.build_search_query", lambda spec: "query")

    replacements = iter(
        [
            ReplacementResult(
                text="{{Крыніцы/Тэст|Mismatch One}}",
                replacements=1,
                used_line_rules=[],
                used_rule_names=["entry_only"],
                rendered_templates=["{{Крыніцы/Тэст|Mismatch One}}"],
                page_arguments=[],
                entry_arguments=["Mismatch One"],
                review_reasons=["Heuristic entry match."],
            ),
            ReplacementResult(
                text="{{Крыніцы/Тэст|Mismatch Two}}",
                replacements=1,
                used_line_rules=[],
                used_rule_names=["entry_only"],
                rendered_templates=["{{Крыніцы/Тэст|Mismatch Two}}"],
                page_arguments=[],
                entry_arguments=["Mismatch Two"],
                review_reasons=["Heuristic entry match."],
            ),
        ]
    )
    monkeypatch.setattr("biblio.runner.replace_text", lambda *args, **kwargs: next(replacements))
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])

    def fake_prompt_page_action(current_summary, *, review_required=False):
        prompts.append(review_required)
        return "a"

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )
    monkeypatch.setattr(ui, "prompt_page_action", fake_prompt_page_action)

    exit_code = run_source(
        RunOptions(
            source_ids=("demo",),
            query=None,
            limit=2,
            minor_threshold=1000,
            apply=True,
            assume_yes=False,
            skip_review_required=False,
            summary=None,
            context=3,
            learn_variants=False,
            show_candidates=False,
        ),
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert prompts == [True, True]
    assert saved == ["One", "Two"]
    assert "[q] 1/2 title=One" in stream.getvalue()
    assert "[q] 2/2 title=Two" in stream.getvalue()


def test_multi_source_apply_supports_summary_edit_for_remaining_sources(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

    saved = []
    actions = iter(["e", "a"])

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved.append((self.title_value, kwargs["summary"], kwargs["minor"]))

    class FakePywikibot:
        Page = FakePage

    def fake_load_source_spec(source_id, root=None):
        return replace(_spec(tmp_path), source_id=source_id, name=source_id)

    monkeypatch.setattr("biblio.runner.load_source_spec", fake_load_source_spec)
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (1, ["Page"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="{{Крыніцы/Тэст}}",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["line_exact"],
            rendered_templates=["{{Крыніцы/Тэст}}"],
            page_arguments=[],
            entry_arguments=[],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ui := AppUI(
            no_color=True,
            console=Console(
                file=io.StringIO(), force_terminal=False, no_color=True, highlight=False
            ),
        ),
        "prompt_page_action",
        lambda current_summary, *, review_required=False: next(actions),
    )
    monkeypatch.setattr(ui, "prompt_summary", lambda current_summary: "Edited summary")

    exit_code = run_sources(
        RunOptions(
            source_ids=("first", "second"),
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert saved == [
        ("Page", "Edited summary", True),
        ("Page", "Edited summary", True),
    ]


def test_learn_only_run_can_promote_review_required_match_to_review_variants(
    monkeypatch,
    tmp_path,
):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

        @property
        def review_keys(self):
            return set(self.review_variants)

        def add_review_variant(self, review_line):
            if review_line in self.review_variants:
                return False
            self.review_variants.append(review_line)
            return True

        def add_ignored_hash(self, value):
            self.ignored_hashes.add(value)
            return True

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = "content for review"

    class FakePywikibot:
        Page = FakePage

    state = FakeState()
    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: _spec(tmp_path))
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: state)
    monkeypatch.setattr(
        "biblio.runner.create_site",
        lambda *args, **kwargs: (FakePywikibot, FakeSite()),
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (1, ["Review page"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="{{Крыніцы/Тэст}}",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=["{{Крыніцы/Тэст}}"],
            page_arguments=[],
            entry_arguments=["Mismatch One"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Mismatch One // Demo encyclopedia"],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])
    monkeypatch.setattr(ui, "prompt_review_match_action", lambda: "r")

    exit_code = run_source(
        RunOptions(
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert state.review_variants == ["Mismatch One // Demo encyclopedia"]
    assert "[review] Added 1 line(s) to review_variants.json" in stream.getvalue()


def test_skip_review_required_avoids_prompt_and_save(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

    prompted = []
    saved = []

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved.append(self.title_value)

    class FakePywikibot:
        Page = FakePage

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: _spec(tmp_path))
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (1, ["One"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="{{Крыніцы/Тэст|Mismatch One}}",
            replacements=1,
            used_line_rules=[],
            used_rule_names=["entry_only"],
            rendered_templates=["{{Крыніцы/Тэст|Mismatch One}}"],
            page_arguments=[],
            entry_arguments=["Mismatch One"],
            review_reasons=["Heuristic entry match."],
            matched_review_lines=["Mismatch One // Demo encyclopedia"],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    def fake_prompt_page_action(current_summary, *, review_required=False):
        prompted.append((current_summary, review_required))
        return "y"

    monkeypatch.setattr(ui, "prompt_page_action", fake_prompt_page_action)

    exit_code = run_source(
        RunOptions(
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert prompted == []
    assert saved == []
    assert (
        "[skip] One: review required; skipped in bulk mode. Heuristic entry match."
        in stream.getvalue()
    )


def test_learned_exact_rule_no_longer_requires_title_review(monkeypatch, tmp_path):
    class FakeState:
        base_rules = []
        review_variants = []
        active_rules = []
        ignored_hashes = set()

        def ensure_rule_saved(self, rule):
            return False

    prompted = []
    saved = []

    class FakeSite:
        pass

    class FakePage:
        def __init__(self, site, title):
            self.site = site
            self.title_value = title
            self.text = f"content for {title}"

        def save(self, **kwargs):
            saved.append(self.title_value)

    class FakePywikibot:
        Page = FakePage

    monkeypatch.setattr("biblio.runner.load_source_spec", lambda *args, **kwargs: _spec(tmp_path))
    monkeypatch.setattr("biblio.runner.load_source_state", lambda *args, **kwargs: FakeState())
    monkeypatch.setattr(
        "biblio.runner.create_site", lambda *args, **kwargs: (FakePywikibot, FakeSite())
    )
    monkeypatch.setattr("biblio.runner._load_titles", lambda *args, **kwargs: (1, ["Page Title"]))
    monkeypatch.setattr(
        "biblio.runner.replace_text",
        lambda *args, **kwargs: ReplacementResult(
            text="{{Крыніцы/Тэст|Mismatch One}}",
            replacements=1,
            used_line_rules=[
                {
                    "kind": "line_exact",
                    "match": "demo",
                    "replacement": "{{Крыніцы/Тэст|Mismatch One}}",
                }
            ],
            used_rule_names=["line_exact"],
            rendered_templates=["{{Крыніцы/Тэст|Mismatch One}}"],
            page_arguments=[],
            entry_arguments=["Mismatch One"],
            review_reasons=[],
            matched_review_lines=[],
        ),
    )
    monkeypatch.setattr("biblio.runner.extract_unknown_variant_infos", lambda *args, **kwargs: [])

    stream = io.StringIO()
    ui = AppUI(
        no_color=True,
        console=Console(file=stream, force_terminal=False, no_color=True, highlight=False),
    )

    def fake_prompt_page_action(current_summary, *, review_required=False):
        prompted.append((current_summary, review_required))
        return "y"

    monkeypatch.setattr(ui, "prompt_page_action", fake_prompt_page_action)

    exit_code = run_source(
        RunOptions(
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
        ui,
        root=tmp_path,
    )

    assert exit_code == 0
    assert prompted == []
    assert saved == ["Page Title"]
