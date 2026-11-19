from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

RASTER_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".webp", ".bmp"})

_WS_RUN = re.compile(r"[ _\u00a0]+")
_LINK = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)
_TEMPLATE_TOKEN = re.compile(r"\{\{|\}\}")
_URL = re.compile(r"https?://[^\s\[\]|<>]+", re.IGNORECASE)
_VECTOR_TEMPLATE = re.compile(
    r"\{\{[ \t\n]*(?:subst[ \t\n]*:[ \t\n]*)?"
    r"(?:vector[ \t\n]+version[ \t\n]+available|vva)(?=[ \t\n|}])",
    re.IGNORECASE,
)
_LITERAL = re.compile(
    r"<!--.*?(?:-->|\Z)|"
    r"<(?P<tag>nowiki|pre|syntaxhighlight|source|math|score|timeline|graph|templatedata)\b"
    r"""(?:[^>"']|"[^"]*"|'[^']*')*"""
    r"(?<!/)>.*?(?:</(?P=tag)\s*>|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_URL_JUNK = " \t\r\n).,;'\""


def normalize_file_name(name: str) -> str:
    """Approximate MediaWiki file-title normalization for safe comparison."""
    text = unicodedata.normalize("NFC", name)
    text = _WS_RUN.sub(" ", text).strip()
    if text:
        text = text[0].upper() + text[1:]
    return text


def _canonical_case(name: str) -> str:
    return name[:1].upper() + name[1:] if name else name


@dataclass(frozen=True)
class FileNamespace:
    """Namespace names that address the file (namespace 6) on one wiki."""

    aliases: frozenset[str]

    @classmethod
    def of(cls, *names: str) -> FileNamespace:
        return cls(frozenset(_canonical_case(name) for name in names))

    @classmethod
    def from_siteinfo(
        cls,
        namespaces: dict[str, dict],
        namespace_aliases: list[dict],
    ) -> FileNamespace:
        info = namespaces.get("6") or {}
        names = {info.get(key) for key in ("name", "canonical") if info.get(key)}
        names.update(
            entry["alias"]
            for entry in namespace_aliases
            if entry.get("id") == 6 and entry.get("alias")
        )
        return cls(frozenset(_canonical_case(name) for name in names))

    def matches(self, prefix: str) -> bool:
        return _canonical_case(prefix.strip()) in self.aliases


@dataclass(frozen=True)
class FileLink:
    start: int
    end: int
    name_start: int
    name_end: int
    alias: str
    name: str
    options: str | None
    template_depth: int
    unsafe_reason: str | None


def _template_depth(text: str, pos: int) -> int:
    depth = 0
    for token in _TEMPLATE_TOKEN.finditer(text, 0, pos):
        depth += 1 if token.group() == "{{" else -1
        if depth < 0:
            depth = 0
    return depth


def find_file_links(text: str, ns: FileNamespace) -> list[FileLink]:
    literal_spans = [(match.start(), match.end()) for match in _LITERAL.finditer(text)]
    # Preserve offsets while hiding literal braces from template-depth accounting.
    masked = _LITERAL.sub(lambda match: " " * len(match.group()), text)
    links: list[FileLink] = []
    for match in _LINK.finditer(text):
        body = match.group(1)
        offset = match.start(1)
        if body.startswith(":"):
            body = body[1:]
            offset += 1
        if "|" in body:
            target_part, options = body.split("|", 1)
        else:
            target_part, options = body, None
        colon = target_part.find(":")
        if colon < 0:
            continue
        alias = target_part[:colon]
        if not ns.matches(alias):
            continue
        rest = target_part[colon + 1 :]
        rest_start = offset + colon + 1
        lead = len(rest) - len(rest.lstrip())
        core_end = len(rest.rstrip())
        if core_end <= lead:
            continue
        core = rest[lead:core_end]
        hash_pos = core.find("#")
        name_len = hash_pos if hash_pos >= 0 else len(core)
        name_start = rest_start + lead
        name_end = name_start + name_len
        links.append(
            FileLink(
                start=match.start(),
                end=match.end(),
                name_start=name_start,
                name_end=name_end,
                alias=alias.strip(),
                name=text[name_start:name_end],
                options=options,
                template_depth=_template_depth(masked, match.start()),
                unsafe_reason=(
                    "inside a comment or literal-content tag"
                    if any(start <= match.start() < end for start, end in literal_spans)
                    else None
                ),
            )
        )
    return links


