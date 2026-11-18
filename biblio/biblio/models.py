from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from biblio.source_templates import render_template


@dataclass(frozen=True)
class RegexRule:
    name: str
    pattern_template: str
    pattern: str
    replacement: str
    compiled: re.Pattern[str] = field(repr=False, compare=False)
    flags: str = ""
    enabled: bool = True
    review_required: bool = False
    review_note: str = ""


@dataclass(frozen=True)
class AliasRule:
    pattern: str
    replacement: str
    flags: str = ""


@dataclass(frozen=True)
class CandidateSpec:
    must_contain_all: tuple[str, ...] = ()
    must_contain_any: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArgumentExtractor:
    name: str
    template_params: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = field(
        default_factory=tuple,
        repr=False,
        compare=False,
    )
    normalizer: str = "entry"


@dataclass(frozen=True)
class NormalizationOptions:
    strip_nowiki: bool = True
    resolve_wikilinks: bool = True
    strip_formatting: bool = True
    normalize_nbsp: bool = True
    normalize_dashes: bool = True
    collapse_whitespace: bool = True


@dataclass(frozen=True)
class ShortRefSpec:
    ref: str
    year: str


@dataclass(frozen=True)
class SourceArgumentExtractorScaffold:
    name: str
    template_params: tuple[str, ...] = ()
    normalizer: str = "entry"


@dataclass(frozen=True)
class TemplateRoleParams:
    role: str
    params: tuple[str, ...] = ()
    default: str | None = None


@dataclass(frozen=True)
class ImportedVolumeFacts:
    volume: str
    title: str
    year: str | None = None
    isbn: str | None = None


@dataclass(frozen=True)
class ImportedTemplateFacts:
    template_title: str
    template_name: str
    source_search_seed: tuple[str, ...] = ()
    role_params: tuple[TemplateRoleParams, ...] = ()
    volumes: tuple[ImportedVolumeFacts, ...] = ()
    extra_params: tuple[str, ...] = ()
    raw_text: str = field(repr=False, default="")


@dataclass(frozen=True)
class SourceSpec:
    source_dir: Path
    source_id: str
    name: str
    site_lang: str
    family: str
    insource_terms: tuple[str, ...]
    isbns: tuple[str, ...]
    keywords: tuple[str, ...]
    candidate: CandidateSpec
    template_name: str
    template_without_pages: str
    template_with_pages: str
    default_summary_format: str
    page_patterns: tuple[re.Pattern[str], ...]
    reject_patterns: tuple[re.Pattern[str], ...]
    regex_rules: tuple[RegexRule, ...]
    argument_extractors: tuple[ArgumentExtractor, ...] = ()
    alias_rules: tuple[AliasRule, ...] = ()
    normalization: NormalizationOptions = NormalizationOptions()
    short_ref: ShortRefSpec | None = None
    volume: str | None = None
    aliases: tuple[str, ...] = ()
    volume_variants: tuple[SourceSpec, ...] = field(
        default_factory=tuple,
        repr=False,
        compare=False,
    )

    @property
    def template_fields(self) -> frozenset[str]:
        fields = {"entry", "pages"}
        if self.volume is not None or self.volume_variants:
            fields.add("volume")
        fields.update(extractor.name for extractor in self.argument_extractors)
        return frozenset(fields)

    def render_template(
        self,
        pages: str | None = None,
        entry: str | None = None,
        **arguments: str | None,
    ) -> str:
        template = self.template_with_pages if pages else self.template_without_pages
        values = {
            "entry": entry or "",
            "pages": pages or "",
        }
        if self.volume is not None or self.volume_variants:
            values["volume"] = self.volume or ""
        for extractor in self.argument_extractors:
            values.setdefault(extractor.name, "")
        for key, value in arguments.items():
            values[key] = value or ""
        return render_template(template, values)

    def argument_normalizer(self, name: str) -> str:
        if name == "pages":
            return "pages"
        if name == "entry":
            return "entry"
        for extractor in self.argument_extractors:
            if extractor.name == name:
                return extractor.normalizer
        return "entry"

    def render_default_summary(self) -> str:
        return self.default_summary_format.replace(
            "{template_name}",
            self.template_name,
        )

    @property
    def rules_path(self) -> Path:
        return self.source_dir / "rules.json"

    @property
    def review_path(self) -> Path:
        return self.source_dir / "review_variants.json"

    @property
    def ignored_path(self) -> Path:
        return self.source_dir / "ignored_variants.json"

    @property
    def search_terms(self) -> tuple[str, ...]:
        seen: set[str] = set()
        values: list[str] = []
        for item in self.insource_terms + self.isbns + self.keywords:
            if item and item not in seen:
                seen.add(item)
                values.append(item)
        return tuple(values)

    @property
    def operational_specs(self) -> tuple[SourceSpec, ...]:
        return self.volume_variants or (self,)


