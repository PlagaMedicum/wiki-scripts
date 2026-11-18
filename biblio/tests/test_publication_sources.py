import pytest
from biblio.engine import replace_text
from biblio.specs import load_source_spec

SOURCES = [
    (
        "belarusian-language-1994",
        "* {{Артыкул|загаловак=Тэма|выданне=Беларуская мова: энцыклапедыя|"
        "месца=Минск|выдавецтва=Беларуская Энцыклапедыя|год=1994|"
        "старонкі=$PAGES|isbn=5-85700-126-9}}",
        "* {{Крыніцы/Беларуская мова: энцыклапедыя|Тэма|с=$PAGES}}",
    ),
    (
        "music-dictionary-1990",
        "* Музыкальный энциклопедический словарь / Гл. ред. Г. В. Келдыш. "
        "— М.: Советская энциклопедия, 1990. — С. $PAGES. — ISBN 5-85270-033-9",
        "* {{Крыніцы/Музыкальный энциклопедический словарь|||$PAGES}}",
    ),
    (
        "myths-1992-volume2",
        "<ref>{{кніга|аўтар=|загаловак=Мифы народов мира. В 2-х т|месца=М.|"
        "год=1991—1992|том=2|старонкі=$PAGES}}</ref>",
        "<ref>{{Крыніцы/Мифы народов мира: Энциклопедия|том=2|старонкі=$PAGES}}</ref>",
    ),
]


@pytest.mark.parametrize(("source_id", "citation", "expected"), SOURCES)
@pytest.mark.parametrize("pages", ["42", "42—43"])
def test_publication_forms_preserve_pages_and_require_review(
    repo_root, source_id, citation, expected, pages
):
    spec = load_source_spec(source_id, root=repo_root)
    text = citation.replace("$PAGES", pages)

    result = replace_text(text, spec, [], page_title="Незвязаная тэма")

    assert result.text == expected.replace("$PAGES", pages)
    assert result.replacements == 1
    assert result.review_reasons
    assert result.matched_review_lines


@pytest.mark.parametrize(("source_id", "citation", "expected"), SOURCES)
def test_publication_forms_do_not_change_protected_text(repo_root, source_id, citation, expected):
    spec = load_source_spec(source_id, root=repo_root)
    text = citation.replace("$PAGES", "42")
    result = replace_text(f"<!-- {text} -->\n{text}", spec, [], page_title="Незвязаная тэма")

    assert result.text == f"<!-- {text} -->\n{expected.replace('$PAGES', '42')}"
    assert result.replacements == 1
    assert result.review_reasons


def test_language_article_parameter_order_is_not_significant(repo_root):
    spec = load_source_spec("belarusian-language-1994", root=repo_root)
    text = (
        "* {{Артыкул|isbn=5-85700-126-9|старонкі=42—43|год=1994|"
        "выдавецтва=Беларуская Энцыклапедыя|месца=Минск|"
        "выданне=Беларуская мова: энцыклапедыя|загаловак=Тэма}}"
    )

    result = replace_text(text, spec, [], page_title="Незвязаная тэма")

    assert result.text == "* {{Крыніцы/Беларуская мова: энцыклапедыя|Тэма|с=42—43}}"
    assert result.review_reasons


def test_myths_book_without_empty_author_parameter(repo_root):
    spec = load_source_spec("myths-1992-volume2", root=repo_root)
    _, citation, expected = SOURCES[2]
    text = citation.replace("|аўтар=", "").replace("$PAGES", "219—220")

    result = replace_text(text, spec, [], page_title="Незвязаная тэма")

    assert result.text == expected.replace("$PAGES", "219—220")
    assert result.review_reasons


def test_myths_book_parameter_order_is_not_significant(repo_root):
    spec = load_source_spec("myths-1992-volume2", root=repo_root)
    text = (
        "<ref>{{кніга|том=2|старонкі=219—220|год=1991—1992|месца=М.|"
        "загаловак=Мифы народов мира. В 2-х т}}</ref>"
    )

    result = replace_text(text, spec, [], page_title="Незвязаная тэма")

    assert result.text == (
        "<ref>{{Крыніцы/Мифы народов мира: Энциклопедия|том=2|старонкі=219—220}}</ref>"
    )
    assert result.review_reasons


