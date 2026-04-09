from __future__ import annotations

import textwrap

import pytest

from biblio.cli import main
from biblio.manage import guess_candidate_defaults


def _write_source_tree(root, source_id, *, include_readme=True, include_rules=True):
    source_dir = root / "sources" / source_id
    source_dir.mkdir(parents=True)
    source_toml = textwrap.dedent(
        """
        [source]
        id = "__SOURCE_ID__"
        name = "Temporary source"
        site_lang = "be"
        family = "wikipedia"

        [search]
        insource_terms = ["ISBN 1"]
        isbns = []
        keywords = []

        [candidate]
        must_contain_all = ["ISBN 1"]
        must_contain_any = []

        [replacement]
        template_name = "Крыніцы/Тэст"
        without_pages = "__WITHOUT__"
        with_pages = "__WITH__"

        [summary]
        default_format = "__SUMMARY__"

        [pages]
        patterns = []
        reject_patterns = []

        [normalization]

        [macros]
        """
    ).replace("__SOURCE_ID__", source_id).replace(
        "__WITHOUT__",
        "{{Крыніцы/Тэст}}",
    ).replace(
        "__WITH__",
        "{{Крыніцы/Тэст||{pages}}}",
    ).replace("__SUMMARY__", "Замена {{{template_name}}}")
    source_dir.joinpath("source.toml").write_text(
        source_toml.strip() + "\n",
        encoding="utf-8",
    )
    if include_rules:
        source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
        source_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")
        source_dir.joinpath("ignored_variants.json").write_text("[]", encoding="utf-8")
    if include_readme:
        source_dir.joinpath("README.md").write_text("# Temporary source\n", encoding="utf-8")
    return source_dir


def test_cli_registers_source_management_commands(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    output = capsys.readouterr().out

    assert "add-source" in output
    assert "validate" in output


def test_validate_reports_missing_canonical_files(monkeypatch, tmp_path, capsys):
    _write_source_tree(tmp_path, "valid-source", include_readme=False, include_rules=False)
    broken_dir = tmp_path / "sources" / "broken-source"
    broken_dir.mkdir(parents=True)
    broken_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "broken-source"
            name = "Broken source"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["ISBN 1"]
            isbns = []
            keywords = []

            [candidate]
            must_contain_all = ["ISBN 1"]
            must_contain_any = []

            [replacement]
            template_name = "Крыніцы/Тэст"
            without_pages = "{{Крыніцы/Тэст}}"
            with_pages = "{{Крыніцы/Тэст||{pages}}}"

            [summary]
            default_format = "Замена {{{template_name}}}"

            [pages]
            patterns = []
            reject_patterns = []

            [normalization]

            [macros]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    broken_dir.joinpath("rules.JSON").write_text("[]", encoding="utf-8")
    broken_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")
    broken_dir.joinpath("ignored_variants.json").write_text("[]", encoding="utf-8")
    broken_dir.joinpath("readme.md").write_text("# wrong case\n", encoding="utf-8")

    monkeypatch.setattr("biblio.specs.project_root", lambda: tmp_path)
    monkeypatch.setattr("biblio.runner.project_root", lambda: tmp_path)
    monkeypatch.setattr("biblio.manage.project_root", lambda: tmp_path)

    exit_code = main(["validate", "--no-color"])
    output = capsys.readouterr().out

    assert exit_code != 0
    assert "broken-source" in output
    assert "README.md" in output
    assert "readme.md" in output


def test_validate_accepts_canonical_layout(monkeypatch, tmp_path, capsys):
    _write_source_tree(tmp_path, "canonical-source", include_rules=False)

    monkeypatch.setattr("biblio.specs.project_root", lambda: tmp_path)
    monkeypatch.setattr("biblio.runner.project_root", lambda: tmp_path)
    monkeypatch.setattr("biblio.manage.project_root", lambda: tmp_path)

    exit_code = main(["validate", "--no-color"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "canonical-source" in output
    assert "OK" in output or "valid" in output.lower()


def test_add_source_creates_definition_and_runtime_files(monkeypatch, tmp_path):
    responses = iter(
        [
            "Example source",
            "example-source",
            "be",
            "wikipedia",
            "Крыніцы/Прыклад",
            "{{Крыніцы/Прыклад}}",
            "{{Крыніцы/Прыклад||{pages}}}",
            "Замена бібліяграфічнай спасылкі шаблонам {{{template_name}}}",
            "Example term",
            "ISBN 1, ISBN 2",
            "Example keyword",
            "Example keyword",
            "ISBN 1, ISBN 2",
            "This source targets example bibliography references on be.wikipedia.org.",
        ]
    )
    csv_defaults = {}

    monkeypatch.setattr("biblio.manage.project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "biblio.ui.AppUI.prompt_text",
        lambda self, label, default=None: next(responses),
    )
    def fake_prompt_csv(self, label, default=None):
        csv_defaults[label] = default
        return tuple(item.strip() for item in next(responses).split(",") if item.strip())

    monkeypatch.setattr("biblio.ui.AppUI.prompt_csv", fake_prompt_csv)
    monkeypatch.setattr("biblio.ui.AppUI.confirm", lambda self, label, default=True: True)

    exit_code = main(["add-source", "--no-color"])

    source_dir = tmp_path / "sources" / "example-source"
    assert exit_code == 0
    assert csv_defaults["Insource terms (comma-separated)"] is None
    assert csv_defaults["ISBNs (comma-separated)"] is None
    assert csv_defaults["Keywords (comma-separated)"] is None
    assert csv_defaults["Candidate must contain all (comma-separated)"] == ("Example keyword",)
    assert csv_defaults["Candidate must contain any (comma-separated)"] == (
        "ISBN 1",
        "ISBN 2",
        "Example term",
    )
    assert source_dir.joinpath("source.toml").exists()
    assert source_dir.joinpath("README.md").exists()
    assert source_dir.joinpath("rules.json").read_text(encoding="utf-8") == "[]\n"
    assert source_dir.joinpath("review_variants.json").read_text(encoding="utf-8") == "[]\n"
    assert source_dir.joinpath("ignored_variants.json").read_text(encoding="utf-8") == "[]\n"


def test_guess_candidate_defaults_prefers_text_for_all_and_isbns_for_any():
    candidate_all, candidate_any = guess_candidate_defaults(
        insource_terms=("Гомельская вобласць",),
        isbns=("985-11-0303-9", "985-11-0302-0"),
        keywords=(),
    )

    assert candidate_all == ("Гомельская вобласць",)
    assert candidate_any == ("985-11-0303-9", "985-11-0302-0")
