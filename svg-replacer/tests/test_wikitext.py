from __future__ import annotations

import pytest
from svg_replacer.wikitext import (
    FileNamespace,
    add_vector_template,
    assess_usage,
    discover_raster_candidates,
    find_file_links,
    has_vector_template,
    normalize_file_name,
    remove_svg_markers,
    replace_usage,
)

COMMONS_FILES = FileNamespace.of("File", "Image", "Файл", "Выява")

# Belarusian prose with the characters that naive implementations corrupt:
# і (dotted i), ў (short u), ё, U+2019 apostrophe, NBSP, combining-safe Cyrillic.
BELARUSIAN = "Мінск — сталіца Беларусі, горад ў цэнтры. Апошняе слова: «так».\n"


def test_replace_preserves_options_caption_and_surrounding_wikitext() -> None:
    text = (
        "Абзац перад выявай.\n"
        "[[Файл:Foo.png|thumb|120px|Падпіс: сцяг Беларусі ў аблоках]]\n"
        "Абзац пасля выявы.\n"
    )

    new_text, count = replace_usage(text, "Foo.png", "Foo.svg", COMMONS_FILES)

    assert count == 1
    assert new_text == (
        "Абзац перад выявай.\n"
        "[[Файл:Foo.svg|thumb|120px|Падпіс: сцяг Беларусі ў аблоках]]\n"
        "Абзац пасля выявы.\n"
    )
    # Everything except the replaced filename is byte-for-byte identical.
    assert new_text.replace("Foo.svg", "Foo.png", 1) == text


def test_replace_normalizes_underscores_case_and_spacing() -> None:
    text = "Прыклад: [[File:foo_bar.png|left]] тут."
    assert normalize_file_name("foo bar.png") == "Foo bar.png"

    new_text, count = replace_usage(text, "Foo_bar.png", "Foo_bar.svg", COMMONS_FILES)
    assert count == 1
    assert "[[File:Foo_bar.svg|left]]" in new_text


def test_replace_handles_namespace_aliases_and_lowercase_prefix() -> None:
    text = "[[Image:Foo.png]]\n[[file:Foo.png|20px]]\n[[Выява:Foo.png|frame]]\n[[Шаблон:Foo.png]]\n"
    new_text, count = replace_usage(text, "Foo.png", "Foo.svg", COMMONS_FILES)

    assert count == 3
    assert "[[Image:Foo.svg]]" in new_text
    assert "[[file:Foo.svg|20px]]" in new_text
    assert "[[Выява:Foo.svg|frame]]" in new_text
    # Non-file namespaces are never touched.
    assert "[[Шаблон:Foo.png]]" in new_text


def test_unicode_preserved_byte_for_byte_outside_filename() -> None:
    text = BELARUSIAN + "[[Файл:Foo.png|рамка]]\n" + BELARUSIAN
    new_text, _ = replace_usage(text, "Foo.png", "Foo.svg", COMMONS_FILES)

    before, after = new_text.split("[[Файл:Foo.svg|рамка]]")
    assert before == BELARUSIAN
    assert after == "\n" + BELARUSIAN
    assert "ў" in new_text and "і" in new_text and "«" in new_text


def test_template_nested_occurrence_is_blocked_not_replaced() -> None:
    text = "{{Інфабокс\n| выява = [[Файл:Foo.png]]\n}}\nПрамы выяву: [[Файл:Foo.png]]\n"
    assessment = assess_usage(text, "Foo.png", COMMONS_FILES)

    assert assessment.status == "blocked"
    assert "template" in assessment.blocked_reason


def test_usage_hidden_inside_template_call_is_indirect() -> None:
    text = "{{Портал|малюнак=Foo.png}}\n{{Файл-без-пасылкі}}\n"
    assessment = assess_usage(text, "Foo.png", COMMONS_FILES)
    assert assessment.status == "indirect"


def test_usage_in_comment_or_nowiki_is_blocked() -> None:
    commented = "<!-- [[Файл:Foo.png]] -->\n"
    nowiki = "<nowiki>[[Файл:Foo.png]]</nowiki>\n"
    assert assess_usage(commented, "Foo.png", COMMONS_FILES).status == "blocked"
    assert assess_usage(nowiki, "Foo.png", COMMONS_FILES).status == "blocked"


def test_multiple_direct_occurrences_are_all_replaced() -> None:
    text = "[[Файл:Foo.png]] і зноў [[Файл:Foo.png|малы]].\n"
    assessment = assess_usage(text, "Foo.png", COMMONS_FILES)
    assert assessment.status == "replace"
    assert len(assessment.matches) == 2

    new_text, count = replace_usage(text, "Foo.png", "Foo.svg", COMMONS_FILES)
    assert count == 2
    assert "Foo.png" not in new_text


def test_unrelated_files_and_plain_mentions_untouched() -> None:
    text = (
        "[[Файл:Other.png]]\nСпасылка на [[Foo.png]] як артыкул.\nПроста тэкст Foo.png у радку.\n"
    )
    assessment = assess_usage(text, "Foo.png", COMMONS_FILES)
    assert assessment.status == "indirect"
    with pytest.raises(ValueError):
        replace_usage(text, "Foo.png", "Foo.svg", COMMONS_FILES)


