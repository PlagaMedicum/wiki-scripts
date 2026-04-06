from __future__ import annotations

import re

from bewiki_biblio.models import SourceSpec
from bewiki_biblio.utils import parse_regex_flags


WIKILINK_PIPED_RE = re.compile(r"\[\[[^|\]]+\|([^\]]+)\]\]")
WIKILINK_SIMPLE_RE = re.compile(r"\[\[([^\]]+)\]\]")
NOWIKI_TAG_RE = re.compile(r"</?nowiki>", re.IGNORECASE)
ITALIC_BOLD_RE = re.compile(r"''+")
REF_BODY_RE = re.compile(
    r"(?P<open><ref\b(?:\"[^\"]*\"|'[^']*'|[^'\">])*(?<!/)>)"
    r"(?P<body>.*?)"
    r"(?P<close></ref\s*>)",
    re.IGNORECASE | re.DOTALL,
)
REVIEW_LINE_PREFIX_RE = re.compile(
    r"^(?P<prefix>\s*(?:[*#;:]+\s*)?)(?P<body>.*)$",
    re.UNICODE,
)


def normalize_biblio_wikitext(text: str, spec: SourceSpec) -> str:
    options = spec.normalization
    if options.strip_nowiki:
        text = NOWIKI_TAG_RE.sub("", text)
    if options.resolve_wikilinks:
        text = WIKILINK_PIPED_RE.sub(r"\1", text)
        text = WIKILINK_SIMPLE_RE.sub(r"\1", text)
    if options.strip_formatting:
        text = ITALIC_BOLD_RE.sub("", text)
    if options.normalize_nbsp:
        text = text.replace("\u00A0", " ")
    if options.normalize_dashes:
        text = re.sub(r"\s*[—–]\s*", " — ", text)

    for alias in spec.alias_rules:
        text = re.sub(
            alias.pattern,
            alias.replacement,
            text,
            flags=parse_regex_flags(alias.flags),
        )

    if options.collapse_whitespace:
        text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_pages_arg(pages: str) -> str:
    pages = re.sub(r"\s*[—–-]\s*", "—", pages)
    pages = re.sub(r"\s*,\s*", ", ", pages)
    return pages.strip()


def normalize_entry_arg(entry: str) -> str:
    entry = normalize_whitespace(entry)
    entry = re.sub(r"\s*[—–-]\s*", " — ", entry)
    entry = entry.strip(" \t\r\n,;:.")
    return entry


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_review_line(line: str, spec: SourceSpec) -> str:
    line = re.sub(r"^\s*[*#;:]+\s*", "", line).strip()
    line = normalize_biblio_wikitext(line, spec)

    line = re.sub(r"\s*/\s*", " / ", line)
    line = re.sub(r"\s*;\s*", "; ", line)
    line = re.sub(r"\s*,\s*", ", ", line)
    line = re.sub(r"\s*:\s*", ": ", line)
    line = re.sub(r"\bТ\.\s*(\d+)\b", r"Т. \1", line, flags=re.IGNORECASE)
    line = re.sub(r"\bкн\.\s*(\d+)\b", r"кн. \1", line, flags=re.IGNORECASE)
    line = re.sub(r"\b([А-ЯA-Z])\.\s*([А-ЯA-Z])\.", r"\1. \2.", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


ENTRY_TEMPLATE_PARAM_RE = re.compile(
    r"\|\s*(?:частка|раздзел|chapter|entry|article|артыкул)\s*=\s*(?P<entry>[^|}]+)",
    re.IGNORECASE | re.UNICODE,
)
ENTRY_LIST_PREFIX_RE = re.compile(
    r"^\s*(?:[*#;:]+\s*)?(?P<entry>.+?)\s*(?://|/\s*/)\s*(?=\S)",
    re.UNICODE,
)
BIBLIOGRAPHY_DESCRIPTOR_RE = re.compile(
    r"\b(?:isbn|энцыклап(?:едыя)?|encyclop(?:aedia|edia)?|том)\b",
    re.IGNORECASE | re.UNICODE,
)
VOLUME_MARKER_RE = re.compile(
    r"\bт\.\s*\d+\b|\bкн\.\s*\d+\b",
    re.IGNORECASE | re.UNICODE,
)


def split_ref_aware_segments(
    text: str,
) -> list[tuple[str, str, str | None, str | None]]:
    segments: list[tuple[str, str, str | None, str | None]] = []
    position = 0

    for match in REF_BODY_RE.finditer(text):
        if match.start() > position:
            segments.append(("text", text[position : match.start()], None, None))
        segments.append(
            (
                "ref",
                match.group("body"),
                match.group("open"),
                match.group("close"),
            )
        )
        position = match.end()

    if position < len(text):
        segments.append(("text", text[position:], None, None))

    if not segments:
        segments.append(("text", text, None, None))

    return segments


def make_review_key(line: str, spec: SourceSpec) -> str:
    return normalize_review_line(line, spec).casefold()


def _looks_like_bibliography_prefix(entry: str, spec: SourceSpec) -> bool:
    candidate = normalize_biblio_wikitext(entry, spec).casefold()
    if not candidate:
        return False

    signals = 0
    if ":" in candidate:
        signals += 1
    if BIBLIOGRAPHY_DESCRIPTOR_RE.search(candidate):
        signals += 1
    if VOLUME_MARKER_RE.search(candidate):
        signals += 1

    source_name = normalize_biblio_wikitext(spec.name, spec).casefold()
    if source_name and source_name in candidate:
        signals += 1

    for term in spec.insource_terms + spec.keywords:
        normalized_term = normalize_biblio_wikitext(term, spec).casefold()
        if len(normalized_term) >= 4 and normalized_term in candidate:
            signals += 1
            break

    return signals >= 2


def extract_entry_arg(text: str, spec: SourceSpec) -> str | None:
    raw = re.sub(r"^\s*[*#;:]+\s*", "", text).strip()
    normalized = normalize_biblio_wikitext(raw, spec)

    match = ENTRY_TEMPLATE_PARAM_RE.search(normalized)
    if match:
        entry = normalize_entry_arg(match.group("entry"))
        return entry or None

    if normalized.startswith("{{"):
        return None

    match = ENTRY_LIST_PREFIX_RE.match(normalized)
    if match:
        entry = normalize_entry_arg(match.group("entry"))
        if entry and len(entry) <= 200 and not _looks_like_bibliography_prefix(entry, spec):
            return entry

    return None


def extract_pages_arg(text: str, spec: SourceSpec) -> str | None:
    normalized = normalize_biblio_wikitext(text, spec)
    candidates: list[tuple[int, str]] = []

    for regex in spec.page_patterns:
        for match in regex.finditer(normalized):
            pages = normalize_pages_arg(match.group("pages"))
            tail = normalized[match.end() : match.end() + 20]

            if any(reject_pattern.search(tail) for reject_pattern in spec.reject_patterns):
                continue

            score = 0
            if match.start() < 12:
                score += 2
            if match.end() > len(normalized) - 12:
                score += 2
            if "isbn" in normalized[max(0, match.start() - 40) : min(len(normalized), match.end() + 40)].casefold():
                score += 1

            candidates.append((score, pages))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]
