from __future__ import annotations

import difflib
import re
import tomllib
from pathlib import Path

from biblio.models import (
    AliasRule,
    ArgumentExtractor,
    CandidateSpec,
    NormalizationOptions,
    RegexRule,
    ShortRefSpec,
    SourceSpec,
    SourceValidationIssue,
)
from biblio.source_templates import validate_template_placeholders
from biblio.utils import expand_macro_template, parse_regex_flags

BUILTIN_MACROS = {
    "LIST_PREFIX": r"\s*(?:[*#;:]+\s*)?",
    "WS": r"\s+",
    "OPT_WS": r"\s*",
    "SEP": r"\s*(?:[,;:/])\s*",
    "DASH": r"\s*(?:[—–]|-{1,2})\s*",
    "OPT_DASH": r"(?:\s*(?:[—–]|-{1,2})\s*)?",
    "INITIAL": r"(?:[A-ZА-ЯЁІЎ]|Дз|Дж)\.",
    "PAGES": r"\d+(?:\s*(?:[—–]|-{1,2})\s*\d+)?(?:\s*,\s*\d+(?:\s*(?:[—–]|-{1,2})\s*\d+)?)*",
    "YEAR4": r"(?:19|20)\d{2}",
    "ISBN_TOKEN": r"ISBN\s*\d[\d-]+",
}

DEFAULT_PAGE_PATTERNS = (
    r"\b(?:с|стар)\.{{OPT_WS}}(?P<pages>{{PAGES}})",
    r"\|{{OPT_WS}}(?:старонкі|pages?|pp?){{OPT_WS}}={{OPT_WS}}(?P<pages>{{PAGES}})(?={{OPT_WS}}(?:\||\}\}))",
)

DEFAULT_REJECT_PATTERNS = (r"^\s*:\s*іл",)

PERSISTENT_SOURCE_FILENAMES = ("source.toml",)

RUNTIME_STATE_FILENAMES = (
    "rules.json",
    "review_variants.json",
    "ignored_variants.json",
)

COMMON_FILENAME_ALIASES = {
    "source.yaml": "source.toml",
    "source.yml": "source.toml",
    "source.json": "source.toml",
    "rule.json": "rules.json",
    "reviews.json": "review_variants.json",
    "review.json": "review_variants.json",
    "ignored.json": "ignored_variants.json",
}

SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PLACEHOLDER_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REGEX_RULE_REPLACEMENT_FIELDS = {
    "entry",
    "pages",
    "prefix",
    "source_id",
    "template",
    "template_name",
}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def source_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "sources"


def validate_source_id(source_id: str) -> None:
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("Source IDs must use lowercase ASCII letters, digits, and hyphens.")


def discover_source_specs(root: Path | None = None) -> list[SourceSpec]:
    actual_root = root or project_root()
    specs: list[SourceSpec] = []
    for path in sorted(source_root(actual_root).glob("*/source.toml")):
        specs.append(_load_source_spec_from_dir(path.parent, actual_root))
    hidden_alias_ids = {
        alias for spec in specs for variant in spec.volume_variants for alias in variant.aliases
    }
    return [spec for spec in specs if spec.source_id not in hidden_alias_ids]


