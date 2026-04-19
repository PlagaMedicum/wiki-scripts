from __future__ import annotations

import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from biblio.models import ImportedTemplateFacts, ImportedVolumeFacts, TemplateRoleParams

_KNOWN_TEMPLATE_ROLES = (
    ("volume", "том"),
    ("entry", "частка"),
    ("author", "аўтар"),
    ("pages", "старонкі"),
    ("responsible", "частка адказны"),
    ("ref", "ref"),
)
_CANONICAL_VOLUME_RE = re.compile(r"^\d+(?:-\d+)?$")
_TEMPLATE_NAMESPACE_RE = re.compile(r"^(?:Шаблон|Template):", re.IGNORECASE)
_NUMERIC_PARAM_RE = re.compile(r"^\d+$")


def fetch_template_raw(
    template_title: str,
    *,
    site_lang: str,
    family: str,
    timeout: float = 20.0,
) -> str:
    encoded_title = quote(template_title, safe="")
    url = f"https://{site_lang}.{family}.org/w/index.php?title={encoded_title}&action=raw"
    request = Request(
        url,
        headers={
            "User-Agent": "biblio-add-source/0.1 (+https://be.wikipedia.org/)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def template_raw_url(
    template_title: str,
    *,
    site_lang: str,
    family: str,
) -> str:
    encoded_title = quote(template_title, safe="")
    return f"https://{site_lang}.{family}.org/w/index.php?title={encoded_title}&action=raw"


def parse_template_facts(
    template_title: str,
    raw_text: str,
) -> ImportedTemplateFacts:
    body = _strip_noinclude(raw_text)
    docs = _extract_noinclude(raw_text)
    role_params = _extract_known_role_params(body) or _extract_known_role_params(docs)
    extra_params = tuple(
        param
        for param in _collect_template_params(body)
        if param not in _known_param_names(role_params)
    )
    title_field = _extract_field_value(body, "загаловак") or _extract_field_value(docs, "загаловак")
    title_seed = _extract_first_wikilink(title_field) or _strip_template_namespace(template_title)
    volume_titles = _extract_volume_titles(body, docs)
    year_map = _extract_switch_map(body, "год") or _extract_switch_map(docs, "год")
    isbn_map = (
        _extract_switch_map(body, "isbn том")
        or _extract_switch_map(docs, "isbn том")
        or _extract_switch_map(body, "isbn")
        or _extract_switch_map(docs, "isbn")
    )
    volumes = tuple(
        ImportedVolumeFacts(
            volume=volume,
            title=title,
            year=year_map.get(volume),
            isbn=isbn_map.get(volume),
        )
        for volume, title in _sorted_canonical_items(volume_titles)
    )
    ref_default = _extract_ref_default(body) or _extract_ref_default(docs)
    merged_role_params = []
    for binding in role_params:
        if binding.role == "ref" and ref_default:
            merged_role_params.append(
                TemplateRoleParams(
                    role=binding.role,
                    params=binding.params,
                    default=ref_default,
                )
            )
            continue
        merged_role_params.append(binding)
    return ImportedTemplateFacts(
        template_title=template_title,
        template_name=_strip_template_namespace(template_title),
        source_search_seed=(title_seed,) if title_seed else (),
        role_params=tuple(merged_role_params),
        volumes=volumes,
        extra_params=extra_params,
        raw_text=raw_text,
    )


def build_imported_template_forms(
    template_name: str,
    role_params: tuple[TemplateRoleParams, ...],
    *,
    single_volume: bool,
) -> tuple[str, str]:
    without_pages = _build_template_form(
        template_name,
        role_params,
        include_pages=False,
        single_volume=single_volume,
    )
    with_pages = _build_template_form(
        template_name,
        role_params,
        include_pages=True,
        single_volume=single_volume,
    )
    return without_pages, with_pages


def _strip_noinclude(raw_text: str) -> str:
    return re.sub(r"<noinclude>.*?</noinclude>", "", raw_text, flags=re.IGNORECASE | re.DOTALL)


def _extract_noinclude(raw_text: str) -> str:
    return "\n".join(
        re.findall(r"<noinclude>(.*?)</noinclude>", raw_text, flags=re.IGNORECASE | re.DOTALL)
    )


def _strip_template_namespace(title: str) -> str:
    return _TEMPLATE_NAMESPACE_RE.sub("", title).strip()


def _extract_field_value(raw_text: str, field_name: str) -> str:
    pattern = re.compile(
        rf"^\|{re.escape(field_name)}\s*=\s*(?P<value>.*?)(?=^\|[^\s].*?=|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(raw_text)
    if not match:
        return ""
    return match.group("value").strip()


def _extract_aliases(value: str) -> tuple[str, ...]:
    seen: set[str] = set()
    aliases: list[str] = []
    for alias in re.findall(r"\{\{\{([^|{}]+)", value):
        cleaned = alias.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            aliases.append(cleaned)
    return tuple(aliases)


def _extract_known_role_params(raw_text: str) -> tuple[TemplateRoleParams, ...]:
    bindings: list[TemplateRoleParams] = []
    for role, field_name in _KNOWN_TEMPLATE_ROLES:
        aliases = _extract_aliases(_extract_field_value(raw_text, field_name))
        if aliases:
            bindings.append(TemplateRoleParams(role=role, params=aliases))
    return tuple(bindings)


def _collect_template_params(raw_text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    params: list[str] = []
    for param in re.findall(r"\{\{\{([^|{}]+)", raw_text):
        cleaned = param.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            params.append(cleaned)
    return tuple(params)


def _known_param_names(bindings: tuple[TemplateRoleParams, ...]) -> set[str]:
    return {param for binding in bindings for param in binding.params}


def _extract_first_wikilink(value: str) -> str | None:
    match = re.search(r"\[\[([^\]|]+)", value)
    if not match:
        return None
    return match.group(1).strip()


def _extract_ref_default(raw_text: str) -> str | None:
    value = _extract_field_value(raw_text, "ref")
    match = re.search(r"\{\{\{[^|{}]+\|([^{}]+)\}\}\}", value)
    if not match:
        return None
    return match.group(1).strip()


def _extract_switch_map(raw_text: str, field_name: str) -> dict[str, str]:
    value = _extract_field_value(raw_text, field_name)
    if "{{#switch:" not in value:
        return {}
    start = re.search(r"\|[^\n=|{}]+(?:\|[^\n=|{}]+)*\s*=", value)
    if not start:
        return {}
    body = value[start.start() :]
    body = re.sub(r"\}\}\s*$", "", body.strip(), flags=re.DOTALL)
    body = re.sub(
        r"\s+\|(?=[^\n=|{}]+(?:\|[^\n=|{}]+)*\s*=)",
        "\n|",
        body,
    )
    mapping: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|") or "=" not in line:
            continue
        keys_part, raw_value = line[1:].split("=", 1)
        value_text = raw_value.strip()
        for key in (part.strip() for part in keys_part.split("|")):
            if key:
                mapping[key] = value_text
    return mapping


def _extract_volume_titles(body: str, docs: str) -> dict[str, str]:
    title_switch = _extract_switch_map(body, "загаловак") or _extract_switch_map(docs, "загаловак")
    if len(_sorted_canonical_items(title_switch)) > 1:
        return title_switch
    tom_switch = _extract_switch_map(body, "том") or _extract_switch_map(docs, "том")
    if tom_switch:
        return tom_switch
    return title_switch


def _build_template_form(
    template_name: str,
    role_params: tuple[TemplateRoleParams, ...],
    *,
    include_pages: bool,
    single_volume: bool,
) -> str:
    lookup = {binding.role: binding for binding in role_params}
    placeholders = {
        "volume": "{volume}",
        "entry": "{entry}",
        "pages": "{pages}",
        "author": "{author}",
        "responsible": "{responsible}",
    }
    active_roles = []
    for role in ("volume", "entry", "pages", "author", "responsible"):
        if role == "volume" and single_volume:
            continue
        if role == "pages" and not include_pages:
            continue
        binding = lookup.get(role)
        if binding and binding.params:
            active_roles.append(role)
    positional: dict[int, str] = {}
    named: list[str] = []
    for role in active_roles:
        binding = lookup[role]
        numeric_index = _numeric_param_index(binding.params)
        if numeric_index is not None:
            positional[numeric_index] = placeholders[role]
            continue
        named_alias = _named_param_alias(binding.params)
        if named_alias:
            named.append(f"{named_alias}={placeholders[role]}")
    parts = [template_name]
    if positional:
        max_index = max(positional)
        for index in range(1, max_index + 1):
            parts.append(positional.get(index, ""))
    parts.extend(named)
    return "{{" + "|".join(parts) + "}}"


def _numeric_param_index(params: tuple[str, ...]) -> int | None:
    for param in params:
        if _NUMERIC_PARAM_RE.fullmatch(param):
            return int(param)
    return None


def _named_param_alias(params: tuple[str, ...]) -> str | None:
    for param in params:
        if not _NUMERIC_PARAM_RE.fullmatch(param):
            return param
    return None


def _sorted_canonical_items(mapping: dict[str, str]) -> tuple[tuple[str, str], ...]:
    canonical = [
        (key, value) for key, value in mapping.items() if _CANONICAL_VOLUME_RE.fullmatch(key)
    ]
    return tuple(sorted(canonical, key=lambda item: _volume_sort_key(item[0])))


def _volume_sort_key(value: str) -> tuple[int, int]:
    if "-" not in value:
        return (int(value), 0)
    head, tail = value.split("-", 1)
    return (int(head), int(tail))
