from __future__ import annotations

import re
from collections.abc import Mapping

TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
MACRO_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def parse_regex_flags(flag_names: str) -> int:
    if not flag_names:
        return 0

    flags = 0
    for name in re.split(r"[|,\s]+", flag_names.strip()):
        if not name:
            continue
        if not hasattr(re, name):
            raise ValueError(f"Unsupported regex flag: {name}")
        flags |= getattr(re, name)
    return flags


def substitute_tokens(template: str, mapping: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return mapping.get(key, match.group(0))

    return TOKEN_RE.sub(replace, template)


def format_wiki_target(site_lang: str, family: str) -> str:
    return f"{site_lang}/{family}"


def expand_macro_template(
    template: str,
    macros: Mapping[str, str],
    stack: tuple[str, ...] = (),
) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in macros:
            raise ValueError(f"Undefined macro: {name}")
        if name in stack:
            chain = " -> ".join((*stack, name))
            raise ValueError(f"Macro cycle detected: {chain}")
        return expand_macro_template(macros[name], macros, (*stack, name))

    expanded = MACRO_RE.sub(replace, template)
    if expanded == template:
        return expanded
    return expand_macro_template(expanded, macros, stack)
