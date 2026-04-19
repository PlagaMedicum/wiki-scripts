from __future__ import annotations

import re
from dataclasses import dataclass

from biblio.models import SourceSpec
from biblio.utils import parse_regex_flags

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
SUSPICIOUS_PAGE_VALUE_RE = re.compile(
    r"(?:\b(?:с|стар)\.?\s*|\|\s*(?:старонкі|pages?|pp?)\s*=\s*)"
    r"\d+(?:\s*[—–-]\s*\d+)?\s*/\s*\d",
    re.IGNORECASE | re.UNICODE,
)
DOUBLE_HYPHEN_RANGE_RE = re.compile(r"(?<=\d)\s*--\s*(?=\d)")
DOUBLE_HYPHEN_DASH_RE = re.compile(r"(?<=\S)\s+--\s+(?=\S)")


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
        text = text.replace("\u00a0", " ")
    if options.normalize_dashes:
        text = DOUBLE_HYPHEN_RANGE_RE.sub("—", text)
        text = DOUBLE_HYPHEN_DASH_RE.sub(" — ", text)
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
    pages = DOUBLE_HYPHEN_RANGE_RE.sub("—", pages)
    pages = re.sub(r"\s*[—–-]\s*", "—", pages)
    pages = re.sub(r"\s*,\s*", ", ", pages)
    return pages.strip()


def has_suspicious_page_value(text: str, spec: SourceSpec) -> bool:
    normalized = normalize_biblio_wikitext(text, spec)
    return bool(SUSPICIOUS_PAGE_VALUE_RE.search(normalized))


