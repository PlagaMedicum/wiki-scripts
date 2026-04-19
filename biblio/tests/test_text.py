from __future__ import annotations

import json

from biblio.specs import load_source_spec
from biblio.text import (
    extract_entry_arg,
    extract_pages_arg,
    extract_template_arguments,
    has_suspicious_page_value,
    normalize_biblio_wikitext,
    normalize_review_line,
    split_ref_aware_segments,
)


def test_normalize_review_line_resolves_markup(gvb_spec):
    line = (
        "[[Гарады і вёскі Беларусі]]: Энцыклапедыя. Т.1, кн.1. "
        "[[Гомельская вобласць]]/[[Станіслаў Віктаравіч Марцэлеў|С. В. Марцэлеў]]; "
        "Рэдкалегія: [[Генадзь Пятровіч Пашкоў|Г. П. Пашкоў]] "
        "(галоўны рэдактар) і інш. — Мн.: [[Беларуская энцыклапедыя|БелЭн]], 2004. "
        "632с.: іл. Тыраж 4000 экз. <nowiki>ISBN 985-11-0303-9</nowiki> "
        "<nowiki>ISBN 985-11-0302-0</nowiki>"
    )

    normalized = normalize_review_line(line, gvb_spec)

    assert "[[" not in normalized
    assert "nowiki" not in normalized
    assert "БелЭн" in normalized
    assert "Т. 1, кн. 1" in normalized


def test_extract_pages_arg_prefers_page_markers(gvb_spec):
    line = (
        "Марцэлеў С. В., рэдкалегія: Пашкоў Г. П. (галоўны рэдактар) і інш., "
        "«Гарады і вёскі Беларусі: Энцыклапедыя», г. Мінск, БелЭн., 2004 г., "
        "ISBN 985-11-0303-9 ISBN 985-11-0302-0, Гомельская вобласць, Т. 1, кн. 1, "
        "с. 213—214;"
    )
    assert extract_pages_arg(line, gvb_spec) == "213—214"


def test_extract_pages_arg_supports_star_marker_without_space(repo_root):
    spec = load_source_spec("gvb14", root=repo_root)
    line = (
        "Гарады і вёскі Беларусі: энцыклапедыя. Т. 9 : Гродзенская вобласць, кн. 2 "
        "/ рэдкал.: У. У. Андрыевіч (гал. рэд.) [і інш.]. — Мінск: БелЭн, 2016. "
        "— 848 с.: іл. ISBN 978-985-11-0908-7, стар.346"
    )
    assert extract_pages_arg(line, spec) == "346"


def test_extract_pages_arg_rejects_book_extent(gvb_spec):
    line = (
        "Гарады і вёскі Беларусі: Энцыклапедыя. Т.1, кн.1. Гомельская вобласць "
        "/ С. В. Марцэлеў; Рэдкалегія: Г. П. Пашкоў (галоўны рэдактар) і інш. "
        "— Мн.: БелЭн, 2004. 632 с.: іл. Тыраж 4000 экз. "
        "ISBN 985-11-0303-9 ISBN 985-11-0302-0"
    )
    assert extract_pages_arg(line, gvb_spec) is None


def test_extract_pages_arg_from_template_param(gvb_spec):
    line = (
        "{{кніга|частка = Ручаёўка|загаловак = Гарады і вёскі Беларусі: Энцыклапедыя. "
        "Т. 1, кн. 1. Гомельская вобласць|старонкі = 67—68|старонак = 520 с.: іл.|"
        "isbn = 985-11-0303-9}}"
    )
    assert extract_pages_arg(line, gvb_spec) == "67—68"


def test_extract_pages_arg_from_template_param_for_gvb2(repo_root):
    gvb2_spec = load_source_spec("gvb2", root=repo_root)
    line = (
        "{{кніга|частка = Ручаёўка|загаловак = Гарады і вёскі Беларусі: Энцыклапедыя. "
        "Т. 2, кн. 2. Гомельская вобласць|старонкі = 67—68|старонак = 520 с.: іл.|"
        "isbn = 985-11-0330-6}}"
    )
    assert extract_pages_arg(line, gvb2_spec) == "67—68"


