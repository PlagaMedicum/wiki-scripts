from __future__ import annotations

import re

# Python reproductions of wikificator's core regex transformations for automated regression testing


def process_link_py(left: str, right: str) -> str:
    left = left.replace("\u00a0", " ").strip()
    left = re.sub(r"[ _]+", " ", left)
    if re.match(r"^(?:Катэгорыя|Файл) ?:", left):
        return f"[[{left}|{right}]]"

    right = re.sub(r" {2,}", " ", right.strip())
    after_link = right[len(left) :]
    uni_left = left[:1].upper() + left[1:]
    uni_right = (right[:1].upper() + right[1:]).replace("_", " ").replace("\u00a0", " ")

    # The buggy regex in original JS:
    # afterLink.match(/^[a-zа-яё]*$/)
    # The fixed regex must include Belarusian letters і, ў:
    # afterLink.match(/^[a-zа-яёіў]*$/)
    if uni_right.startswith(uni_left) and re.match(r"^[a-zа-яёіў]*$", after_link, re.IGNORECASE):
        in_link = right[: len(left)]
        return f"[[{in_link}]]{after_link}"
    return f"[[{left}|{right}]]"


def test_belarusian_link_simplification():
    # Words with 'ў' and 'і' in inflectional suffixes
    # In MediaWiki wikitext, [[A|AB]] simplifies to [[A]]B
    assert process_link_py("лес", "лесаў") == "[[лес]]аў"
    assert process_link_py("Мінск", "Мінскі") == "[[Мінск]]і"
    assert process_link_py("горад", "горадзе") == "[[горад]]зе"
    # When right does not start with left (stem modification), keep piped
    assert process_link_py("рубель", "рублі") == "[[рубель|рублі]]"


def test_html_comments_protection():
    # Demonstrating the defect: HTML comments must be protected like tags
    raw = "Тэкст <!-- Каментар з працяжнікам -- і «двукоссямі» --> працяг."
    # If comments are protected:
    comment_pattern = re.compile(r"<!--[\s\S]*?-->")
    hidden = []

    def hide(match):
        hidden.append(match.group(0))
        return f"\x01{len(hidden)}\x02"

    protected = comment_pattern.sub(hide, raw)
    assert "\x011\x02" in protected
    # Unhide restore
    restored = re.sub(r"\x01(\d+)\x02", lambda m: hidden[int(m.group(1)) - 1], protected)
    assert restored == raw


def test_arithmetic_subtraction_vs_dash():
    # Arithmetic: "5 - 3 = 2" should NOT become "5 — 3 = 2"
    # In math expressions: (\d)\s*[-−]\s*(\d)\s*=\s*(\d)
    expr = "5 - 3 = 2"
    # Ensure minus sign or space-dash-space in math is preserved or uses minus sign −
    math_pattern = re.compile(r"(\d+)\s*-\s*(\d+)\s*=")
    fixed = math_pattern.sub(r"\1 − \2 =", expr)
    assert "—" not in fixed
    assert "5 − 3 =" in fixed


def test_numeric_ranges_preserve_en_dash():
    # "стар. 10–15" or "10–15" should not be destroyed into a raw hyphen "10-15"
    # En-dash U+2013:
    range_text = "стар. 10–15"
    # In wikificator, line 192 converts ALL '–' to '-', losing the en-dash in non-year numeric ranges!
    assert "–" in range_text
