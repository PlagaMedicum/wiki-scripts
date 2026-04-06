from __future__ import annotations

from dataclasses import dataclass
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
TEMPLATE_DELIMITER_RE = re.compile(r"\{\{|\}\}")


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


def normalize_title_for_match(text: str) -> str:
    text = text.replace("_", " ").replace("\u00A0", " ")
    text = re.sub(r"\s*[—–-]\s*", " — ", text)
    return normalize_whitespace(text).casefold()


def entry_matches_page_title(entry: str, page_title: str) -> bool:
    return normalize_title_for_match(entry) == normalize_title_for_match(page_title)


def normalize_argument_value(value: str, normalizer: str) -> str:
    if normalizer == "pages":
        return normalize_pages_arg(value)
    if normalizer == "entry":
        return normalize_entry_arg(value)
    if normalizer == "whitespace":
        return normalize_whitespace(value)
    return value.strip()


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
TITLE_TEMPLATE_PARAM_RE = re.compile(
    r"(?P<prefix>\|\s*(?:загаловак|title)\s*=\s*)(?P<value>[^|}]+)",
    re.IGNORECASE | re.UNICODE,
)
ENTRY_LIST_PREFIX_RE = re.compile(
    r"^\s*(?:[*#;:]+\s*)?(?P<entry>.+?)\s*(?://|/\s*/)\s*(?=\S)",
    re.UNICODE,
)
TITLE_WITH_ENTRY_RE = re.compile(
    r"^\s*(?P<entry>.+?)\s*//\s*(?P<rest>\S.*)$",
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
NAME_TOKEN_RE = r"[A-ZА-ЯЁІЎ][^\s,/.():;]+(?:[-'][^\s,/.():;]+)*"
SURNAME_INITIALS_RE = (
    rf"{NAME_TOKEN_RE}(?:\s+{NAME_TOKEN_RE})*,?(?:\s+[A-ZА-ЯЁІЎ]\.){{1,3}}"
)
INITIALS_SURNAME_RE = (
    rf"(?:[A-ZА-ЯЁІЎ]\.\s*){{1,3}}{NAME_TOKEN_RE}(?:\s+{NAME_TOKEN_RE})*"
)
QUOTED_SURNAME_INITIALS_RE = rf"[\"'«“„]?{SURNAME_INITIALS_RE}[\"'»”]?"
QUOTED_INITIALS_SURNAME_RE = rf"[\"'«“„]?{INITIALS_SURNAME_RE}[\"'»”]?"
AUTHOR_LIKE_RE = rf"(?:{QUOTED_SURNAME_INITIALS_RE}|{QUOTED_INITIALS_SURNAME_RE})"
AUTHOR_ENTRY_RESPONSIBLE_RE = re.compile(
    rf"^(?P<author>{AUTHOR_LIKE_RE})\s+(?P<entry>.+?)\s*/\s*(?P<responsible>{AUTHOR_LIKE_RE})$",
    re.UNICODE,
)
AUTHOR_ENTRY_RE = re.compile(
    rf"^(?P<author>{AUTHOR_LIKE_RE})\s+(?P<entry>.+)$",
    re.UNICODE,
)


@dataclass(frozen=True)
class PrefixComponents:
    entry: str
    author: str | None = None
    responsible: str | None = None


@dataclass(frozen=True)
class CandidateUnit:
    raw_text: str
    body: str
    prefix: str
    start: int
    end: int
    trailing_newline: str = ""


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


def _template_balance_delta(text: str) -> int:
    delta = 0
    for match in TEMPLATE_DELIMITER_RE.finditer(text):
        delta += 1 if match.group() == "{{" else -1
    return delta


def split_candidate_units(text: str) -> list[CandidateUnit]:
    units: list[CandidateUnit] = []
    lines = text.splitlines(keepends=True)
    index = 0
    offset = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped) :]
        match = REVIEW_LINE_PREFIX_RE.match(stripped)
        prefix = match.group("prefix") if match else ""
        body = match.group("body") if match else stripped
        start = offset

        if body.lstrip().startswith("{{"):
            block_parts = [body + newline]
            trailing_newline = newline
            balance = _template_balance_delta(body)
            end = offset + len(line)
            index += 1
            offset += len(line)

            while balance > 0 and index < len(lines):
                next_line = lines[index]
                block_parts.append(next_line)
                trailing_newline = next_line[len(next_line.rstrip("\r\n")) :]
                balance += _template_balance_delta(next_line)
                offset += len(next_line)
                end = offset
                index += 1

            raw_text = text[start:end]
            body_text = "".join(block_parts).rstrip("\r\n")
            units.append(
                CandidateUnit(
                    raw_text=raw_text,
                    body=body_text,
                    prefix=prefix,
                    start=start,
                    end=end,
                    trailing_newline=trailing_newline,
                )
            )
            continue

        end = offset + len(line)
        units.append(
            CandidateUnit(
                raw_text=line,
                body=body,
                prefix=prefix,
                start=start,
                end=end,
                trailing_newline=newline,
            )
        )
        index += 1
        offset += len(line)

    return units


def make_review_key(line: str, spec: SourceSpec) -> str:
    return normalize_review_line(line, spec).casefold()