@dataclass(frozen=True)
class Assessment:
    raster: str
    matches: list[FileLink]
    blocked: list[tuple[FileLink, str]]

    @property
    def status(self) -> str:
        if self.blocked:
            return "blocked"
        if self.matches:
            return "replace"
        return "indirect"

    @property
    def blocked_reason(self) -> str:
        reasons = dict.fromkeys(reason for _link, reason in self.blocked)
        return "; ".join(reasons)


def assess_usage(text: str, raster_name: str, ns: FileNamespace) -> Assessment:
    target = normalize_file_name(raster_name)
    matches: list[FileLink] = []
    blocked: list[tuple[FileLink, str]] = []
    for link in find_file_links(text, ns):
        if normalize_file_name(link.name) != target:
            continue
        if link.template_depth > 0:
            blocked.append((link, "transcluded through a template"))
        elif link.unsafe_reason is not None:
            blocked.append((link, link.unsafe_reason))
        else:
            matches.append(link)
    return Assessment(raster=raster_name, matches=matches, blocked=blocked)


def replace_matches(text: str, matches: list[FileLink], svg_name: str) -> str:
    """Rewrite only the filename spans of already-assessed matches."""
    new_text = text
    for link in sorted(matches, key=lambda item: item.name_start, reverse=True):
        new_text = new_text[: link.name_start] + svg_name + new_text[link.name_end :]
    return new_text


def replace_usage(text: str, raster_name: str, svg_name: str, ns: FileNamespace) -> tuple[str, int]:
    assessment = assess_usage(text, raster_name, ns)
    if assessment.status != "replace":
        raise ValueError(
            f"usage of {raster_name!r} is not safely replaceable (status: {assessment.status})"
        )
    return replace_matches(text, assessment.matches, svg_name), len(assessment.matches)


def usage_context(text: str, needle: str, *, limit: int = 3, width: int = 160) -> list[str]:
    needles = {needle, needle.replace(" ", "_"), needle.replace("_", " ")}
    lines: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not any(candidate in line for candidate in needles):
            continue
        trimmed = line.strip()
        if len(trimmed) > width:
            trimmed = trimmed[: width - 1] + "…"
        lines.append(f"{number}: {trimmed}")
        if len(lines) >= limit:
            break
    return lines


def has_vector_template(text: str) -> bool:
    return _VECTOR_TEMPLATE.search(text) is not None


def add_vector_template(text: str, svg_name: str) -> str:
    return f"{{{{Vector version available|{svg_name}}}}}\n{text}"


def _raster_extension(name: str) -> str | None:
    dot = name.rfind(".")
    if dot <= 0:
        return None
    extension = name[dot:].lower()
    return extension if extension in RASTER_EXTENSIONS else None


@dataclass(frozen=True)
class RasterCandidate:
    name: str
    origin: str
    evidence: str


_ORIGIN_PRIORITY = {
    "file link": 0,
    "Commons file URL": 1,
    "upload URL": 2,
    "external URL": 3,
}


def _raster_from_url(url: str, ns: FileNamespace) -> tuple[str, str] | None:
    parts = urlsplit(url.rstrip(_URL_JUNK))
    host = parts.netloc.lower()
    if host == "commons.wikimedia.org":
        title = None
        if parts.path.startswith("/wiki/"):
            title = unquote(parts.path[len("/wiki/") :])
        elif parts.path.endswith("/index.php"):
            title = (parse_qs(parts.query).get("title") or [None])[0]
        if title and ":" in title:
            prefix, _, name = title.partition(":")
            if ns.matches(prefix):
                return name, "Commons file URL"
        return None
    if host == "upload.wikimedia.org":
        name = unquote(parts.path.rsplit("/", 1)[-1])
        if _raster_extension(name):
            return name, "upload URL"
        return None
    name = unquote(parts.path.rsplit("/", 1)[-1])
    if _raster_extension(name):
        return name, "external URL"
    return None


def discover_raster_candidates(text: str, ns: FileNamespace) -> list[RasterCandidate]:
    """Find raster files referenced by an SVG page's source/derivation info."""
    found: dict[str, RasterCandidate] = {}

    def add(name: str, origin: str, evidence: str) -> None:
        if not _raster_extension(name):
            return
        key = normalize_file_name(name)
        candidate = RasterCandidate(name=name, origin=origin, evidence=evidence)
        if key not in found or _ORIGIN_PRIORITY[origin] < _ORIGIN_PRIORITY[found[key].origin]:
            found[key] = candidate

    for link in find_file_links(text, ns):
        add(link.name, "file link", text[link.start : link.end])
    for url in _URL.findall(text):
        parsed = _raster_from_url(url, ns)
        if parsed:
            add(parsed[0], parsed[1], url)

    return list(found.values())
