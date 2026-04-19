from __future__ import annotations

from pathlib import Path

from biblio.manage_render import render_source_toml
from biblio.manage_reports import render_add_source_preview
from biblio.manage_tui import _build_basics_panel, collect_scaffold_tui
from biblio.models import SourceScaffold
from biblio.specs import DEFAULT_PAGE_PATTERNS, DEFAULT_REJECT_PATTERNS
from biblio.ui import AppUI
from rich.console import Console


def _fixture_text(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / "template_raw" / name
    return path.read_text(encoding="utf-8")


class FakePromptInput:
    def __init__(self, responses):
        self._responses = iter(responses)

    def prompt_text(self, _label, *, default="", multiline=False, help_text=""):
        value = next(self._responses)
        if value == "__DEFAULT__":
            return default
        return value

    def prompt_choice(self, _label, *, choices, default=None, help_text=""):
        value = next(self._responses)
        if value == "__DEFAULT__":
            return default
        assert value in choices
        return value

    def confirm(self, _label, *, default=True, help_text=""):
        value = next(self._responses)
        if value == "__DEFAULT__":
            return default
        return value

    def prompt_csv(self, _label, *, default=(), help_text=""):
        value = next(self._responses)
        if value == "__DEFAULT__":
            return default
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def prompt_int(self, _label, *, default, minimum=0, help_text=""):
        value = next(self._responses)
        if value == "__DEFAULT__":
            return default
        return value


def _ui() -> AppUI:
    return AppUI(no_color=True, console=Console(record=True, width=120))


def test_collect_scaffold_tui_fetch_import_populates_merged_source(tmp_path):
    prompt = FakePromptInput(
        [
            "Беларуская энцыклапедыя",
            "belen-imported",
            "be",
            "wikipedia",
            False,
            "f",
            "Шаблон:Крыніцы/БелЭн",
            "__DEFAULT__",
            "__DEFAULT__",
            "__DEFAULT__",
            "",
            "",
            "__DEFAULT__",
            "__DEFAULT__",
            False,
            "Imported BelEn source scaffold.",
        ]
    )

    scaffold = collect_scaffold_tui(
        _ui(),
        tmp_path,
        input_adapter=prompt,
        fetcher=lambda title, site_lang, family: _fixture_text("belen.txt"),
    )

    assert scaffold.template_name == "Крыніцы/БелЭн"
    assert scaffold.imported_from_title == "Шаблон:Крыніцы/БелЭн"
    assert (
        scaffold.template_without_pages
        == "{{Крыніцы/БелЭн|{volume}|{entry}|{author}||{responsible}}}"
    )
    assert (
        scaffold.template_with_pages
        == "{{Крыніцы/БелЭн|{volume}|{entry}|{author}|{pages}|{responsible}}}"
    )
    assert scaffold.insource_terms == ("Беларуская энцыклапедыя",)
    assert scaffold.candidate_all == ("Беларуская энцыклапедыя",)
    assert scaffold.volumes[0].name == "Т. 1: А — Аршын"
    assert scaffold.volumes[0].short_ref_ref == "БелЭн"
    assert scaffold.volumes[0].short_ref_year == "1996"
    assert scaffold.volumes[-1].volume == "18-2"
    assert len(scaffold.volumes) == 19
    assert {item.name for item in scaffold.argument_extractors} == {"author", "responsible"}
    source_toml = render_source_toml(scaffold)
    assert "[argument_extractors.author]" in source_toml
    assert "# - volume: том, 1" in source_toml


def test_collect_scaffold_tui_accepts_pasted_raw_source_and_keeps_extra_params_as_notes(tmp_path):
    raw = """
|частка = {{{артыкул|{{{2|}}}}}}
|аўтар = {{{аўтар|{{{3|}}}}}}
|ref = {{{ref|Прыклад}}}
|extra = {{{псеўданім|}}}
"""
    prompt = FakePromptInput(
        [
            "Прыклад",
            "example-imported",
            "be",
            "wikipedia",
            True,
            "p",
            "Шаблон:Крыніцы/Прыклад",
            raw,
            "__DEFAULT__",
            "n",
            "Прыклад",
            "",
            "",
            "__DEFAULT__",
            "__DEFAULT__",
            "Example imported source.",
        ]
    )

    scaffold = collect_scaffold_tui(_ui(), tmp_path, input_adapter=prompt)

    assert scaffold.template_name == "Крыніцы/Прыклад"
    assert scaffold.imported_from_title == "Шаблон:Крыніцы/Прыклад"
    assert "Unmapped template parameter retained as note: псеўданім" in scaffold.import_notes
    assert "Прыклад" in render_source_toml(scaffold)


def test_collect_scaffold_tui_uses_imported_template_forms_for_rb7(tmp_path):
    prompt = FakePromptInput(
        [
            "Рэспубліка Беларусь",
            "rb7-imported",
            "be",
            "wikipedia",
            False,
            "f",
            "Шаблон:Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах",
            True,
            "__DEFAULT__",
            "__DEFAULT__",
            "",
            "",
            "__DEFAULT__",
            "__DEFAULT__",
            False,
            "Imported RB7 source scaffold.",
        ]
    )

    scaffold = collect_scaffold_tui(
        _ui(),
        tmp_path,
        input_adapter=prompt,
        fetcher=lambda title, site_lang, family: _fixture_text("rb7.txt"),
    )

    assert (
        scaffold.template_without_pages
        == "{{Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах|{volume}|{entry}||{author}}}"
    )
    assert (
        scaffold.template_with_pages
        == "{{Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах|{volume}|{entry}|{pages}|{author}}}"
    )
    assert len(scaffold.volumes) == 7
    assert scaffold.volumes[1].name == "2: А — Герань"
    assert scaffold.volumes[1].short_ref_year == "2006"


def test_add_source_tui_glossary_panel_describes_terms():
    ui = _ui()
    ui.print(_build_basics_panel(ui))
    output = ui.console.export_text()

    assert "Alias" in output
    assert "Insource term" in output
    assert "Keyword" in output
    assert "Candidate all/any" in output


def test_render_add_source_preview_prints_source_and_readme():
    ui = _ui()
    scaffold = SourceScaffold(
        source_id="example",
        name="Example",
        site_lang="be",
        family="wikipedia",
        template_name="Крыніцы/Прыклад",
        template_without_pages="{{Крыніцы/Прыклад}}",
        template_with_pages="{{Крыніцы/Прыклад|{pages}}}",
        default_summary_format="Замена {{{template_name}}}",
        insource_terms=("Example",),
        isbns=(),
        keywords=(),
        candidate_all=("Example",),
        candidate_any=(),
        page_patterns=DEFAULT_PAGE_PATTERNS,
        reject_patterns=DEFAULT_REJECT_PATTERNS,
        description="Example source.",
    )

    render_add_source_preview(ui, scaffold)
    output = ui.console.export_text()

    assert "Preview: source.toml" in output