def validate_source_layouts(root: Path | None = None) -> list[SourceValidationIssue]:
    actual_root = root or project_root()
    sources_dir = source_root(actual_root)
    issues: list[SourceValidationIssue] = []

    if not sources_dir.exists():
        issues.append(
            SourceValidationIssue(
                source_name="sources",
                path=sources_dir,
                message="Missing sources/ directory.",
            )
        )
        return issues

    for child in sorted(sources_dir.iterdir()):
        if child.is_file():
            issues.append(
                SourceValidationIssue(
                    source_name="sources",
                    path=child,
                    message="Unexpected file in sources root; expected only source directories.",
                )
            )
            continue

        if not child.is_dir():
            continue

        try:
            validate_source_id(child.name)
        except ValueError as exc:
            issues.append(
                SourceValidationIssue(
                    source_name=child.name,
                    path=child,
                    message=str(exc),
                )
            )

        names = {item.name for item in child.iterdir() if item.is_file()}
        lowered = {name.lower(): name for name in names}

        for required in PERSISTENT_SOURCE_FILENAMES:
            if required in names:
                continue

            alias_candidate = next(
                (name for name in names if COMMON_FILENAME_ALIASES.get(name.lower()) == required),
                None,
            )
            if alias_candidate:
                candidate = alias_candidate
            elif required.lower() in lowered:
                candidate = lowered[required.lower()]
            else:
                close = difflib.get_close_matches(required, names, n=1, cutoff=0.65)
                candidate = close[0] if close else None

            issues.append(
                SourceValidationIssue(
                    source_name=child.name,
                    path=child / required,
                    message=f"Missing required file: {required}",
                    suggestion=(
                        f"Rename {candidate} to {required}" if candidate else f"Create {required}"
                    ),
                )
            )

        if "source.toml" in names:
            try:
                load_source_spec(child.name, root=actual_root)
            except Exception as exc:
                issues.append(
                    SourceValidationIssue(
                        source_name=child.name,
                        path=child / "source.toml",
                        message=f"Invalid source.toml: {exc}",
                    )
                )

    return issues


