from __future__ import annotations

import io
from dataclasses import replace

import pytest
from biblio.cli import main
from biblio.models import BulkRunStatus, ReplacementResult, RunStats
from biblio.specs import discover_source_specs, load_source_spec
from biblio.ui import AppUI, ChecklistOption
from rich.console import Console


def test_list_command_no_color(capsys, monkeypatch, repo_root):
    monkeypatch.setattr(
        "biblio.runner.discover_source_specs",
        lambda: discover_source_specs(root=repo_root),
    )
    exit_code = main(["list", "--no-color"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "gvb1" in output
    assert "gvb20" in output
    assert "Available bibliography sources" in output
    assert "\x1b[" not in output


def test_help_mentions_startup_wizard(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])

    output = capsys.readouterr().out
    assert "startup wizard" in output.lower()
    assert "no subcommand" in output.lower()
    assert "usage: biblio" in output.lower()
    assert "first developed for be.wiki" in output.lower()


def test_main_without_arguments_launches_startup_wizard(monkeypatch):
    captured = {}

    def fake_startup(ui):
        captured["no_color"] = ui.no_color
        return 0

    monkeypatch.setattr("biblio.cli._interactive_startup", fake_startup)

    exit_code = main([])

    assert exit_code == 0
    assert captured["no_color"] is False


def test_main_without_command_supports_no_color_startup(monkeypatch):
    captured = {}

    def fake_startup(ui):
        captured["no_color"] = ui.no_color
        return 0

    monkeypatch.setattr("biblio.cli._interactive_startup", fake_startup)

    exit_code = main(["--no-color"])

    assert exit_code == 0
    assert captured["no_color"] is True


def test_run_command_accepts_multiple_source_ids(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("biblio.cli.run_sources", fake_run_sources)

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

    monkeypatch.setattr("biblio.cli.run_sources", fake_run_sources)

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

    monkeypatch.setattr(
        "biblio.cli.discover_source_specs", lambda: [FakeSpec("gvb1"), FakeSpec("gvb2")]
    )
    monkeypatch.setattr("biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "--all", "--no-color"])

    assert exit_code == 0
    assert captured["options"].source_ids == ("gvb1", "gvb2")


def test_run_command_accepts_minor_threshold(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "gvb1", "--minor-threshold", "250", "--no-color"])

    assert exit_code == 0
    assert captured["options"].minor_threshold == 250


def test_run_command_accepts_skip_review_required(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    monkeypatch.setattr("biblio.cli.run_sources", fake_run_sources)

    exit_code = main(["run", "gvb1", "--skip-review-required", "--no-color"])

    assert exit_code == 0
    assert captured["options"].skip_review_required is True


def test_run_command_accepts_verbose_and_configures_logging(monkeypatch):
    captured = {}

    def fake_run_sources(options, ui):
        captured["options"] = options
        return 0

    def fake_configure_logging(*, verbose):
        captured["verbose"] = verbose
        return "logs/biblio.log"

    monkeypatch.setattr("biblio.cli.run_sources", fake_run_sources)
    monkeypatch.setattr("biblio.cli.configure_logging", fake_configure_logging)

    exit_code = main(["run", "gvb1", "--verbose", "--no-color"])

    assert exit_code == 0
    assert captured["options"].source_ids == ("gvb1",)
    assert captured["verbose"] is True


def test_main_returns_130_on_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setattr(
        "biblio.cli._interactive_startup", lambda ui: (_ for _ in ()).throw(KeyboardInterrupt)
    )

    exit_code = main([])

    assert exit_code == 130
    assert "Stopped by user." in capsys.readouterr().out


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
    assert "Inferred pages" in output
    assert "Decision" in output
    assert "safe to auto-apply" in output
    assert "{{Крыніцы/ГВБ|1-1||213}}" in output
    assert "@@" in output


def test_rich_diff_panel_explains_manual_review_reasoning():
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
        text="{{Крыніцы/БелЭн|2|Асаковыя|Скуратовіч А.}}",
        replacements=1,
        used_line_rules=[],
        used_rule_names=["template_citation"],
        rendered_templates=["{{Крыніцы/БелЭн|2|Асаковыя|Скуратовіч А.}}"],
        page_arguments=[],
        entry_arguments=["Асаковыя"],
        extra_argument_values={"author": ["Скуратовіч А."]},
        review_reasons=["Entry or author inferred from bibliography prefix before template citation; confirm manually."],
    )

    ui.print_diff_panel(
        title="Асаковыя",
        result=result,
        old_text="old",
        context=3,
    )

    output = stream.getvalue()
    assert "Decision" in output
    assert "manual review required" in output
    assert "Reason" in output
    assert "At least one value was inferred heuristically" in output
    assert "Manual reasons" in output
    assert "Inferred author" in output


def test_rich_diff_panel_emits_ansi_diff_colors():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=True,
        color_system="truecolor",
        width=100,
        no_color=False,
        highlight=False,
    )
    ui = AppUI(no_color=False, console=console)
    result = ReplacementResult(
        text="new\n{{Крыніцы/ГВБ|1-1||213}}",
        replacements=1,
        used_line_rules=[],
        rendered_templates=["{{Крыніцы/ГВБ|1-1||213}}"],
        page_arguments=["213"],
    )

    ui.print_diff_panel(
        title="Тэставая старонка",
        result=result,
        old_text="old",
        context=1,
    )

    output = stream.getvalue()
    assert "\x1b[" in output
    assert "\x1b[31m-old" in output
    assert "\x1b[32m+new" in output
    assert "\x1b[1;36m@@ -1 +1,2 @@" in output
    assert "\x1b[1;33m213\x1b[0m" in output


def test_unknown_variant_preview_shows_context_and_example_diff(repo_root):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    spec = load_source_spec("gvb4", root=repo_root)

    from biblio.models import VariantInfo

    source_excerpt = (
        'Ручаёўка<ref name="энцык">'
        "* Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118."
        "</ref> is a village."
    )
    matched = "* Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118."

    ui.print_unknown_variant(
        "Тэставая старонка",
        VariantInfo(
            full_line=matched,
            review_line="Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118.",
            normalized_line="Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118.",
            pages="118",
            entry="Асмолавічы",
            source_excerpt=source_excerpt,
            excerpt_match_start=source_excerpt.index(matched),
            excerpt_match_end=source_excerpt.index(matched) + len(matched),
        ),
        spec,
    )

    output = stream.getvalue()
    assert "Unknown candidate variant" in output
    assert "Source excerpt" in output
    assert "Example diff" in output
    assert 'Ручаёўка<ref name="энцык">' in output
    assert "</ref> is a village." in output
    assert '-Ручаёўка<ref name="энцык">* Асмолавічы' in output
    assert '+Ручаёўка<ref name="энцык">{{Крыніцы/ГВБ|4-2|Асмолавічы|118}}</ref>' in output


def test_unknown_variant_preview_emits_ansi_diff_colors(repo_root):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=True,
        color_system="truecolor",
        width=120,
        no_color=False,
        highlight=False,
    )
    ui = AppUI(no_color=False, console=console)
    spec = load_source_spec("gvb4", root=repo_root)

    from biblio.models import VariantInfo

    source_excerpt = (
        'Ручаёўка<ref name="энцык">'
        "* Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118."
        "</ref> is a village."
    )
    matched = "* Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118."

    ui.print_unknown_variant(
        "Тэставая старонка",
        VariantInfo(
            full_line=matched,
            review_line="Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118.",
            normalized_line="Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ... — С. 118.",
            pages="118",
            entry="Асмолавічы",
            source_excerpt=source_excerpt,
            excerpt_match_start=source_excerpt.index(matched),
            excerpt_match_end=source_excerpt.index(matched) + len(matched),
        ),
        spec,
    )

    output = stream.getvalue()
    assert "\x1b[" in output
    assert "\x1b[31m-" in output
    assert '<ref name="энцык">' in output
    assert "\x1b[32m+" in output
    assert "{{Крыніцы/ГВБ|4-2|Асмолавічы|118}}" in output
    assert "\x1b[1;33m* Асмолавічы // Гарады і вёскі Беларусі" in output


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
            failed=1,
            errors=1,
            retry_events=3,
            learned=1,
            ignored=2,
            failed_titles=["Broken page"],
        )
    )

    output = stream.getvalue()
    assert "Run summary" in output
    assert "Processed" in output
    assert "10" in output
    assert "Failed" in output
    assert "Retry attempts" in output
    assert "Failed pages" in output
    assert "Broken page" in output