def test_extract_pages_arg_rejects_slash_separated_template_param(repo_root):
    spec = load_source_spec("belen13", root=repo_root)
    line = (
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т. 13: Праміле — Рэлаксін|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2001|"
        "том=13|старонкі=4/4|старонак=576|isbn=985-11-0216-4}}"
    )

    assert extract_pages_arg(line, spec) is None
    assert has_suspicious_page_value(line, spec) is True


def test_extract_entry_arg_from_list_prefix(repo_root):
    spec = load_source_spec("gvb4", root=repo_root)
    line = (
        "* Асмолавічы // Гарады і вёскі Беларусі: Энцыклапедыя ў 15 тамах. "
        "Т. 4, кн. 2. Брэсцкая вобласць / Рэдкалегія: Г. П. Пашкоў "
        "(галоўны рэдактар) і інш. — Мінск.: БелЭн, 2007. — 608 с.: іл. "
        "— С. 118. ISBN 978-985-11-0388-7."
    )
    assert extract_entry_arg(line, spec) == "Асмолавічы"


def test_extract_entry_arg_ignores_bibliography_title_before_double_slash(repo_root):
    spec = load_source_spec("gvb9", root=repo_root)
    line = (
        "* Гарады і вёскі Беларусі: Энцыклапедыя. Т.8, кн.2. Мінская вобласць "
        "// Рэдкалегія: Т. У. Бялова (дырэктар) і інш. — Мн.: БелЭн, 2011. "
        "— 464 с.: іл. ISBN 978-985-11-0554-6"
    )

    assert extract_entry_arg(line, spec) is None


def test_extract_entry_arg_from_template_param(repo_root):
    spec = load_source_spec("gvb2", root=repo_root)
    line = (
        "{{кніга|частка = Ручаёўка|загаловак = Гарады і вёскі Беларусі: Энцыклапедыя. "
        "Т. 2, кн. 2. Гомельская вобласць|старонкі = 67—68|isbn = 985-11-0330-6}}"
    )
    assert extract_entry_arg(line, spec) == "Ручаёўка"


def test_extract_entry_arg_from_multiline_template_param(repo_root):
    spec = load_source_spec("gvb18", root=repo_root)
    line = (
        "{{Кніга\n"
        "| аўтар =\n"
        "| частка = Грыгаравічы\n"
        "| спасылка частка =\n"
        "| загаловак = Гарады і вёскі Беларусі: энцыклапедыя. Т. 10. Віцебская вобласць. кн. 3\n"
        "| адказны = У. У. Ваніна (гал. рэд.) [і інш.]\n"
        "| месца = Мн.\n"
        "| выдавецтва = Беларуская Энцыклапедыя імя Петруся Броўкі\n"
        "| год = 2019\n"
        "| старонкі = 156\n"
        "| старонак = 592\n"
        "| isbn = 978-985-11-1156-1\n"
        "}}"
    )
    assert extract_entry_arg(line, spec) == "Грыгаравічы"


def test_extract_entry_arg_ignores_url_slashes_in_template_without_entry(repo_root):
    spec = load_source_spec("gvb5", root=repo_root)
    line = (
        "* {{Кніга|ref=Гарады і вёскі Беларусі : Энцыклапедыя. Магілёўская вобласць."
        "|спасылка=https://archive.org/details/bel-enc-harvio/HVB.Mahilouskaja.1/page/n367/mode/2up?view=theater "
        "|загаловак=Гарады і вёскі Беларусі : Энцыклапедыя. Магілёўская вобласць. "
        "|адказны=Пад навуковай рэдакцыяй А.І. Лакоткі |год=2008 |мова=be |месца=Мінск "
        "|выдавецтва=Беларуская Энцыклапедыя імя Петруся Броўкі |том=5 "
        "|старонкі=367–368 |старонак=728 |isbn=978-985-11-0409-9}}"
    )

    assert extract_entry_arg(line, spec) is None
    assert extract_pages_arg(line, spec) == "367—368"


def test_extract_template_arguments_for_belen10(repo_root):
    spec = load_source_spec("belen10", root=repo_root)
    line = (
        "{{кніга|частка = Маркава|аўтар = Шаблюк В. У.|частка адказны = В. У. Шаблюк|"
        "загаловак = Беларуская энцыклапедыя: У 18 т. Т. 10: Малайзія — Мугаджары|"
        "старонкі = 114|isbn = 985-11-0169-9}}"
    )

    assert extract_entry_arg(line, spec) == "Маркава"
    assert extract_pages_arg(line, spec) == "114"
    assert extract_template_arguments(line, spec) == {
        "author": "Шаблюк В. У.",
        "responsible": "В. У. Шаблюк",
    }


