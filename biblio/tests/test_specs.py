from __future__ import annotations

import textwrap

import pytest
from biblio.query import build_search_query
from biblio.specs import discover_source_specs, load_source_spec


def _write_source(tmp_path, source_id: str, source_toml: str) -> None:
    source_dir = tmp_path / "sources" / source_id
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        source_toml.strip() + "\n",
        encoding="utf-8",
    )


def test_load_gvb1_spec(repo_root):
    spec = load_source_spec("gvb1", root=repo_root)

    assert spec.source_id == "gvb1"
    assert spec.site_lang == "be"
    assert spec.family == "wikipedia"
    assert spec.template_name == "Крыніцы/ГВБ"
    assert spec.render_template() == "{{Крыніцы/ГВБ|1-1}}"
    assert spec.render_template(entry="Абрамаўка") == "{{Крыніцы/ГВБ|1-1|Абрамаўка}}"
    assert spec.render_template("213—214") == "{{Крыніцы/ГВБ|1-1||213—214}}"
    assert spec.render_template("213—214", "Абрамаўка") == "{{Крыніцы/ГВБ|1-1|Абрамаўка|213—214}}"
    assert (
        spec.render_default_summary() == "Замена бібліяграфічнай спасылкі шаблонам {{Крыніцы/ГВБ}}"
    )
    assert spec.candidate.must_contain_all == ("Гомельская вобласць",)
    assert spec.candidate.must_contain_any == (
        "Т. 1, кн. 1. Гомельская вобласць",
        "985-11-0303-9",
        "985-11-0302-0",
    )
    assert not spec.regex_rules


def test_load_belen10_spec(repo_root):
    spec = load_source_spec("belen10", root=repo_root)

    assert spec.source_id == "belen10"
    assert spec.template_name == "Крыніцы/БелЭн"
    assert spec.render_template(entry="Маркава") == "{{Крыніцы/БелЭн|10|Маркава}}"
    assert (
        spec.render_template(
            entry="Маркава",
            author="Шаблюк В. У.",
            responsible="В. У. Шаблюк",
        )
        == "{{Крыніцы/БелЭн|10|Маркава|Шаблюк В. У.||В. У. Шаблюк}}"
    )
    assert (
        spec.render_template(
            "114",
            "Маркава",
            author="Шаблюк В. У.",
            responsible="В. У. Шаблюк",
        )
        == "{{Крыніцы/БелЭн|10|Маркава|Шаблюк В. У.|114|В. У. Шаблюк}}"
    )
    assert {extractor.name for extractor in spec.argument_extractors} == {"author", "responsible"}


def test_belen1_entry_only_rules_require_review(repo_root):
    spec = load_source_spec("belen1", root=repo_root)
    flagged = {
        rule.name: rule.review_required
        for rule in spec.regex_rules
        if rule.name in {"entry_only", "entry_only_with_pages"}
    }

    assert flagged == {
        "entry_only": True,
        "entry_only_with_pages": True,
    }


def test_build_query_uses_all_search_terms(gvb_spec):
    assert build_search_query(gvb_spec) == (
        'insource:"Гомельская вобласць" insource:"985-11-0303-9" insource:"985-11-0302-0"'
    )


def test_discover_source_specs(repo_root):
    ids = [spec.source_id for spec in discover_source_specs(root=repo_root)]
    assert "belen1" in ids
    assert "belen18-2" in ids
    assert "gvb1" in ids
    assert "gvb20" in ids
    assert "gvb" not in ids


def test_missing_candidate_section_raises(tmp_path):
    source_dir = tmp_path / "sources" / "broken"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "broken"
            name = "Broken"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["ISBN 1"]
            isbns = []
            keywords = []

            [replacement]
            template_name = "Крыніцы/Тэст"
            without_pages = "{{Крыніцы/Тэст}}"
            with_pages = "{{Крыніцы/Тэст||{pages}}}"

            [summary]
            default_format = "Замена {{{template_name}}}"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"\[candidate\]"):
        load_source_spec("broken", root=tmp_path)


def test_undefined_macro_raises(tmp_path):
    source_dir = tmp_path / "sources" / "undefined"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "undefined"
            name = "Undefined macro"
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
            patterns = ["\\\\bс\\\\.{{OPT_WS}}(?P<pages>{{PAGES}})"]
            reject_patterns = []

            [normalization]

            [macros]

            [[regex_rules]]
            name = "broken"
            pattern = "{{MISSING}}"
            replacement = "{template}"
            flags = "UNICODE"
            enabled = true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Undefined macro"):
        load_source_spec("undefined", root=tmp_path)


def test_macro_cycle_raises(tmp_path):
    source_dir = tmp_path / "sources" / "cycle"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "cycle"
            name = "Macro cycle"
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
            patterns = ["\\\\bс\\\\.{{OPT_WS}}(?P<pages>{{PAGES}})"]
            reject_patterns = []

            [normalization]

            [macros]
            A = "{{B}}"
            B = "{{A}}"

            [[regex_rules]]
            name = "broken"
            pattern = "{{A}}"
            replacement = "{template}"
            flags = "UNICODE"
            enabled = true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Macro cycle detected"):
        load_source_spec("cycle", root=tmp_path)


def test_reserved_macro_override_rejected(tmp_path):
    source_dir = tmp_path / "sources" / "reserved"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "reserved"
            name = "Reserved macro"
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
            patterns = ["\\\\bс\\\\.{{OPT_WS}}(?P<pages>{{PAGES}})"]
            reject_patterns = []

            [normalization]

            [macros]
            LIST_PREFIX = "bad"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="reserved"):
        load_source_spec("reserved", root=tmp_path)


def test_replacement_placeholder_validation_rejects_unknown_field(tmp_path):
    _write_source(
        tmp_path,
        "unknown-placeholder",
        """
        [source]
        id = "unknown-placeholder"
        name = "Unknown placeholder"
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
        without_pages = "{{Крыніцы/Тэст|{entry}|{bogus}}}"
        with_pages = "{{Крыніцы/Тэст|{entry}|{pages}}}"

        [summary]
        default_format = "Замена {{{template_name}}}"

        [pages]
        patterns = []
        reject_patterns = []

        [normalization]

        [macros]
        """,
    )

    with pytest.raises(ValueError, match="unknown placeholders"):
        load_source_spec("unknown-placeholder", root=tmp_path)


@pytest.mark.parametrize("field", ["enabled", "review_required"])
def test_regex_rule_boolean_flags_are_strict(tmp_path, field):
    bad_value = '"yes"' if field == "enabled" else "1"
    source_toml = (
        textwrap.dedent(
            """
        [source]
        id = "bad-boolean"
        name = "Bad boolean"
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

        [[regex_rules]]
        name = "broken"
        pattern = "ISBN"
        replacement = "__REPLACEMENT__"
        flags = "UNICODE"
        __FIELD__ = __BAD_VALUE__
        """
        )
        .replace("__WITHOUT__", "{{Крыніцы/Тэст|{entry}}}")
        .replace(
            "__WITH__",
            "{{Крыніцы/Тэст|{entry}|{pages}}}",
        )
        .replace("__SUMMARY__", "Замена {{{template_name}}}")
        .replace(
            "__REPLACEMENT__",
            "{prefix}{template}",
        )
        .replace("__FIELD__", field)
        .replace("__BAD_VALUE__", bad_value)
    )
    _write_source(
        tmp_path,
        "bad-boolean",
        source_toml,
    )

    with pytest.raises(ValueError, match=r"Expected a boolean"):
        load_source_spec("bad-boolean", root=tmp_path)