def test_bulk_status_panel_snapshot():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=100,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    ui.print(
        ui.build_bulk_status_panel(
            BulkRunStatus(
                source_label="belen13 (БелЭн 13) [1/1]",
                total_pages=114,
                current_index=15,
                current_title="Краязнаўства Беларусі",
                phase="save",
                detail="Publishing edit to the wiki",
                phase_elapsed=6.2,
                processed=15,
                matched=12,
                saved=11,
                skipped=3,
                failed=1,
                retries=2,
            )
        )
    )

    output = stream.getvalue()
    assert "Bulk apply status" in output
    assert "belen13 (БелЭн 13) [1/1]" in output
    assert "15/114" in output
    assert "Краязнаўства Беларусі" in output
    assert "save (6.20s)" in output
    assert "Publishing edit to the wiki" in output
    assert "Failed" in output
    assert "Retries" in output


def test_bulk_status_prints_plain_status_lines():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=100,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    status = BulkRunStatus(
        source_label="demo (Demo) [1/1]",
        total_pages=5,
        current_index=2,
        current_title="Page title",
        phase="save",
        detail="Publishing edit to the wiki",
        processed=2,
        matched=2,
        saved=1,
        skipped=0,
        failed=0,
        retries=1,
    )

    ui.begin_bulk_run(status)
    ui.update_bulk_status(status)
    ui.update_bulk_status(replace(status, phase="retry", detail="Retrying save in 2.00s"))

    output = stream.getvalue()
    normalized_output = " ".join(output.split())
    assert output.count("[bulk-status]") == 2
    assert "| 2/5 | save | Page title | Publishing edit to the wiki |" in normalized_output
    assert "| 2/5 | retry | Page title | Retrying save in 2.00s |" in normalized_output


