from __future__ import annotations

import textwrap

from biblio.engine import extract_unknown_variant_infos, is_candidate_line, replace_text
from biblio.specs import load_source_spec
from biblio.state import load_source_state
from biblio.text import make_review_key


def _write_temp_source(tmp_path, source_id: str, source_toml: str) -> None:
    source_dir = tmp_path / "sources" / source_id
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(source_toml.strip() + "\n", encoding="utf-8")
    source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("ignored_variants.json").write_text("[]", encoding="utf-8")


def _load_regex_demo_spec(tmp_path):
    _write_temp_source(
        tmp_path,
        "regexdemo",
        textwrap.dedent(
            r"""
            [source]
            id = "regexdemo"
            name = "Regex demo"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["Гомельская вобласць"]
            isbns = ["985-11-0303-9", "985-11-0302-0"]
            keywords = []

            [candidate]
            must_contain_all = ["Гомельская вобласць"]
            must_contain_any = ["985-11-0303-9", "985-11-0302-0"]

            [replacement]
            template_name = "Крыніцы/ГВБ"
            without_pages = "{{Крыніцы/ГВБ|1-1}}"
            with_pages = "{{Крыніцы/ГВБ|1-1||{pages}}}"

            [summary]
            default_format = "Замена бібліяграфічнай спасылкі шаблонам {{{template_name}}}"

            [pages]
            patterns = [
              "\\bс\\.{{OPT_WS}}(?P<pages>{{PAGES}})",
              "\\|{{OPT_WS}}(?:старонкі|pages?|pp?){{OPT_WS}}={{OPT_WS}}(?P<pages>{{PAGES}})(?={{OPT_WS}}(?:\\||\\}\\}))",
            ]
            reject_patterns = [
              "^\\s*:\\s*іл",
            ]

            [normalization]
            strip_nowiki = true
            resolve_wikilinks = true
            strip_formatting = true
            normalize_nbsp = true
            normalize_dashes = true
            collapse_whitespace = true

            [macros]
            TITLE = "Гарады і вёскі Беларусі"
            REGION = "Гомельская вобласць"
            ISBNS = "(?:985-11-0303-9|985-11-0302-0)"
            COMMON = "(?=.*{{TITLE}})(?=.*{{REGION}})(?=.*{{ISBNS}})"

            [[regex_rules]]
            name = "list_entry_trailing_pages"
            pattern = "^(?P<prefix>{{LIST_PREFIX}}){{COMMON}}.*?\\bс\\.{{OPT_WS}}(?P<pages>{{PAGES}})\\s*[;.]?$"
            replacement = "{prefix}{template}"
            flags = "IGNORECASE|UNICODE|MULTILINE"
            enabled = true

            [[regex_rules]]
            name = "leading_page_marker"
            pattern = "^(?P<prefix>{{LIST_PREFIX}})с\\.{{OPT_WS}}(?P<pages>{{PAGES}}){{SEP}}{{COMMON}}.*$"
            replacement = "{prefix}{template}"
            flags = "IGNORECASE|UNICODE|MULTILINE"
            enabled = true

            [[regex_rules]]
            name = "full_line_bibliography"
            pattern = "^(?P<prefix>{{LIST_PREFIX}})(?!.*\\|{{OPT_WS}}(?:старонкі|pages?|pp?){{OPT_WS}}=){{COMMON}}.*$"
            replacement = "{prefix}{template}"
            flags = "IGNORECASE|UNICODE|MULTILINE"
            enabled = true
            """
        ),
    )
    return load_source_spec("regexdemo", root=tmp_path)