def normalize_entry_arg(entry: str) -> str:
    entry = normalize_whitespace(entry)
    entry = re.sub(r"\s*[—–-]\s*", " — ", entry)
    entry = entry.strip(" \t\r\n,;:.")
    return entry


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_title_for_match(text: str) -> str:
    text = text.replace("_", " ").replace("\u00a0", " ")
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
    line = re.sub(
        rf"\b(?P<first>{INITIAL_TOKEN_RE})\s*(?P<second>{INITIAL_TOKEN_RE})",
        r"\g<first> \g<second>",
        line,
    )
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
INITIAL_TOKEN_RE = r"(?:[A-ZА-ЯЁІЎ]|Дз|Дж)\."
NAME_TOKEN_RE = r"[A-ZА-ЯЁІЎ][^\s,/.():;]+(?:[-'][^\s,/.():;]+)*"
SURNAME_INITIALS_RE = rf"{NAME_TOKEN_RE}(?:\s+{NAME_TOKEN_RE})*,?(?:\s+{INITIAL_TOKEN_RE}){{1,3}}"
INITIALS_SURNAME_RE = rf"(?:{INITIAL_TOKEN_RE}\s*){{1,3}}{NAME_TOKEN_RE}(?:\s+{NAME_TOKEN_RE})*"
QUOTED_SURNAME_INITIALS_RE = rf"[\"'«“„]?{SURNAME_INITIALS_RE}[\"'»”]?"
QUOTED_INITIALS_SURNAME_RE = rf"[\"'«“„]?{INITIALS_SURNAME_RE}[\"'»”]?"
AUTHOR_ITEM_RE = rf"(?:{QUOTED_SURNAME_INITIALS_RE}|{QUOTED_INITIALS_SURNAME_RE})"
AUTHOR_LIST_RE = rf"{AUTHOR_ITEM_RE}(?:\s*,\s*{AUTHOR_ITEM_RE})*"
AUTHOR_ENTRY_RESPONSIBLE_RE = re.compile(
    rf"^(?P<author>{AUTHOR_LIST_RE})\s+(?P<entry>.+?)\s*/\s*(?P<responsible>{AUTHOR_LIST_RE})$",
    re.UNICODE,
)
AUTHOR_ENTRY_RE = re.compile(
    rf"^(?P<author>{AUTHOR_LIST_RE})\s+(?P<entry>.+)$",
    re.UNICODE,
)
AUTHOR_LIST_FULL_RE = re.compile(
    rf"^{AUTHOR_LIST_RE}$",
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
    return [
        (kind, segment, open_tag, close_tag)
        for kind, segment, _, _, open_tag, close_tag in iter_ref_aware_segments(text)
    ]


def iter_ref_aware_segments(
    text: str,
) -> list[tuple[str, str, int, int, str | None, str | None]]:
    segments: list[tuple[str, str, int, int, str | None, str | None]] = []
    position = 0

    for match in REF_BODY_RE.finditer(text):
        if match.start() > position:
            segments.append(
                (
                    "text",
                    text[position : match.start()],
                    position,
                    match.start(),
                    None,
                    None,
                )
            )
        segments.append(
            (
                "ref",
                match.group("body"),
                match.start("body"),
                match.end("body"),
                match.group("open"),
                match.group("close"),
            )
        )
        position = match.end()

    if position < len(text) or not segments:
        segments.append(("text", text[position:], position, len(text), None, None))

    return segments


def build_match_excerpt(
    text: str,
    *,
    match_start: int,
    match_end: int,
    context_lines: int = 1,
) -> tuple[str, int, int]:
    if match_start < 0 or match_end < match_start or match_end > len(text):
        raise ValueError("Invalid match bounds for source excerpt.")

    if not text:
        return "", 0, 0

    def line_start(position: int) -> int:
        if position <= 0:
            return 0
        return text.rfind("\n", 0, position) + 1

    def line_end(position: int) -> int:
        if position >= len(text):
            return len(text)
        newline = text.find("\n", position)
        return len(text) if newline == -1 else newline

    excerpt_start = line_start(match_start)
    for _ in range(context_lines):
        if excerpt_start == 0:
            break
        excerpt_start = line_start(excerpt_start - 1)

    anchor_end = match_start if match_end == match_start else match_end - 1
    excerpt_end = line_end(anchor_end)
    for _ in range(context_lines):
        if excerpt_end >= len(text):
            break
        excerpt_end = line_end(excerpt_end + 1)

    excerpt = text[excerpt_start:excerpt_end]
    return excerpt, match_start - excerpt_start, match_end - excerpt_start


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


def _match_author_entry_with_page_title(
    prefix: str,
    page_title: str,
) -> tuple[str, str] | None:
    normalized_prefix = normalize_whitespace(prefix)
    normalized_title = normalize_whitespace(page_title)
    if (
        not normalized_prefix
        or not normalized_title
        or not normalized_prefix.casefold().endswith(normalized_title.casefold())
    ):
        return None

    author_part = normalized_prefix[: -len(normalized_title)].rstrip()
    author_candidates = [
        author_part.rstrip(" ,;:/"),
        author_part.rstrip(" ,;:/."),
    ]
    for candidate in author_candidates:
        if candidate and AUTHOR_LIST_FULL_RE.fullmatch(candidate):
            return candidate, normalized_title

    return None


def _parse_prefix_components(
    prefix: str,
    spec: SourceSpec,
    page_title: str | None = None,
) -> PrefixComponents | None:
    prefix = normalize_entry_arg(prefix)
    if not prefix or _looks_like_bibliography_prefix(prefix, spec):
        return None

    if page_title:
        split = re.split(r"\s*/\s*", prefix, maxsplit=1)
        if len(split) == 2 and AUTHOR_LIST_FULL_RE.fullmatch(split[1]):
            matched = _match_author_entry_with_page_title(split[0], page_title)
            if matched:
                author, entry = matched
                return PrefixComponents(
                    entry=entry,
                    author=_normalize_person_arg(author),
                    responsible=_normalize_person_arg(split[1]),
                )

        matched = _match_author_entry_with_page_title(prefix, page_title)
        if matched:
            author, entry = matched
            return PrefixComponents(
                entry=entry,
                author=_normalize_person_arg(author),
            )

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


def extract_prefix_components(
    text: str,
    spec: SourceSpec,
    page_title: str | None = None,
) -> PrefixComponents | None:
    normalized = normalize_biblio_wikitext(
        re.sub(r"^\s*[*#;:]+\s*", "", text).strip(),
        spec,
    )
    match = ENTRY_LIST_PREFIX_RE.match(normalized)
    if not match:
        return None
    return _parse_prefix_components(match.group("entry"), spec, page_title)


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


def extract_entry_arg(
    text: str,
    spec: SourceSpec,
    page_title: str | None = None,
) -> str | None:
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
                components = _parse_prefix_components(match.group("entry"), spec, page_title)
                if components and components.entry and len(components.entry) <= 200:
                    return components.entry
        return None

    components = extract_prefix_components(raw, spec, page_title)
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


def extract_template_arguments(
    text: str,
    spec: SourceSpec,
    page_title: str | None = None,
) -> dict[str, str]:
    normalized = normalize_biblio_wikitext(text.strip(), spec)
    prefix_components = extract_prefix_components(text, spec, page_title)
    values: dict[str, str] = {}
    for extractor in spec.argument_extractors:
        value = extract_template_param_value(
            text,
            spec,
            extractor.template_params,
            normalizer=extractor.normalizer,
        )
        if not value and prefix_components and page_title:
            if extractor.name == "author" and prefix_components.author:
                value = normalize_argument_value(prefix_components.author, extractor.normalizer)
            elif extractor.name == "responsible" and prefix_components.responsible:
                value = normalize_argument_value(
                    prefix_components.responsible,
                    extractor.normalizer,
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
            if re.match(r"\s*/", normalized[match.end("pages") :]):
                continue
            pages = normalize_pages_arg(match.group("pages"))
            tail = normalized[match.end() : match.end() + 20]

            if any(reject_pattern.search(tail) for reject_pattern in spec.reject_patterns):
                continue

            score = 0
            if match.start() < 12:
                score += 2
            if match.end() > len(normalized) - 12:
                score += 2
            if (
                "isbn"
                in normalized[
                    max(0, match.start() - 40) : min(len(normalized), match.end() + 40)
                ].casefold()
            ):
                score += 1

            candidates.append((score, pages))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]