def test_prompt_csv_without_default_does_not_pass_empty_default(monkeypatch):
    captured = {}

    def fake_ask(label, **kwargs):
        captured["label"] = label
        captured["kwargs"] = kwargs
        return "term 1, term 2"

    monkeypatch.setattr("biblio.ui.Prompt.ask", fake_ask)
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
    assert "learned or edited" in output
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

    assert (
        ui.prompt_choice(
            "Choose variant action [r=review, i=ignore, s=skip]",
            choices=["r", "i", "s"],
            default="s",
        )
        == "r"
    )

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


def test_build_checklist_panel_shows_literal_checkbox_markers():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=100,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)

    ui.print(
        ui.build_checklist_panel(
            "Select sources",
            [
                ChecklistOption("gvb1", "gvb1", "First source"),
                ChecklistOption("gvb2", "gvb2", "Second source"),
            ],
            selected={"gvb2"},
            cursor=1,
        )
    )

    output = stream.getvalue()
    assert "[ ]" in output
    assert "[x]" in output
    assert "Window" in output


def test_build_checklist_panel_adapts_to_terminal_height():
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=100,
        height=12,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    options = [ChecklistOption(f"src{i}", f"src{i}", f"Source {i}") for i in range(10)]

    ui.print(
        ui.build_checklist_panel(
            "Select sources",
            options,
            selected=set(),
            cursor=8,
        )
    )

    output = stream.getvalue()
    assert "src0" not in output
    assert "src4" in output
    assert "src8" in output
    assert "src9" in output
    assert "5-10 of 10" in output


def test_prompt_choice_falls_back_to_prompt_ask(monkeypatch):
    captured = {}
    ui = AppUI(no_color=True, console=Console(file=io.StringIO(), no_color=True))

    monkeypatch.setattr(ui, "_supports_single_key_input", lambda: False)

    def fake_ask(label, **kwargs):
        captured["label"] = label
        captured["kwargs"] = kwargs
        return "s"

    monkeypatch.setattr("biblio.ui.Prompt.ask", fake_ask)

    assert (
        ui.prompt_choice(
            "Choose variant action [r=review, i=ignore, s=skip]",
            choices=["r", "i", "s"],
            default="s",
        )
        == "s"
    )
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
    assert "save an exact rule to rules.json" in output
    assert labels == [
        "Choose variant action [r=review, e=edit, i=ignore, s=skip]",
        "Choose variant action [r=review, e=edit, i=ignore, s=skip]",
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
    assert "Save this page and all remaining safe pages." in output
    assert "Current edit summary: Summary 1" in output
    assert "Current edit summary: Summary 2" in output
    assert labels == [
        "Choose page action [y=save, n=skip, a=save all safe, e=edit summary, q=quit]",
        "Choose page action [y=save, n=skip, a=save all safe, e=edit summary, q=quit]",
    ]


def test_prompt_page_action_explains_review_required_bulk_behavior(monkeypatch):
    stream = io.StringIO()
    console = Console(
        file=stream,
        force_terminal=False,
        width=120,
        no_color=True,
        highlight=False,
    )
    ui = AppUI(no_color=True, console=console)
    monkeypatch.setattr(ui, "prompt_choice", lambda label, **kwargs: "n")

    assert ui.prompt_page_action("Summary 1", review_required=True) == "n"

    output = stream.getvalue()
    assert "Manual review is required for this change." in output
    assert "manual-review changes will still pause" in output


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
    assert "save an exact rule to rules.json" in output
    assert labels == [
        "Choose review action [r=learn exact, e=edit, i=ignore, s=skip]",
        "Choose review action [r=learn exact, e=edit, i=ignore, s=skip]",
    ]
