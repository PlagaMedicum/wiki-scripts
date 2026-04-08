from __future__ import annotations

import io

import pytest
from rich.console import Console

from bewiki_biblio.cli import main
from bewiki_biblio.models import ReplacementResult, RunStats
from bewiki_biblio.ui import AppUI, ChecklistOption


def test_list_command_no_color(capsys):
    exit_code = main(["list", "--no-color"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "gvb1" in output
    assert "gvb20" in output
    assert "Available bibliography sources" in output
    assert "\x1b[" not in output


def test_main_without_arguments_launches_startup_wizard(monkeypatch):
    captured = {}

    def fake_startup(ui):
        captured["no_color"] = ui.no_color
        return 0

    monkeypatch.setattr("bewiki_biblio.cli._interactive_startup", fake_startup)

    exit_code = main([])

    assert exit_code == 0
    assert captured["no_color"] is False


def test_main_without_command_supports_no_color_startup(monkeypatch):
    captured = {}

    def fake_startup(ui):
        captured["no_color"] = ui.no_color
        return 0

    monkeypatch.setattr("bewiki_biblio.cli._interactive_startup", fake_startup)

    exit_code = main(["--no-color"])

    assert exit_code == 0
    assert captured["no_color"] is True


def test_run_command_accepts_multiple_source_ids(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("bewiki_biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "gvb1", "gvb2", "--no-color"])

    assert exit_code == 0
    assert captured["options"].source_ids == ("gvb1", "gvb2")
    assert captured["options"].minor_threshold == 1000
    assert captured["options"].skip_review_required is False


def test_run_command_splits_comma_separated_source_ids(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("bewiki_biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "gvb1,gvb2", "gvb3", "--no-color"])

    assert exit_code == 0
    assert captured["options"].source_ids == ("gvb1", "gvb2", "gvb3")


def test_run_command_accepts_all_sources_flag(monkeypatch):
    captured = {}

    class FakeSpec:
        def __init__(self, source_id):
            self.source_id = source_id

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("bewiki_biblio.cli.discover_source_specs", lambda: [FakeSpec("gvb1"), FakeSpec("gvb2")])
    monkeypatch.setattr("bewiki_biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "--all", "--no-color"])

    assert exit_code == 0
    assert captured["options"].source_ids == ("gvb1", "gvb2")


def test_run_command_accepts_minor_threshold(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("bewiki_biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "gvb1", "--minor-threshold", "250", "--no-color"])

    assert exit_code == 0
    assert captured["options"].minor_threshold == 250


def test_run_command_accepts_skip_review_required(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("bewiki_biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "gvb1", "--skip-review-required", "--no-color"])

    assert exit_code == 0
    assert captured["options"].skip_review_required is True


def test_run_command_rejects_all_with_explicit_sources(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--all", "gvb1", "--no-color"])

    assert excinfo.value.code == 2
    assert "either --all or explicit source identifiers" in capsys.readouterr().err


def test_run_command_requires_source_ids_or_all(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--no-color"])

    assert excinfo.value.code == 2
    assert "at least one source identifier or --all" in capsys.readouterr().err


def test_rich_diff_panel_snapshot(gvb_spec):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=100,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    result = ReplacementResult(
        text="{{Крыніцы/ГВБ|1-1||213}}",
        replacements=1,
        used_line_rules=[],
        rendered_templates=["{{Крыніцы/ГВБ|1-1||213}}"],
        page_arguments=["213"],
    )
    ui.print_diff_panel(
        title="Тэставая старонка",
        result=result,
        old_text="Старая бібліяграфія",
        context=3,
    )

    output = stream.getvalue()
    assert "Proposed change" in output
    assert "Тэставая старонка" in output
    assert "{{Крыніцы/ГВБ|1-1||213}}" in output
    assert "@@" in output


def test_final_summary_snapshot():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=100,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    ui.print_final_summary(
        RunStats(
            processed=10,
            matched=4,
            saved=2,
            skipped=6,
            errors=1,
            learned=1,
            ignored=2,
        )
    )

    output = stream.getvalue()
    assert "Run summary" in output
    assert "Processed" in output
    assert "10" in output


def test_prompt_csv_without_default_does_not_pass_empty_default(monkeypatch):
    captured = {}

    def fake_ask(label, **kwargs):
        captured["label"] = label
        captured["kwargs"] = kwargs
        return "term 1, term 2"

    monkeypatch.setattr("bewiki_biblio.ui.Prompt.ask", fake_ask)
    ui = AppUI(no_color=True, console=Console(file=io.StringIO(), no_color=True))

    result = ui.prompt_csv("Insource terms (comma-separated)")

    assert result == ("term 1", "term 2")
    assert captured["label"] == "Insource terms (comma-separated)"
    assert "default" not in captured["kwargs"]


def test_run_guidance_mentions_interactive_controls():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)

    ui.print_run_guidance(
        apply=True,
        assume_yes=False,
        has_review_required_rules=True,
        skip_review_required=True,
        learn_variants=True,
        show_candidates=True,
    )

    output = stream.getvalue()
    assert "Interactive guidance" in output
    assert "review_variants.json" in output
    assert "`y` save" in output
    assert "still stop for confirmation" in output
    assert "skipped automatically instead of prompting" in output
    assert "candidate lines" in output
    assert "one key directly" in output


def test_prompt_choice_uses_single_key_input(monkeypatch):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)

    monkeypatch.setattr(ui, "_supports_single_key_input", lambda: True)
    monkeypatch.setattr(ui, "_read_single_key", lambda: "r")

    assert ui.prompt_choice(
        "Choose variant action [r=review, i=ignore, s=skip]",
        choices=["r", "i", "s"],
        default="s",
    ) == "r"

    output = stream.getvalue()
    assert "Choose variant action [r=review, i=ignore, s=skip]" in output
    assert "r" in output


def test_prompt_checklist_supports_select_all_single_key(monkeypatch):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    keys = iter(["a", "\r"])

    monkeypatch.setattr(ui, "_supports_single_key_input", lambda: True)
    monkeypatch.setattr(ui, "_read_single_key", lambda: next(keys))

    result = ui.prompt_checklist(
        "Select sources",
        [
            ChecklistOption("gvb1", "gvb1", "First source"),
            ChecklistOption("gvb2", "gvb2", "Second source"),
        ],
        allow_empty=False,
    )

    assert result == ("gvb1", "gvb2")
    output = stream.getvalue()
    assert "Select sources" in output
    assert "select all" in output


def test_prompt_choice_falls_back_to_prompt_ask(monkeypatch):
    captured = {}
    ui = AppUI(no_color=True, console=Console(file=io.StringIO(), no_color=True))

    monkeypatch.setattr(ui, "_supports_single_key_input", lambda: False)

    def fake_ask(label, **kwargs):
        captured["label"] = label
        captured["kwargs"] = kwargs
        return "s"

    monkeypatch.setattr("bewiki_biblio.ui.Prompt.ask", fake_ask)

    assert ui.prompt_choice(
        "Choose variant action [r=review, i=ignore, s=skip]",
        choices=["r", "i", "s"],
        default="s",
    ) == "s"
    assert captured["label"] == "Choose variant action [r=review, i=ignore, s=skip]"
    assert captured["kwargs"]["choices"] == ["r", "i", "s"]
    assert captured["kwargs"]["default"] == "s"


def test_prompt_variant_action_shows_help_once(monkeypatch):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    labels = []

    def fake_prompt_choice(label, **kwargs):
        labels.append(label)
        return "s"

    monkeypatch.setattr(ui, "prompt_choice", fake_prompt_choice)

    assert ui.prompt_variant_action() == "s"
    assert ui.prompt_variant_action() == "s"

    output = stream.getvalue()
    assert output.count("Variant review controls") == 1
    assert "Add this variant to review_variants.json" in output
    assert labels == [
        "Choose variant action [r=review, i=ignore, s=skip]",
        "Choose variant action [r=review, i=ignore, s=skip]",
    ]


def test_prompt_page_action_shows_help_once(monkeypatch):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    labels = []

    def fake_prompt_choice(label, **kwargs):
        labels.append(label)
        return "n"

    monkeypatch.setattr(ui, "prompt_choice", fake_prompt_choice)

    assert ui.prompt_page_action("Summary 1") == "n"
    assert ui.prompt_page_action("Summary 2") == "n"

    output = stream.getvalue()
    assert output.count("Save controls") == 1
    assert "Save this page and all remaining non-review-required pages." in output
    assert "Current edit summary: Summary 1" in output
    assert "Current edit summary: Summary 2" in output
    assert labels == [
        "Choose page action [y=save, n=skip, a=save all, e=edit summary, q=quit]",
        "Choose page action [y=save, n=skip, a=save all, e=edit summary, q=quit]",
    ]


def test_prompt_review_match_action_shows_help_once(monkeypatch):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    labels = []

    def fake_prompt_choice(label, **kwargs):
        labels.append(label)
        return "s"

    monkeypatch.setattr(ui, "prompt_choice", fake_prompt_choice)

    assert ui.prompt_review_match_action() == "s"
    assert ui.prompt_review_match_action() == "s"

    output = stream.getvalue()
    assert output.count("Manual review controls") == 1
    assert "future exact replacement" in output
    assert labels == [
        "Choose review action [r=learn exact, i=ignore, s=skip]",
        "Choose review action [r=learn exact, i=ignore, s=skip]",
    ]