def test_replace_usage_refuses_unsafe_pages() -> None:
    text = "{{Інфабокс|выява=[[Файл:Foo.png]]}}"
    with pytest.raises(ValueError):
        replace_usage(text, "Foo.png", "Foo.svg", COMMONS_FILES)


def test_find_file_links_reports_spans_without_fragment_or_padding() -> None:
    text = "[[ Файл:Foo.png#fragment |parameter]]"
    links = find_file_links(text, COMMONS_FILES)
    assert len(links) == 1
    link = links[0]
    assert text[link.name_start : link.name_end] == "Foo.png"
    assert link.options == "parameter"
    assert link.template_depth == 0
    assert link.unsafe_reason is None


def test_siteinfo_aliases_recognize_local_and_canonical_names() -> None:
    namespaces = {
        "0": {"name": "", "subpages": False},
        "6": {"name": "Файл", "canonical": "File"},
    }
    aliases = [{"id": 6, "alias": "Image"}, {"id": 6, "alias": "Выява"}]
    ns = FileNamespace.from_siteinfo(namespaces, aliases)

    for prefix in ("Файл", "файл", "File", "file", "Image", "image", "Выява", "выява"):
        assert ns.matches(prefix), prefix
    assert not ns.matches("Шаблон")
    assert not ns.matches("Imagee")


def test_discover_raster_candidates_from_derivation_info() -> None:
    svg_page = (
        "{{Information\n"
        "| source = [[File:Original photo.jpg]]\n"
        "| other versions = [[:File:older_version.png]]\n"
        "}}\n"
        "Mirror: https://upload.wikimedia.org/wikipedia/commons/1/2/scan001.tif\n"
        "Irrelevant: https://example.org/diagram.svg\n"
    )
    candidates = discover_raster_candidates(svg_page, COMMONS_FILES)

    names = [c.name for c in candidates]
    assert "Original photo.jpg" in names
    assert "older_version.png" in names
    assert "scan001.tif" in names
    assert not any(name.endswith(".svg") for name in names)
    assert not any(name.startswith("diagram") for name in names)
    # Deduplicated by normalized name.
    assert len({normalize_file_name(n) for n in names}) == len(names)


@pytest.mark.parametrize("template", ["Derived from", "derived_from"])
def test_discover_plain_derived_from_parameters(template):
    text = (
        "{{Information|source={{"
        + template
        + "|Project Management (phases).png|by=[[User:Example|Example]]}}"
        "|other_versions={{Other versions|Translated diagram.png}}}}"
    )
    candidates = discover_raster_candidates(text, COMMONS_FILES)
    assert [candidate.name for candidate in candidates] == ["Project Management (phases).png"]


def test_multiple_derived_sources_remain_ambiguous():
    text = "{{Derived from|1=First.png|2=Second.jpg|by=Example}}"
    assert {candidate.name for candidate in discover_raster_candidates(text, COMMONS_FILES)} == {
        "First.png",
        "Second.jpg",
    }


def test_commented_derivation_is_not_a_source():
    assert discover_raster_candidates("<!-- {{Derived from|Unused.png}} -->", COMMONS_FILES) == []


def test_discover_raster_candidates_commons_file_urls() -> None:
    svg_page = (
        "Converted from https://commons.wikimedia.org/wiki/File:Derived_image.PNG?uselang=be\n"
    )
    candidates = discover_raster_candidates(svg_page, COMMONS_FILES)
    assert [c.name for c in candidates] == ["Derived_image.PNG"]


def test_remove_svg_markers_drops_own_line_and_newline():
    text = "{{Information|x}}\n{{SVG|diagram}}\n\n== license ==\n"
    assert remove_svg_markers(text) == "{{Information|x}}\n\n== license ==\n"


@pytest.mark.parametrize(
    "marker",
    [
        "{{SVG}}",
        "{{svg|diagram}}",
        "{{ subst:SVG | x }}",
        "{{Convert to SVG|diagram}}",
        "{{convert_to_svg}}",
        "{{ convert to svg |1= please }}",
    ],
)
def test_remove_svg_markers_recognizes_marker_family(marker):
    assert marker not in remove_svg_markers(f"before {marker} after\n")


@pytest.mark.parametrize(
    "text",
    [
        "<!-- {{SVG|diagram}} -->",
        "<nowiki>{{SVG|diagram}}</nowiki>",
        "{{SVG|{{nested}}}}",
        "{{SVGx|y}}",
        "{{SVG other|y}}",
    ],
)
def test_remove_svg_markers_never_touches_protected_or_foreign(text):
    assert remove_svg_markers(text) == text


def test_vector_template_detection_and_addition() -> None:
    assert has_vector_template("{{Vector version available|Foo.svg}}")
    assert has_vector_template("desc\n{{vector version available|Foo.svg}}\nmore")
    assert has_vector_template("{{VVA|Foo.svg}}")
    assert has_vector_template("{{ subst:Vector version available | Foo.svg }}")
    assert has_vector_template("{{Vector version available}}")
    assert not has_vector_template("no template here")
    assert not has_vector_template("{{Vector version}}")
    assert not has_vector_template("see Vector version available docs")

    text = "{{Information|description=x}}\n"
    new_text = add_vector_template(text, "Foo.svg")
    assert new_text == "{{Vector version available|Foo.svg}}\n" + text
    # Byte-for-byte preservation of the original page body.
    assert new_text.removeprefix("{{Vector version available|Foo.svg}}\n") == text