def test_extract_entry_arg_from_template_title_prefix_for_belen13(repo_root):
    spec = load_source_spec("belen13", root=repo_root)
    line = (
        "{{кніга|загаловак=Рагоўскае возера // Беларуская энцыклапедыя: У 18 т. "
        "Т. 13: Праміле — Рэлаксін|адказны=Рэдкал.: Г. П. Пашкоў і інш|"
        "месца=Мн.|выдавецтва=БелЭн|год=2001|том=13|старонкі=202|"
        "старонак=576|isbn=985-11-0216-4}}"
    )

    assert extract_entry_arg(line, spec) == "Рагоўскае возера"
    assert extract_pages_arg(line, spec) == "202"


def test_extract_pages_arg_treats_double_hyphen_as_dash_equivalent(repo_root):
    spec = load_source_spec("belen16", root=repo_root)
    line = (
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т.16: Трыпалі -- Хвіліна|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2003|"
        "том=16|старонкі=414--415|старонак=576|isbn=985-11-0263-6}}"
    )

    assert extract_pages_arg(line, spec) == "414—415"


def test_extract_list_style_arguments_for_belen10(repo_root):
    spec = load_source_spec("belen10", root=repo_root)
    line = (
        "* Шаблюк В. У. Маркава / В. У. Шаблюк // Беларуская энцыклапедыя: У 18 т. "
        "Т. 10: Малайзія — Мугаджары / Рэдкал.: Г. П. Пашкоў і інш. — Мн. : БелЭн, 2000. "
        "— Т. 10. — С. 114. — 544 с. — 10 000 экз. — ISBN 985-11-0035-8. "
        "— ISBN 985-11-0169-9 (т. 10)."
    )

    assert extract_template_arguments(line, spec) == {
        "author": "Шаблюк В. У.",
        "responsible": "В. У. Шаблюк",
    }


def test_extract_list_style_arguments_for_belen16_comma_author(repo_root):
    spec = load_source_spec("belen16", root=repo_root)
    line = (
        "* Ярмоленка, В. А. Фялінская Ева Зыгмунтаўна / В. А. Ярмоленка // "
        "Беларуская энцыклапедыя: У 18 т. / Беларуская энцыклапедыя; "
        "Рэдкал.: Г. П. Пашкоў (гал. рэд.) [і інш.]. Т. 16: Трыпалі — Хвіліна. "
        "— Мн.: «Беларуская энцыклапедыя», 2003. — 576 с.: іл. — С. 512."
    )

    assert extract_entry_arg(line, spec) == "Фялінская Ева Зыгмунтаўна"
    assert extract_template_arguments(line, spec) == {
        "author": "Ярмоленка, В. А.",
        "responsible": "В. А. Ярмоленка",
    }


def test_extract_entry_arg_from_quoted_author_prefix_for_belen16(repo_root):
    spec = load_source_spec("belen16", root=repo_root)
    line = (
        '* "Лапцэвіч Л. Г." Хатынь // Беларуская энцыклапедыя: У 18 т. '
        "/ Беларуская энцыклапедыя; Рэдкал.: Г. П. Пашкоў і інш. "
        "Т. 16: Трыпалі — Хвіліна. — Мн.: БелЭн, 2003."
    )

    assert extract_entry_arg(line, spec) == "Хатынь"
    assert extract_template_arguments(line, spec) == {
        "author": "Лапцэвіч Л. Г.",
    }


def test_extract_entry_arg_from_author_prefix_before_template_belen17(repo_root):
    spec = load_source_spec("belen17", root=repo_root)
    line = (
        "* Касцюковіч М. Шарпак // {{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. "
        "Т. 17: Хвінявічы — Шчытні|адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|"
        "выдавецтва=БелЭн|год=2003|том=17|старонак=512|isbn=985-11-0279-2}}"
    )

    assert extract_entry_arg(line, spec) == "Шарпак"
    assert extract_template_arguments(line, spec) == {
        "author": "Касцюковіч М.",
    }


