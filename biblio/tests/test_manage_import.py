from __future__ import annotations

from pathlib import Path

from biblio.manage_import import (
    build_imported_template_forms,
    fetch_template_raw,
    parse_template_facts,
)


def _fixture_text(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / "template_raw" / name
    return path.read_text(encoding="utf-8")


def test_parse_template_facts_extracts_belen_aliases_and_volumes():
    facts = parse_template_facts("Шаблон:Крыніцы/БелЭн", _fixture_text("belen.txt"))

    role_lookup = {item.role: item for item in facts.role_params}

    assert facts.template_name == "Крыніцы/БелЭн"
    assert facts.source_search_seed == ("Беларуская энцыклапедыя",)
    assert role_lookup["volume"].params == ("том", "1")
    assert role_lookup["entry"].params == ("артыкул", "2")
    assert role_lookup["author"].params == ("аўтар", "3")
    assert role_lookup["pages"].params == ("старонкі", "с", "4")
    assert role_lookup["responsible"].params == ("адказны", "5")
    assert role_lookup["ref"].params == ("ref",)
    assert role_lookup["ref"].default == "БелЭн"
    assert facts.extra_params == ()
    assert len(facts.volumes) == 19
    assert facts.volumes[0].volume == "1"
    assert facts.volumes[0].title == "Т. 1: А — Аршын"
    assert facts.volumes[0].year == "1996"
    assert facts.volumes[0].isbn == "985-11-0036-6"
    assert facts.volumes[-1].volume == "18-2"
    assert facts.volumes[-1].title == "Т. 18. Кн. 2: Рэспубліка Беларусь"
    assert facts.volumes[-1].year == "2004"
    assert facts.volumes[-1].isbn == "985-11-0295-4"


def test_parse_template_facts_detects_extra_params():
    raw = """
|частка = {{{артыкул|{{{2|}}}}}}
|аўтар = {{{аўтар|{{{3|}}}}}}
|ref = {{{ref|БелЭн}}}
|custom = {{{псеўданім|{{{alias|}}}}}}
"""

    facts = parse_template_facts("Шаблон:Крыніцы/Прыклад", raw)

    assert facts.extra_params == ("псеўданім", "alias")


def test_parse_template_facts_extracts_rb7_volumes_and_isbn_switch():
    facts = parse_template_facts(
        "Шаблон:Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах",
        _fixture_text("rb7.txt"),
    )

    role_lookup = {item.role: item for item in facts.role_params}

    assert facts.template_name == "Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах"
    assert facts.source_search_seed == ("Рэспубліка Беларусь (энцыклапедыя)",)
    assert role_lookup["volume"].params == ("том", "1")
    assert role_lookup["entry"].params == ("артыкул", "2")
    assert role_lookup["pages"].params == ("старонкі", "с", "3")
    assert role_lookup["author"].params == ("аўтар", "4")
    assert len(facts.volumes) == 7
    assert facts.volumes[0].volume == "1"
    assert facts.volumes[0].title == "1"
    assert facts.volumes[0].year == "2005"
    assert facts.volumes[0].isbn == "985-11-0342-X"
    assert facts.volumes[1].title == "2: А — Герань"
    assert facts.volumes[-1].volume == "7"
    assert facts.volumes[-1].year == "2008"
    assert facts.volumes[-1].isbn == "978-985-11-0421-1"


def test_build_imported_template_forms_uses_detected_positional_layout():
    facts = parse_template_facts(
        "Шаблон:Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах",
        _fixture_text("rb7.txt"),
    )

    without_pages, with_pages = build_imported_template_forms(
        facts.template_name,
        facts.role_params,
        single_volume=False,
    )

    assert (
        without_pages
        == "{{Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах|{volume}|{entry}||{author}}}"
    )
    assert (
        with_pages
        == "{{Крыніцы/Рэспубліка Беларусь: Энцыклапедыя ў 7 тамах|{volume}|{entry}|{pages}|{author}}}"
    )


def test_fetch_template_raw_uses_action_raw(monkeypatch):
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self) -> bytes:
            return b"raw body"

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("biblio.manage_import.urlopen", fake_urlopen)

    result = fetch_template_raw(
        "Шаблон:Крыніцы/БелЭн",
        site_lang="be",
        family="wikipedia",
        timeout=7.5,
    )

    assert result == "raw body"
    assert "action=raw" in seen["url"]
    assert "%D0%A8%D0%B0%D0%B1%D0%BB%D0%BE%D0%BD" in seen["url"]
    assert seen["timeout"] == 7.5