@dataclass(frozen=True)
class RunOptions:
    source_ids: tuple[str, ...]
    query: str | None
    limit: int
    minor_threshold: int
    apply: bool
    assume_yes: bool
    skip_review_required: bool
    summary: str | None
    context: int
    learn_variants: bool
    show_candidates: bool

    @property
    def source_id(self) -> str:
        return self.source_ids[0]


@dataclass
class ReplacementResult:
    text: str
    replacements: int
    used_line_rules: list[dict]
    used_rule_names: list[str] = field(default_factory=list)
    rendered_templates: list[str] = field(default_factory=list)
    page_arguments: list[str] = field(default_factory=list)
    entry_arguments: list[str] = field(default_factory=list)
    extra_argument_values: dict[str, list[str]] = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)
    matched_review_lines: list[str] = field(default_factory=list)
    short_ref_aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VariantInfo:
    full_line: str
    review_line: str
    normalized_line: str
    pages: str | None = None
    entry: str | None = None
    extra_arguments: dict[str, str] = field(default_factory=dict)
    source_excerpt: str = ""
    excerpt_match_start: int = 0
    excerpt_match_end: int = 0


@dataclass
class RunStats:
    processed: int = 0
    matched: int = 0
    saved: int = 0
    skipped: int = 0
    failed: int = 0
    errors: int = 0
    learned: int = 0
    ignored: int = 0
    retry_events: int = 0
    failed_titles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BulkRunStatus:
    source_label: str
    total_pages: int
    current_index: int = 0
    current_title: str = ""
    phase: str = "queue"
    detail: str = ""
    phase_elapsed: float = 0.0
    processed: int = 0
    matched: int = 0
    saved: int = 0
    skipped: int = 0
    failed: int = 0
    retries: int = 0


@dataclass(frozen=True)
class SourceValidationIssue:
    source_name: str
    path: Path
    message: str
    suggestion: str | None = None


@dataclass(frozen=True)
class SourceScaffold:
    source_id: str
    name: str
    site_lang: str
    family: str
    template_name: str
    template_without_pages: str
    template_with_pages: str
    default_summary_format: str
    insource_terms: tuple[str, ...]
    isbns: tuple[str, ...]
    keywords: tuple[str, ...]
    candidate_all: tuple[str, ...]
    candidate_any: tuple[str, ...]
    page_patterns: tuple[str, ...]
    reject_patterns: tuple[str, ...]
    description: str
    argument_extractors: tuple[SourceArgumentExtractorScaffold, ...] = ()
    template_role_params: tuple[TemplateRoleParams, ...] = ()
    import_notes: tuple[str, ...] = ()
    imported_from_title: str | None = None
    volumes: tuple[SourceVolumeScaffold, ...] = ()


@dataclass(frozen=True)
class SourceVolumeScaffold:
    volume: str
    name: str
    aliases: tuple[str, ...] = ()
    insource_terms: tuple[str, ...] = ()
    isbns: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    candidate_all: tuple[str, ...] = ()
    candidate_any: tuple[str, ...] = ()
    short_ref_ref: str | None = None
    short_ref_year: str | None = None