def test_replace_exact_reference_variant(gvb_spec):
    text = (
        "Гарады і вёскі Беларусі: Энцыклапедыя. Т.1, кн.1. Гомельская вобласць/С. В. Марцэлеў; "
        "Рэдкалегія: Г. П. Пашкоў (галоўны рэдактар) і інш. — Мн.: БелЭн, 2004. "
        "632с.: іл. Тыраж 4000 экз. ISBN 985-11-0303-9 ISBN 985-11-0302-0"
    )
    result = replace_text(
        text,
        gvb_spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(text, gvb_spec),
                "replacement": "{{Крыніцы/ГВБ|1-1}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/ГВБ|1-1}}"


def test_replace_regex_list_reference_with_pages(tmp_path):
    spec = _load_regex_demo_spec(tmp_path)
    text = (
        "* Марцэлеў С. В., рэдкалегія: Пашкоў Г. П. (галоўны рэдактар) і інш., "
        "«Гарады і вёскі Беларусі: Энцыклапедыя», г. Мінск, БелЭн., 2004 г., "
        "ISBN 985-11-0303-9 ISBN 985-11-0302-0, Гомельская вобласць, Т. 1, кн. 1, "
        "с. 213—214;"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/ГВБ|1-1||213—214}}"
    assert result.page_arguments == ["213—214"]
    assert "list_entry_trailing_pages" in result.used_rule_names


def test_replace_leading_page_reference_with_pages(tmp_path):
    spec = _load_regex_demo_spec(tmp_path)
    text = (
        "* с. 253, Гарады і вёскі Беларусі: Энцыклапедыя. Т. 1, кн. 1. "
        "Гомельская вобласць / С. В. Марцэлеў; Рэдкалегія: Г. П. Пашкоў "
        "(галоўны рэдактар) і інш. — Мн.: БелЭн, 2004. 632 с.: іл. "
        "Тыраж 4000 экз. ISBN 985-11-0303-9 ISBN 985-11-0302-0"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/ГВБ|1-1||253}}"
    assert "leading_page_marker" in result.used_rule_names


def test_full_line_rule_matches_broader_variant(tmp_path):
    spec = _load_regex_demo_spec(tmp_path)
    text = (
        "[[Гарады і вёскі Беларусі]]: Энцыклапедыя. Т. 1, кн. 1. "
        "[[Гомельская вобласць]] / [[Станіслаў Віктаравіч Марцэлеў|С. В. Марцэлеў]]; "
        "Рэдкалегія: [[Генадзь Пятровіч Пашкоў|Г. П. Пашкоў]] (галоўны рэдактар) і інш. "
        "— Мінск: [[Беларуская энцыклапедыя|БелЭн]], 2004. 632 с.: іл. Тыраж 4000 экз. "
        "ISBN 985-11-0302-0"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/ГВБ|1-1}}"
    assert "full_line_bibliography" in result.used_rule_names


def test_replace_exact_rule_only_inside_ref_tags(gvb_spec):
    text = (
        'Ручаёўка<ref name="энцык">'
        "Гарады і вёскі Беларусі: Энцыклапедыя. Т.1, кн.1. Гомельская вобласць/С. В. Марцэлеў; "
        "Рэдкалегія: Г. П. Пашкоў (галоўны рэдактар) і інш. — Мн.: БелЭн, 2004. "
        "632с.: іл. Тыраж 4000 экз. ISBN 985-11-0303-9 ISBN 985-11-0302-0"
        "</ref> is a village."
    )
    body = (
        "Гарады і вёскі Беларусі: Энцыклапедыя. Т.1, кн.1. Гомельская вобласць/С. В. Марцэлеў; "
        "Рэдкалегія: Г. П. Пашкоў (галоўны рэдактар) і інш. — Мн.: БелЭн, 2004. "
        "632с.: іл. Тыраж 4000 экз. ISBN 985-11-0303-9 ISBN 985-11-0302-0"
    )
    result = replace_text(
        text,
        gvb_spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(body, gvb_spec),
                "replacement": "{{Крыніцы/ГВБ|1-1}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert (
        result.text
        == 'Ручаёўка<ref name="энцык">{{Крыніцы/ГВБ|1-1}}</ref> is a village.'
    )