@pytest.mark.parametrize(
    "citation",
    [
        "* Музыкальный энциклопедический словарь. М., «Советская энциклопедия», 1990",
        "* Музыкальный энциклопедический словарь. М.: Советская энциклопедия, 1990.",
    ],
)
def test_music_full_book_citation_requires_review(repo_root, citation):
    spec = load_source_spec("music-dictionary-1990", root=repo_root)

    result = replace_text(citation, spec, [], page_title="Незвязаная тэма")

    assert result.text == "* {{Крыніцы/Музыкальный энциклопедический словарь}}"
    assert result.review_reasons


@pytest.mark.parametrize(
    ("source_id", "citation"),
    [
        (
            "belarusian-language-1994",
            "* {{Артыкул|загаловак=Тэма|выданне=Беларуская мова: энцыклапедыя|"
            "месца=Минск|выдавецтва=Беларуская Энцыклапедыя|год=1994|"
            "старонкі=42|isbn=5-85700-126-9|спасылка=https://example.invalid/source}}",
        ),
        (
            "belarusian-language-1994",
            "* {{Артыкул|загаловак=Тэма|выданне=Беларуская мова: энцыклапедыя|"
            "месца=Минск|выдавецтва=Беларуская Энцыклапедыя|год=1994|"
            "старонкі=42|isbn=5-85700-126-9|ref=CustomAnchor}}",
        ),
        (
            "belarusian-language-1994",
            "* {{Артыкул|загаловак=Тэма|выданне=Беларуская мова: энцыклапедыя|"
            "месца=Минск|выдавецтва=Беларуская Энцыклапедыя|год=1994|"
            "старонкі=42|isbn=5-85700-126-9|год=2000}}",
        ),
        (
            "belarusian-language-1994",
            "* {{Артыкул|загаловак=[[Іншая старонка|Тэма]]|"
            "выданне=Беларуская мова: энцыклапедыя|месца=Минск|"
            "выдавецтва=Беларуская Энцыклапедыя|год=1994|"
            "старонкі=42|isbn=5-85700-126-9}}",
        ),
        (
            "music-dictionary-1990",
            "* [[Іншая старонка|Музыкальный энциклопедический словарь]]. "
            "М., «Советская энциклопедия», 1990",
        ),
        (
            "music-dictionary-1990",
            "* Музыкальный энциклопедический словарь / Гл. ред. Г. В. Келдыш. "
            "— М.: Советская энциклопедия, 2003. — С. 42. — ISBN 5-85270-033-9",
        ),
        (
            "music-dictionary-1990",
            "* Музыкальный энциклопедический словарь / Гл. ред. Г. В. Келдыш. "
            "— М.: Советская энциклопедия, 1990. — С. 42. — ISBN 5-85270-033-9. "
            "Дадатковыя звесткі.",
        ),
        (
            "myths-1992-volume2",
            "<ref>{{кніга|аўтар=|загаловак=Мифы народов мира. В 2-х т|месца=М.|"
            "год=1991—1992|том=1|старонкі=42}}</ref>",
        ),
        (
            "myths-1992-volume2",
            "<ref>{{кніга|аўтар=|загаловак=Мифы народов мира. В 2-х т|месца=М.|"
            "год=1991—1992|том=2|старонкі=42|спасылка=https://example.invalid/source}}</ref>",
        ),
        (
            "myths-1992-volume2",
            "<ref>{{кніга|аўтар=Аўтар|загаловак=Мифы народов мира. В 2-х т|месца=М.|"
            "год=1991—1992|том=2|старонкі=42}}</ref>",
        ),
        (
            "myths-1992-volume2",
            "<ref>{{кніга|загаловак=Мифы народов мира. В 2-х т|месца=М.|"
            "год=1991—1992|том=2|старонкі=42|том=1}}</ref>",
        ),
    ],
)
def test_publication_forms_leave_conflicting_or_extra_information(repo_root, source_id, citation):
    spec = load_source_spec(source_id, root=repo_root)

    result = replace_text(citation, spec, [], page_title="Незвязаная тэма")

    assert result.text == citation
    assert result.replacements == 0