def _require_table(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid [{key}] section")
    return value


def _require_string(data: dict, key: str, section: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid {section}.{key}")
    return value


def _string_list(data: dict, key: str) -> tuple[str, ...]:
    values = data.get(key, [])
    if not isinstance(values, (list, tuple)) or not all(isinstance(item, str) for item in values):
        raise ValueError(f"Expected a string list for {key}")
    return tuple(values)


def _require_bool(data: dict, key: str, section: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Expected a boolean for {section}.{key}")
    return value


def _load_macro_map(data: dict) -> dict[str, str]:
    macros = dict(BUILTIN_MACROS)
    local_macros = data.get("macros", {})
    if not isinstance(local_macros, dict):
        raise ValueError("Missing or invalid [macros] section")

    for key, value in local_macros.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Macro {key!r} must be a non-empty string")
        if key in BUILTIN_MACROS:
            raise ValueError(f"Macro {key!r} is reserved")
        macros[key] = value

    return macros


def _compile_regex_rules(
    rule_defs: list,
    macros: dict[str, str],
    allowed_fields: set[str],
) -> tuple[RegexRule, ...]:
    regex_rules: list[RegexRule] = []
    for item in rule_defs:
        if not isinstance(item, dict):
            raise ValueError("Each regex_rules entry must be a table")

        name = _require_string(item, "name", "regex_rules")
        pattern_template = _require_string(item, "pattern", "regex_rules")
        flags = item.get("flags", "")
        if not isinstance(flags, str):
            raise ValueError(f"regex_rules.{name}.flags must be a string")
        enabled = _require_bool(item, "enabled", f"regex_rules.{name}", True)
        review_required = _require_bool(item, "review_required", f"regex_rules.{name}", False)
        pattern = expand_macro_template(pattern_template, macros)
        compiled = re.compile(pattern, parse_regex_flags(flags))
        replacement = _require_string(item, "replacement", "regex_rules")
        validate_template_placeholders(
            replacement,
            allowed_fields | set(compiled.groupindex) | REGEX_RULE_REPLACEMENT_FIELDS,
            context=f"regex_rules.{name}.replacement",
        )
        review_note = item.get("review_note", "")
        if not isinstance(review_note, str):
            raise ValueError(f"regex_rules.{name}.review_note must be a string")
        regex_rules.append(
            RegexRule(
                name=name,
                pattern_template=pattern_template,
                pattern=pattern,
                replacement=replacement,
                flags=flags,
                enabled=enabled,
                review_required=review_required,
                review_note=review_note.strip(),
                compiled=compiled,
            )
        )
    return tuple(regex_rules)


def _load_argument_extractors(
    data: dict,
    macros: dict[str, str],
) -> tuple[ArgumentExtractor, ...]:
    raw = data.get("argument_extractors", {})
    if not isinstance(raw, dict):
        raise ValueError("Missing or invalid [argument_extractors] section")

    extractors: list[ArgumentExtractor] = []
    for name, config in raw.items():
        if not isinstance(config, dict):
            raise ValueError(f"argument_extractors.{name} must be a table")
        if not PLACEHOLDER_NAME_RE.fullmatch(name):
            raise ValueError(f"argument_extractors name {name!r} is not a valid placeholder")
        if name in REGEX_RULE_REPLACEMENT_FIELDS:
            raise ValueError(f"argument_extractors name {name!r} is reserved")
        template_params = _string_list(config, "template_params")
        pattern_templates = _string_list(config, "patterns")
        if not template_params and not pattern_templates:
            raise ValueError(f"argument_extractors.{name} must define template_params or patterns")
        normalizer = config.get("normalizer", "entry")
        if normalizer not in {"entry", "pages", "whitespace", "raw"}:
            raise ValueError(
                f"argument_extractors.{name}.normalizer must be one of entry, pages, whitespace, raw"
            )
        extractors.append(
            ArgumentExtractor(
                name=name,
                template_params=template_params,
                patterns=_compile_patterns(
                    pattern_templates,
                    macros,
                    flags=re.UNICODE | re.IGNORECASE | re.MULTILINE,
                ),
                normalizer=normalizer,
            )
        )
    return tuple(extractors)


def _compile_patterns(
    patterns: tuple[str, ...],
    macros: dict[str, str],
    *,
    flags: int,
) -> tuple[re.Pattern[str], ...]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        compiled.append(re.compile(expand_macro_template(pattern, macros), flags))
    return tuple(compiled)


def _merge_terms(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for group in groups:
        for value in group:
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                values.append(cleaned)
    return tuple(values)


def _load_short_ref(data: dict | None, *, context: str) -> ShortRefSpec | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"Missing or invalid [{context}] section")
    return ShortRefSpec(
        ref=_require_string(data, "ref", context),
        year=_require_string(data, "year", context),
    )


def _merge_macros(
    base_macros: dict[str, str],
    overrides: dict,
    *,
    context: str,
) -> dict[str, str]:
    merged = dict(base_macros)
    if not isinstance(overrides, dict):
        raise ValueError(f"Missing or invalid [{context}] section")
    for key, value in overrides.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{context}.{key} must be a non-empty string")
        if key in BUILTIN_MACROS:
            raise ValueError(f"{context}.{key!r} is reserved")
        merged[key] = value
    return merged


def _build_source_spec(
    *,
    source_dir: Path,
    source_id: str,
    name: str,
    site_lang: str,
    family: str,
    search_terms: dict,
    candidate_terms: dict,
    replacement: dict,
    summary: dict,
    pages: dict,
    normalization: dict,
    data: dict,
    macros: dict[str, str],
    short_ref: ShortRefSpec | None,
    volume: str | None = None,
    aliases: tuple[str, ...] = (),
    volume_variants: tuple[SourceSpec, ...] = (),
    compile_regex_rules: bool = True,
) -> SourceSpec:
    template_without_pages = _require_string(replacement, "without_pages", "replacement")
    template_with_pages = _require_string(replacement, "with_pages", "replacement")
    if template_with_pages.count("{pages}") != 1:
        raise ValueError("replacement.with_pages must contain {pages} exactly once")
    if "{pages}" in template_without_pages:
        raise ValueError("replacement.without_pages must not contain {pages}")

    default_summary_format = _require_string(summary, "default_format", "summary")
    if "{template_name}" not in default_summary_format:
        raise ValueError("summary.default_format must include {template_name}")

    argument_extractors = _load_argument_extractors(data, macros)
    allowed_template_fields = {"entry", "pages"} | {
        extractor.name for extractor in argument_extractors
    }
    if volume is not None or volume_variants:
        allowed_template_fields.add("volume")
    validate_template_placeholders(
        template_without_pages,
        allowed_template_fields,
        context="replacement.without_pages",
        disallowed_fields={"pages"},
    )
    validate_template_placeholders(
        template_with_pages,
        allowed_template_fields,
        context="replacement.with_pages",
        required_fields={"pages"},
    )
    validate_template_placeholders(
        default_summary_format,
        {"template_name"},
        context="summary.default_format",
        required_fields={"template_name"},
    )
    regex_rules = (
        _compile_regex_rules(
            data.get("regex_rules", []),
            macros,
            allowed_template_fields,
        )
        if compile_regex_rules
        else ()
    )

    alias_rules: list[AliasRule] = []
    for item in normalization.get("alias_replacements", []):
        if not isinstance(item, dict):
            raise ValueError("Each normalization.alias_replacements entry must be a table")
        alias_rules.append(
            AliasRule(
                pattern=_require_string(item, "pattern", "normalization.alias_replacements"),
                replacement=_require_string(
                    item,
                    "replacement",
                    "normalization.alias_replacements",
                ),
                flags=item.get("flags", ""),
            )
        )

    insource_terms = _string_list(search_terms, "insource_terms")
    isbns = _string_list(search_terms, "isbns")
    keywords = _string_list(search_terms, "keywords")
    if not (insource_terms or isbns or keywords):
        raise ValueError("[search] must define at least one term")

    must_contain_all = _string_list(candidate_terms, "must_contain_all")
    must_contain_any = _string_list(candidate_terms, "must_contain_any")
    if not (must_contain_all or must_contain_any):
        raise ValueError("[candidate] must define at least one term")

    normalization_options = NormalizationOptions(
        strip_nowiki=_require_bool(normalization, "strip_nowiki", "normalization", True),
        resolve_wikilinks=_require_bool(
            normalization,
            "resolve_wikilinks",
            "normalization",
            True,
        ),
        strip_formatting=_require_bool(
            normalization,
            "strip_formatting",
            "normalization",
            True,
        ),
        normalize_nbsp=_require_bool(normalization, "normalize_nbsp", "normalization", True),
        normalize_dashes=_require_bool(
            normalization,
            "normalize_dashes",
            "normalization",
            True,
        ),
        collapse_whitespace=_require_bool(
            normalization,
            "collapse_whitespace",
            "normalization",
            True,
        ),
    )

    return SourceSpec(
        source_dir=source_dir,
        source_id=source_id,
        name=name,
        site_lang=site_lang,
        family=family,
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
        candidate=CandidateSpec(
            must_contain_all=must_contain_all,
            must_contain_any=must_contain_any,
        ),
        template_name=_require_string(replacement, "template_name", "replacement"),
        template_without_pages=template_without_pages,
        template_with_pages=template_with_pages,
        default_summary_format=default_summary_format,
        page_patterns=_compile_patterns(
            _string_list(pages, "patterns") or DEFAULT_PAGE_PATTERNS,
            macros,
            flags=re.VERBOSE | re.UNICODE | re.IGNORECASE,
        ),
        reject_patterns=_compile_patterns(
            _string_list(pages, "reject_patterns") or DEFAULT_REJECT_PATTERNS,
            macros,
            flags=re.UNICODE | re.IGNORECASE,
        ),
        regex_rules=regex_rules,
        argument_extractors=argument_extractors,
        alias_rules=tuple(alias_rules),
        normalization=normalization_options,
        short_ref=short_ref,
        volume=volume,
        aliases=aliases,
        volume_variants=volume_variants,
    )


def _load_source_spec_from_dir(source_dir: Path, actual_root: Path) -> SourceSpec:
    source_id = source_dir.name
    path = source_dir / "source.toml"
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    source = _require_table(data, "source")
    search = _require_table(data, "search")
    candidate = _require_table(data, "candidate")
    replacement = _require_table(data, "replacement")
    summary = _require_table(data, "summary")
    short_ref = data.get("short_ref")
    pages = data.get("pages", {})
    if not isinstance(pages, dict):
        raise ValueError("Missing or invalid [pages] section")
    normalization = data.get("normalization", {})
    if not isinstance(normalization, dict):
        raise ValueError("Missing or invalid [normalization] section")
    volumes = data.get("volumes", [])
    if not isinstance(volumes, list):
        raise ValueError("Missing or invalid [[volumes]] section")

    if _require_string(source, "id", "source") != source_id:
        raise ValueError(f"source.id must match directory name '{source_id}'")

    base_name = _require_string(source, "name", "source")
    site_lang = _require_string(source, "site_lang", "source")
    family = _require_string(source, "family", "source")
    base_macros = _load_macro_map(data)
    base_short_ref = _load_short_ref(short_ref, context="short_ref")

    volume_variants: list[SourceSpec] = []
    if volumes:
        for index, volume_data in enumerate(volumes, start=1):
            if not isinstance(volume_data, dict):
                raise ValueError(f"volumes[{index}] must be a table")
            context = f"volumes[{index}]"
            volume_value = _require_string(volume_data, "volume", context)
            volume_name = _require_string(volume_data, "name", context)
            aliases = _string_list(volume_data, "aliases")
            for alias in aliases:
                validate_source_id(alias)
            volume_search = {
                "insource_terms": _merge_terms(
                    _string_list(search, "insource_terms"),
                    _string_list(volume_data, "insource_terms"),
                ),
                "isbns": _merge_terms(
                    _string_list(search, "isbns"),
                    _string_list(volume_data, "isbns"),
                ),
                "keywords": _merge_terms(
                    _string_list(search, "keywords"),
                    _string_list(volume_data, "keywords"),
                ),
            }
            volume_candidate = {
                "must_contain_all": _merge_terms(
                    _string_list(candidate, "must_contain_all"),
                    _string_list(volume_data, "must_contain_all"),
                ),
                "must_contain_any": _merge_terms(
                    _string_list(candidate, "must_contain_any"),
                    _string_list(volume_data, "must_contain_any"),
                ),
            }
            volume_macros = _merge_macros(
                base_macros,
                volume_data.get("macros", {}),
                context=f"{context}.macros",
            )
            volume_short_ref = (
                _load_short_ref(
                    volume_data.get("short_ref"),
                    context=f"{context}.short_ref",
                )
                or base_short_ref
            )
            volume_variants.append(
                _build_source_spec(
                    source_dir=source_dir,
                    source_id=source_id,
                    name=volume_name,
                    site_lang=site_lang,
                    family=family,
                    search_terms=volume_search,
                    candidate_terms=volume_candidate,
                    replacement=replacement,
                    summary=summary,
                    pages=pages,
                    normalization=normalization,
                    data=data,
                    macros=volume_macros,
                    short_ref=volume_short_ref,
                    volume=volume_value,
                    aliases=aliases,
                )
            )

    return _build_source_spec(
        source_dir=source_dir,
        source_id=source_id,
        name=base_name,
        site_lang=site_lang,
        family=family,
        search_terms=search,
        candidate_terms=candidate,
        replacement=replacement,
        summary=summary,
        pages=pages,
        normalization=normalization,
        data=data,
        macros=base_macros,
        short_ref=base_short_ref,
        volume_variants=tuple(volume_variants),
        compile_regex_rules=not volume_variants,
    )


def load_source_spec(source_id: str, root: Path | None = None) -> SourceSpec:
    actual_root = root or project_root()
    validate_source_id(source_id)
    source_dir = source_root(actual_root) / source_id
    path = source_dir / "source.toml"
    if not path.exists():
        raise FileNotFoundError(f"Unknown source '{source_id}': {path}")
    return _load_source_spec_from_dir(source_dir, actual_root)
