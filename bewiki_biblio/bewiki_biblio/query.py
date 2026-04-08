from __future__ import annotations

from bewiki_biblio.models import SourceSpec


def build_search_query(spec: SourceSpec) -> str:
    parts: list[str] = []
    for value in spec.search_terms:
        parts.append(f'insource:"{value}"')
    return " ".join(parts)