def test_extract_multi_author_prefix_before_template_for_belen15(repo_root):
    spec = load_source_spec("belen15", root=repo_root)
    line = (
        "* 'Вештарт І. Ф., Цярохін С. Ф.' Сыта // "
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т.15: Следавікі — Трыо|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2002|"
        "том=15|старонкі=324|старонак=552|isbn=985-11-0251-2 (Т. 15)|тыраж=10&nbsp;000}}"
    )

    assert extract_entry_arg(line, spec) == "Сыта"
    assert extract_pages_arg(line, spec) == "324"
    assert extract_template_arguments(line, spec) == {
        "author": "Вештарт І. Ф., Цярохін С. Ф.",
    }


def test_extract_author_prefix_with_digraph_initial_before_template_for_belen15(repo_root):
    spec = load_source_spec("belen15", root=repo_root)
    line = (
        "* 'Караў У. Дз.' Талстой Дзмітрый Андрэевіч // "
        "{{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. Т.15: Следавікі — Трыо|"
        "адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|выдавецтва=БелЭн|год=2002|"
        "том=15|старонкі=406|старонак=552|isbn=985-11-0251-2 (Т. 15)|тыраж=10&nbsp;000}}"
    )

    assert extract_entry_arg(line, spec) == "Талстой Дзмітрый Андрэевіч"
    assert extract_pages_arg(line, spec) == "406"
    assert extract_template_arguments(line, spec) == {
        "author": "Караў У. Дз.",
    }


def test_extract_author_entry_from_multi_author_prefix_with_page_title_belen8(repo_root):
    spec = load_source_spec("belen8", root=repo_root)
    line = (
        "* Трусаў, А. А., Угрыновіч, У. В. Кафля / А. А. Трусаў, У. В. Угрыновіч // "
        "Беларуская энцыклапедыя: У 18 т. / Беларуская Энцыклапедыя; "
        "рэдкалэ: Г. П. Пашкоў (гал. рэд.) [і інш.]. Т. 8: Канто — Кулі. "
        "— Мн.: БелЭн, 1999. — 572 с.: іл. — С. 188 — 189. — ISBN 985-11-0144-3."
    )

    assert extract_entry_arg(line, spec, "Кафля") == "Кафля"
    assert extract_pages_arg(line, spec) == "188—189"
    assert extract_template_arguments(line, spec, "Кафля") == {
        "author": "Трусаў, А. А., Угрыновіч, У. В.",
        "responsible": "А. А. Трусаў, У. В. Угрыновіч",
    }


def test_extract_author_entry_from_initials_prefix_with_separator_dot_belen1(repo_root):
    spec = load_source_spec("belen1", root=repo_root)
    line = (
        "* А. М. Булыка. Апостраф // {{кніга|загаловак=Беларуская энцыклапедыя: У 18 т. "
        "Т. 1: А — Аршын|адказны=Рэдкал.: Г. П. Пашкоў і інш|месца=Мн.|"
        "выдавецтва=БелЭн|год=1996|том=1|старонак=552|isbn=985-11-0036-6|тыраж=10&nbsp;000}}"
    )

    assert extract_entry_arg(line, spec, "Апостраф") == "Апостраф"
    assert extract_template_arguments(line, spec, "Апостраф") == {
        "author": "А. М. Булыка",
    }


def test_split_ref_aware_segments_ignores_self_closing_refs_before_real_ref():
    text = (
        'Text<ref name="one" /> more <ref name="two"/>'
        '<ref name="target">{{кніга|загаловак=Гарады і вёскі Беларусі|isbn=985-11-0330-6}}</ref>'
    )

    segments = split_ref_aware_segments(text)

    assert segments == [
        (
            "text",
            'Text<ref name="one" /> more <ref name="two"/>',
            None,
            None,
        ),
        (
            "ref",
            "{{кніга|загаловак=Гарады і вёскі Беларусі|isbn=985-11-0330-6}}",
            '<ref name="target">',
            "</ref>",
        ),
    ]


def test_fixture_variants_normalize_without_markup(gvb_spec, project_root):
    fixture_path = project_root / "tests" / "fixtures" / "gvb_exact_variants.json"
    variants = json.loads(fixture_path.read_text(encoding="utf-8"))
    normalized = [normalize_biblio_wikitext(item, gvb_spec) for item in variants]
    assert any("БелЭн" in item for item in normalized)
    assert any("ISBN 985-11-0303-9" in item for item in normalized)