def extract_template_param_value(
    text: str,
    spec: SourceSpec,
    param_names: tuple[str, ...],
    *,
    normalizer: str = "entry",
) -> str | None:
    normalized = normalize_biblio_wikitext(text, spec)
    patterns = []
    for name in param_names:
        canonical = normalize_whitespace(name)
        escaped = re.escape(canonical).replace(r"\ ", r"\s+")
        patterns.append(escaped)
    pattern = r"\|\s*(?:" + "|".join(patterns) + r")\s*=\s*(?P<value>[^|}]+)"
    match = re.search(pattern, normalized, flags=re.IGNORECASE | re.UNICODE)
    if not match:
        return None
    value = normalize_argument_value(match.group("value"), normalizer)
    return value or None


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


def _normalize_person_arg(value: str) -> str:
    value = normalize_whitespace(value)
    value = value.strip("\"'«»“”„")
    return value.strip()


def _parse_prefix_components(prefix: str, spec: SourceSpec) -> PrefixComponents | None:
    prefix = normalize_entry_arg(prefix)
    if not prefix or _looks_like_bibliography_prefix(prefix, spec):
        return None

    match = AUTHOR_ENTRY_RESPONSIBLE_RE.match(prefix)
    if match:
        entry = normalize_entry_arg(match.group("entry"))
        if entry and not _looks_like_bibliography_prefix(entry, spec):
            return PrefixComponents(
                entry=entry,
                author=_normalize_person_arg(match.group("author")),
                responsible=_normalize_person_arg(match.group("responsible")),
            )

    match = AUTHOR_ENTRY_RE.match(prefix)
    if match:
        entry = normalize_entry_arg(match.group("entry"))
        if entry and not _looks_like_bibliography_prefix(entry, spec):
            return PrefixComponents(
                entry=entry,
                author=_normalize_person_arg(match.group("author")),
            )

    return PrefixComponents(entry=prefix)


def extract_prefix_components(text: str, spec: SourceSpec) -> PrefixComponents | None:
    normalized = normalize_biblio_wikitext(
        re.sub(r"^\s*[*#;:]+\s*", "", text).strip(),
        spec,
    )
    match = ENTRY_LIST_PREFIX_RE.match(normalized)
    if not match:
        return None
    return _parse_prefix_components(match.group("entry"), spec)


def coalesce_entry_arg(
    group_value: str | None,
    extracted_value: str | None,
    spec: SourceSpec,
) -> str | None:
    if extracted_value:
        return extracted_value
    if not group_value:
        return None

    normalized = normalize_entry_arg(group_value)
    if not normalized or _looks_like_bibliography_prefix(normalized, spec):
        return None
    return normalized


def extract_entry_arg(text: str, spec: SourceSpec) -> str | None:
    raw = re.sub(r"^\s*[*#;:]+\s*", "", text).strip()
    entry = extract_template_param_value(
        raw,
        spec,
        ("частка", "раздзел", "chapter", "entry", "article", "артыкул"),
        normalizer="entry",
    )
    if entry:
        return entry or None

    normalized = normalize_biblio_wikitext(raw, spec)

    if normalized.startswith("{{"):
        title_value = extract_template_param_value(
            raw,
            spec,
            ("загаловак", "title"),
            normalizer="entry",
        )
        if title_value:
            match = TITLE_WITH_ENTRY_RE.match(title_value)
            if match:
                components = _parse_prefix_components(match.group("entry"), spec)
                if components and components.entry and len(components.entry) <= 200:
                    return components.entry
        return None

    components = extract_prefix_components(raw, spec)
    if components and len(components.entry) <= 200:
        return components.entry

    return None


def normalized_unit_variants(text: str, spec: SourceSpec) -> tuple[str, ...]:
    normalized = normalize_biblio_wikitext(text, spec)
    variants = [normalized]

    if normalized.startswith("{{"):
        def strip_title_entry(match: re.Match[str]) -> str:
            value = match.group("value")
            split = TITLE_WITH_ENTRY_RE.match(value)
            if not split:
                return match.group(0)

            entry = normalize_entry_arg(split.group("entry"))
            if not entry or _looks_like_bibliography_prefix(entry, spec):
                return match.group(0)

            stripped = normalize_whitespace(split.group("rest"))
            if not stripped:
                return match.group(0)
            return f"{match.group('prefix')}{stripped}"

        stripped_titles = TITLE_TEMPLATE_PARAM_RE.sub(
            strip_title_entry,
            normalized,
        )
        if stripped_titles != normalized:
            variants.append(stripped_titles)

    return tuple(dict.fromkeys(variants))


def extract_template_arguments(text: str, spec: SourceSpec) -> dict[str, str]:
    normalized = normalize_biblio_wikitext(text.strip(), spec)
    prefix_components = extract_prefix_components(text, spec)
    values: dict[str, str] = {}
    for extractor in spec.argument_extractors:
        value = extract_template_param_value(
            text,
            spec,
            extractor.template_params,
            normalizer=extractor.normalizer,
        )
        if not value:
            for pattern in extractor.patterns:
                match = pattern.search(normalized)
                if not match:
                    continue

                if "value" in match.re.groupindex:
                    raw_value = match.group("value")
                elif extractor.name in match.re.groupindex:
                    raw_value = match.group(extractor.name)
                elif match.groups():
                    raw_value = match.group(1)
                else:
                    continue

                value = normalize_argument_value(raw_value, extractor.normalizer)
                if value:
                    break
        if not value and prefix_components:
            if extractor.name == "author" and prefix_components.author:
                value = normalize_argument_value(prefix_components.author, extractor.normalizer)
            elif extractor.name == "responsible" and prefix_components.responsible:
                value = normalize_argument_value(
                    prefix_components.responsible,
                    extractor.normalizer,
                )
        if value:
            values[extractor.name] = value
    return values


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