def test_replace_line_exact_rule_uses_entry_and_pages_from_current_line(repo_root):
    spec = load_source_spec("gvb4", root=repo_root)
    body = (
        "Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ў 15 тамах. "
        "Т. 4, кн. 2. Брэсцкая вобласць / Рэдкалегія: Г. П. Пашкоў "
        "(галоўны рэдактар) і інш. — Мінск.: БелЭн, 2007. — 608 с.: іл. "
        "— С. 118. ISBN 978-985-11-0388-7."
    )
    result = replace_text(
        f"* {body}",
        spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(body, spec),
                "replacement": "{{Крыніцы/ГВБ|4-2}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/ГВБ|4-2|Асмолавічы|118}}"
    assert result.page_arguments == ["118"]
    assert result.entry_arguments == ["Асмолавічы"]


def test_extract_unknown_variant_template_with_url_keeps_pages_and_empty_entry(repo_root):
    spec = load_source_spec("gvb5", root=repo_root)
    text = (
        "* {{Кніга|ref=Гарады і вёскі Беларусі : Энцыклапедыя. Магілёўская вобласць."
        "|спасылка=https://archive.org/details/bel-enc-harvio/HVB.Mahilouskaja.1/page/n367/mode/2up?view=theater "
        "|загаловак=Гарады і вёскі Беларусі : Энцыклапедыя. Магілёўская вобласць. "
        "|адказны=Пад навуковай рэдакцыяй А.І. Лакоткі |год=2008 |мова=be |месца=Мінск "
        "|выдавецтва=Беларуская Энцыклапедыя імя Петруся Броўкі |том=5 "
        "|старонкі=367–368 |старонак=728 |isbn=978-985-11-0409-9}}"
    )

    infos = extract_unknown_variant_infos(text, spec)

    assert len(infos) == 1
    assert infos[0].entry is None
    assert infos[0].pages == "367—368"
    assert spec.render_template(infos[0].pages, infos[0].entry) == "{{Крыніцы/ГВБ|5-1||367—368}}"


def test_replace_line_exact_rule_keeps_pages_and_empty_entry_for_template_without_part(repo_root):
    spec = load_source_spec("gvb5", root=repo_root)
    body = (
        "{{Кніга|ref=Гарады і вёскі Беларусі : Энцыклапедыя. Магілёўская вобласць."
        "|спасылка=https://archive.org/details/bel-enc-harvio/HVB.Mahilouskaja.1/page/n367/mode/2up?view=theater "
        "|загаловак=Гарады і вёскі Беларусі : Энцыклапедыя. Магілёўская вобласць. "
        "|адказны=Пад навуковай рэдакцыяй А.І. Лакоткі |год=2008 |мова=be |месца=Мінск "
        "|выдавецтва=Беларуская Энцыклапедыя імя Петруся Броўкі |том=5 "
        "|старонкі=367–368 |старонак=728 |isbn=978-985-11-0409-9}}"
    )

    result = replace_text(
        f"* {body}",
        spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(body, spec),
                "replacement": "{{Крыніцы/ГВБ|5-1}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/ГВБ|5-1||367—368}}"
    assert result.page_arguments == ["367—368"]
    assert result.entry_arguments == []


def test_replace_line_exact_rule_does_not_infer_entry_from_bibliography_title(repo_root):
    spec = load_source_spec("gvb9", root=repo_root)
    body = (
        "Гарады і вёскі Беларусі: Энцыклапедыя. Т.8, кн.2. Мінская вобласць "
        "// Рэдкалегія: Т. У. Бялова (дырэктар) і інш. — Мн.: БелЭн, 2011. "
        "— 464 с.: іл. ISBN 978-985-11-0554-6"
    )

    result = replace_text(
        f"* {body}",
        spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(body, spec),
                "replacement": "{{Крыніцы/ГВБ|8-2}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/ГВБ|8-2}}"
    assert result.entry_arguments == []


def test_replace_regex_rule_only_inside_ref_tags(tmp_path):
    spec = _load_regex_demo_spec(tmp_path)
    text = (
        'Ручаёўка<ref name="энцык">'
        "Гарады і вёскі Беларусі: Энцыклапедыя. Т. 1, кн. 1. "
        "Гомельская вобласць / С. В. Марцэлеў; Рэдкалегія: Г. П. Пашкоў "
        "(галоўны рэдактар) і інш. — Мн.: БелЭн, 2004. 632 с.: іл. "
        "Тыраж 4000 экз. ISBN 985-11-0302-0"
        "</ref> is a village."
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert (
        result.text
        == 'Ручаёўка<ref name="энцык">{{Крыніцы/ГВБ|1-1}}</ref> is a village.'
    )
    assert "full_line_bibliography" in result.used_rule_names


def test_full_line_rule_does_not_drop_template_param_pages(tmp_path):
    spec = _load_regex_demo_spec(tmp_path)
    text = (
        "{{кніга|загаловак = Гарады і вёскі Беларусі: Энцыклапедыя. Т. 1, кн. 1. "
        "Гомельская вобласць|аўтар = С. В. Марцэлеў|адказны = Г. П. Пашкоў|"
        "выдавецтва = БелЭн|старонкі = 67—68|isbn = ISBN 985-11-0302-0}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 0


def test_extract_unknown_variants_uses_ref_body_not_whole_line(tmp_path):
    source_dir = tmp_path / "sources" / "tmpref"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "tmpref"
            name = "Temporary ref candidate"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["Гарады і вёскі Беларусі"]
            isbns = ["985-11-0330-6"]
            keywords = []

            [candidate]
            must_contain_all = ["Гарады і вёскі Беларусі"]
            must_contain_any = ["985-11-0330-6"]

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
    source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("ignored_variants.json").write_text("[]", encoding="utf-8")

    spec = load_source_spec("tmpref", root=tmp_path)
    infos = extract_unknown_variant_infos(
        'Ручаёўка<ref name="энцык">{{кніга|загаловак=Гарады і вёскі Беларусі|isbn=985-11-0330-6}}</ref> is a village.',
        spec,
    )

    assert len(infos) == 1
    assert infos[0].full_line == "{{кніга|загаловак=Гарады і вёскі Беларусі|isbn=985-11-0330-6}}"
    assert "<ref" not in infos[0].review_line
    assert "Ручаёўка" not in infos[0].review_line


def test_extract_unknown_variants_ignores_self_closing_refs_before_target_ref(tmp_path):
    source_dir = tmp_path / "sources" / "tmpref2"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "tmpref2"
            name = "Temporary ref candidate"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["Гарады і вёскі Беларусі"]
            isbns = ["985-11-0330-6"]
            keywords = []

            [candidate]
            must_contain_all = ["Гарады і вёскі Беларусі"]
            must_contain_any = ["985-11-0330-6"]

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
    source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("ignored_variants.json").write_text("[]", encoding="utf-8")

    spec = load_source_spec("tmpref2", root=tmp_path)
    infos = extract_unknown_variant_infos(
        'Intro<ref name="one" /><ref name="two" />'
        '<ref name="ГВБ">{{кніга|загаловак=Гарады і вёскі Беларусі|isbn=985-11-0330-6}}</ref>'
        ' tail',
        spec,
    )

    assert len(infos) == 1
    assert infos[0].full_line == "{{кніга|загаловак=Гарады і вёскі Беларусі|isbn=985-11-0330-6}}"
    assert "Intro" not in infos[0].review_line
    assert "<ref" not in infos[0].review_line


def test_extract_unknown_variants_use_full_multiline_template_block(repo_root):
    spec = load_source_spec("gvb7", root=repo_root)
    text = (
        "* {{кніга\n"
        " | частка         = Юзяфоўка\n"
        " | загаловак      = Гарады і вёскі Беларусі: Энцыклапедыя. Т. 7, кн. 3. Магілёўская вобласць\n"
        " | адказны        = рэдкал.: Т. У. Бялова (дырэктар) [і інш.]\n"
        " | месца          = Мн.\n"
        " | выдавецтва     = Беларуская Энцыклапедыя імя Петруся Броўкі\n"
        " | год            = 2009\n"
        " | isbn           = 978-985-11-0452-5\n"
        "}}\n"
    )

    infos = extract_unknown_variant_infos(text, spec)

    assert len(infos) == 1
    assert "| частка         = Юзяфоўка" in infos[0].review_line
    assert infos[0].entry == "Юзяфоўка"
    assert infos[0].pages is None


def test_replace_line_exact_rule_replaces_full_multiline_template_block(repo_root):
    spec = load_source_spec("gvb7", root=repo_root)
    body = (
        "{{кніга\n"
        " | частка         = Юзяфоўка\n"
        " | загаловак      = Гарады і вёскі Беларусі: Энцыклапедыя. Т. 7, кн. 3. Магілёўская вобласць\n"
        " | адказны        = рэдкал.: Т. У. Бялова (дырэктар) [і інш.]\n"
        " | месца          = Мн.\n"
        " | выдавецтва     = Беларуская Энцыклапедыя імя Петруся Броўкі\n"
        " | год            = 2009\n"
        " | isbn           = 978-985-11-0452-5\n"
        "}}"
    )

    result = replace_text(
        f"* {body}\n",
        spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(body, spec),
                "replacement": "{{Крыніцы/ГВБ|7-3}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/ГВБ|7-3|Юзяфоўка}}\n"
    assert result.entry_arguments == ["Юзяфоўка"]


def test_replace_belen10_bibliography_line_with_author_and_responsible(repo_root):
    spec = load_source_spec("belen10", root=repo_root)
    text = (
        "* Шаблюк В. У. Маркава / В. У. Шаблюк // Беларуская энцыклапедыя: У 18 т. "
        "Т. 10: Малайзія — Мугаджары / Рэдкал.: Г. П. Пашкоў і інш. — Мн. : БелЭн, 2000. "
        "— Т. 10. — С. 114. — 544 с. — 10 000 экз. — ISBN 985-11-0035-8. "
        "— ISBN 985-11-0169-9 (т. 10)."
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/БелЭн|10|Маркава|Шаблюк В. У.|114|В. У. Шаблюк}}"
    assert result.entry_arguments == ["Маркава"]
    assert result.page_arguments == ["114"]
    assert result.extra_argument_values == {
        "author": ["Шаблюк В. У."],
        "responsible": ["В. У. Шаблюк"],
    }


def test_replace_belen10_template_citation_with_explicit_params(repo_root):
    spec = load_source_spec("belen10", root=repo_root)
    text = (
        "{{кніга|частка=Маркава|аўтар=Шаблюк В. У.|частка адказны=В. У. Шаблюк|"
        "загаловак=Беларуская энцыклапедыя: У 18 т. Т. 10: Малайзія — Мугаджары|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2000|"
        "том=10|старонкі=114|старонак=544|isbn=985-11-0169-9}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/БелЭн|10|Маркава|Шаблюк В. У.|114|В. У. Шаблюк}}"
    assert result.entry_arguments == ["Маркава"]
    assert result.page_arguments == ["114"]
    assert result.extra_argument_values == {
        "author": ["Шаблюк В. У."],
        "responsible": ["В. У. Шаблюк"],
    }


def test_replace_belen1_wikilinked_entry_only_line(repo_root):
    spec = load_source_spec("belen1", root=repo_root)
    text = (
        "Агол Іосіф (Ізраіль) Іосіфавіч // [[Беларуская энцыклапедыя]]: У 18 т. "
        "Т. 1: А — Аршын / Рэдкал.: [[Генадзь Пятровіч Пашкоў|Г. П. Пашкоў]] і інш. "
        "— Мн. : [[Беларуская Энцыклапедыя імя Петруся Броўкі|БелЭн]], 1996. "
        "— Т. 1. — 552 с. — 10 000 экз. — ISBN 985-11-0035-8. "
        "— ISBN 985-11-0036-6 (т. 1)."
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/БелЭн|1|Агол Іосіф (Ізраіль) Іосіфавіч}}"
    assert result.entry_arguments == ["Агол Іосіф (Ізраіль) Іосіфавіч"]
    assert result.extra_argument_values == {}


def test_replace_belen11_template_citation_with_pages_only(repo_root):
    spec = load_source_spec("belen11", root=repo_root)
    text = (
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т.11: Мугір — Паліклініка|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2000|"
        "том=11|старонкі=374|старонак=560|isbn=985-11-0188-5 (Т.&nbsp;11)|тыраж=10&nbsp;000}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/БелЭн|11|||374}}"
    assert result.entry_arguments == []
    assert result.page_arguments == ["374"]


def test_replace_belen13_template_citation_with_entry_inside_title(repo_root):
    spec = load_source_spec("belen13", root=repo_root)
    text = (
        "{{кніга|загаловак=Рагоўскае возера // Беларуская энцыклапедыя: У 18 т. "
        "Т. 13: Праміле — Рэлаксін|адказны=Рэдкал.: Г. П. Пашкоў і інш|"
        "месца=Мн.|выдавецтва=БелЭн|год=2001|том=13|старонкі=202|"
        "старонак=576|isbn=985-11-0216-4 (Т. 13)|тыраж=10 000}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/БелЭн|13|Рагоўскае возера||202}}"
    assert result.entry_arguments == ["Рагоўскае возера"]
    assert result.page_arguments == ["202"]


def test_replace_belen18_1_template_citation_with_plain_tom_param(repo_root):
    spec = load_source_spec("belen18-1", root=repo_root)
    text = (
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т.18 Кн.1: Дадатак: "
        "Шчытнікі — ЯЯ|адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|"
        "выдавецтва=БелЭн|год=2004|том=18|старонкі=344|старонак=472|"
        "isbn=985-11-0295-4 (Т. 18 Кн. 1)|тыраж=10&nbsp;000}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/БелЭн|18-1|||344}}"
    assert result.entry_arguments == []
    assert result.page_arguments == ["344"]


def test_replace_belen18_1_template_citation_with_dotted_volume_title(repo_root):
    spec = load_source_spec("belen18-1", root=repo_root)
    text = (
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т. 18. Кн. 1.: Дадатак: "
        "Шчытнікі — ЯЯ|адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|"
        "выдавецтва=БелЭн|год=2004|том=18|старонкі=148|старонак=472|"
        "isbn=985-11-0295-4 (Т. 18. Кн. 1.)|тыраж=10&nbsp;000}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/БелЭн|18-1|||148}}"
    assert result.entry_arguments == []
    assert result.page_arguments == ["148"]


def test_line_exact_rule_takes_precedence_over_review_required_belen_regex(repo_root):
    spec = load_source_spec("belen1", root=repo_root)
    body = (
        "Агол Іосіф (Ізраіль) Іосіфавіч // [[Беларуская энцыклапедыя]]: У 18 т. "
        "Т. 1: А — Аршын / Рэдкал.: [[Генадзь Пятровіч Пашкоў|Г. П. Пашкоў]] і інш. "
        "— Мн. : [[Беларуская Энцыклапедыя імя Петруся Броўкі|БелЭн]], 1996. "
        "— Т. 1. — 552 с. — 10 000 экз. — ISBN 985-11-0035-8. "
        "— ISBN 985-11-0036-6 (т. 1)."
    )

    result = replace_text(
        f"* {body}",
        spec,
        [
            {
                "kind": "line_exact",
                "match": make_review_key(body, spec),
                "replacement": "{{Крыніцы/БелЭн|1|Агол Іосіф (Ізраіль) Іосіфавіч}}",
                "enabled": True,
            }
        ],
    )

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/БелЭн|1|Агол Іосіф (Ізраіль) Іосіфавіч}}"
    assert result.used_rule_names == ["line_exact"]
    assert result.review_reasons == []


def test_extract_unknown_belen16_variant_separates_author_entry_and_responsible(repo_root):
    spec = load_source_spec("belen16", root=repo_root)
    text = (
        "* Ярмоленка, В. А. Фялінская Ева Зыгмунтаўна / В. А. Ярмоленка // "
        "Беларуская энцыклапедыя: У 18 т. / Беларуская энцыклапедыя; "
        "Рэдкал.: Г. П. Пашкоў (гал. рэд.) [і інш.]. Т. 16: Трыпалі — Хвіліна. "
        "— Мн.: «Беларуская энцыклапедыя», 2003. — 576 с.: іл. — С. 512."
    )

    infos = extract_unknown_variant_infos(text, spec)

    assert len(infos) == 1
    assert infos[0].entry == "Фялінская Ева Зыгмунтаўна"
    assert infos[0].pages == "512"
    assert infos[0].extra_arguments == {
        "author": "Ярмоленка, В. А.",
        "responsible": "В. А. Ярмоленка",
    }
    assert (
        spec.render_template(infos[0].pages, infos[0].entry, **infos[0].extra_arguments)
        == "{{Крыніцы/БелЭн|16|Фялінская Ева Зыгмунтаўна|Ярмоленка, В. А.|512|В. А. Ярмоленка}}"
    )


def test_extract_unknown_belen17_variant_strips_author_from_entry(repo_root):
    spec = load_source_spec("belen17", root=repo_root)
    text = (
        "* Касцюковіч М. Шарпак // {{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. "
        "Т. 17: Хвінявічы — Шчытні|адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|"
        "выдавецтва=БелЭн|год=2003|том=17|старонак=512|isbn=985-11-0279-2}}"
    )

    infos = extract_unknown_variant_infos(text, spec)

    assert len(infos) == 1
    assert infos[0].entry == "Шарпак"
    assert infos[0].extra_arguments == {
        "author": "Касцюковіч М.",
    }


def test_belen15_template_prefix_with_author_list_requires_review(repo_root):
    spec = load_source_spec("belen15", root=repo_root)
    text = (
        "* 'Вештарт І. Ф., Цярохін С. Ф.' Сыта // "
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т.15: Следавікі — Трыо|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2002|"
        "том=15|старонкі=324|старонак=552|isbn=985-11-0251-2 (Т. 15)|тыраж=10&nbsp;000}}"
    )

    result = replace_text(text, spec, [])

    assert result.replacements == 1
    assert result.text == "* {{Крыніцы/БелЭн|15|Сыта|Вештарт І. Ф., Цярохін С. Ф.|324}}"
    assert result.entry_arguments == ["Сыта"]
    assert result.extra_argument_values == {
        "author": ["Вештарт І. Ф., Цярохін С. Ф."],
    }
    assert result.review_reasons == [
        "Entry or author inferred from bibliography prefix before template citation; confirm manually."
    ]


def test_replace_belen8_candidate_with_page_title_matched_entry(repo_root):
    spec = load_source_spec("belen8", root=repo_root)
    text = (
        "* Трусаў, А. А., Угрыновіч, У. В. Кафля / А. А. Трусаў, У. В. Угрыновіч // "
        "Беларуская энцыклапедыя: У 18 т. / Беларуская Энцыклапедыя; "
        "рэдкалэ: Г. П. Пашкоў (гал. рэд.) [і інш.]. Т. 8: Канто — Кулі. "
        "— Мн.: БелЭн, 1999. — 572 с.: іл. — С. 188 — 189. — ISBN 985-11-0144-3."
    )

    result = replace_text(text, spec, [], page_title="Кафля")

    assert result.replacements == 1
    assert (
        result.text
        == "* {{Крыніцы/БелЭн|8|Кафля|Трусаў, А. А., Угрыновіч, У. В.|188—189|А. А. Трусаў, У. В. Угрыновіч}}"
    )
    assert result.used_rule_names == ["page_title_candidate"]
    assert result.entry_arguments == ["Кафля"]
    assert result.page_arguments == ["188—189"]
    assert result.extra_argument_values == {
        "author": ["Трусаў, А. А., Угрыновіч, У. В."],
        "responsible": ["А. А. Трусаў, У. В. Угрыновіч"],
    }
    assert result.review_reasons == []


def test_review_variants_promote_to_active_rules(tmp_path, repo_root):
    source_dir = tmp_path / "sources" / "tmpdemo"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "tmpdemo"
            name = "Temporary demo"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["ISBN 1"]
            isbns = []
            keywords = ["Кніга"]

            [candidate]
            must_contain_all = ["Кніга"]
            must_contain_any = ["ISBN 1"]

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
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text(
        '["Кніга. ISBN 1, с. 42"]',
        encoding="utf-8",
    )

    spec = load_source_spec("tmpdemo", root=tmp_path)
    state = load_source_state(spec)
    result = replace_text("Кніга. ISBN 1, с. 42", spec, state.active_rules)

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/Тэст||42}}"


def test_line_exact_rule_uses_stored_replacement_verbatim(tmp_path):
    _write_temp_source(
        tmp_path,
        "exactdemo",
        textwrap.dedent(
            """
            [source]
            id = "exactdemo"
            name = "Exact demo"
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
            without_pages = "{{Крыніцы/Тэст|{entry}}}"
            with_pages = "{{Крыніцы/Тэст|{entry}|{pages}}}"

            [summary]
            default_format = "Замена {{{template_name}}}"

            [pages]
            patterns = []
            reject_patterns = []

            [normalization]

            [macros]
            """
        ),
    )
    source_dir = tmp_path / "sources" / "exactdemo"
    source_dir.joinpath("rules.json").write_text(
        """
        [
          {
            "kind": "line_exact",
            "match": "Новае",
            "replacement": "{{Крыніцы/Тэст|Старое}}",
            "enabled": true
          }
        ]
        """.strip(),
        encoding="utf-8",
    )

    spec = load_source_spec("exactdemo", root=tmp_path)
    state = load_source_state(spec)
    result = replace_text("Новае", spec, state.active_rules)

    assert result.replacements == 1
    assert result.text == "{{Крыніцы/Тэст|Старое}}"


def test_missing_ignored_variants_defaults_to_empty(tmp_path):
    source_dir = tmp_path / "sources" / "tmpignored"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "tmpignored"
            name = "Temporary ignored"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["ISBN 1"]
            isbns = []
            keywords = []

            [candidate]
            must_contain_all = []
            must_contain_any = ["ISBN 1"]

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
    source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")

    spec = load_source_spec("tmpignored", root=tmp_path)
    state = load_source_state(spec)

    assert state.ignored_hashes == set()


def test_candidate_detection_uses_candidate_terms_not_search_terms(tmp_path):
    source_dir = tmp_path / "sources" / "tmpcandidate"
    source_dir.mkdir(parents=True)
    source_dir.joinpath("source.toml").write_text(
        textwrap.dedent(
            """
            [source]
            id = "tmpcandidate"
            name = "Temporary candidate"
            site_lang = "be"
            family = "wikipedia"

            [search]
            insource_terms = ["Rare Search Term"]
            isbns = ["ISBN 1"]
            keywords = ["Keyword"]

            [candidate]
            must_contain_all = ["Кніга"]
            must_contain_any = ["ISBN 1"]

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
    source_dir.joinpath("rules.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("review_variants.json").write_text("[]", encoding="utf-8")
    source_dir.joinpath("ignored_variants.json").write_text("[]", encoding="utf-8")

    spec = load_source_spec("tmpcandidate", root=tmp_path)

    assert is_candidate_line("Кніга. ISBN 1", spec)
    assert not is_candidate_line("Rare Search Term only", spec)
