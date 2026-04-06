from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RegexRule:
    name: str
    pattern_template: str
    pattern: str
    replacement: str
    compiled: re.Pattern[str] = field(repr=False, compare=False)
    flags: str = ""
    enabled: bool = True


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
class NormalizationOptions:
    strip_nowiki: bool = True
    resolve_wikilinks: bool = True
    strip_formatting: bool = True
    normalize_nbsp: bool = True
    normalize_dashes: bool = True
    collapse_whitespace: bool = True


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
    alias_rules: tuple[AliasRule, ...] = ()
    normalization: NormalizationOptions = NormalizationOptions()

    def render_template(
        self,
        pages: str | None = None,
        entry: str | None = None,
    ) -> str:
        template = self.template_with_pages if pages else self.template_without_pages
        template = template.replace("{entry}", entry or "")
        if pages:
            template = template.replace("{pages}", pages)
        while "|}}" in template:
            template = template.replace("|}}", "}}")
        return template

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


@dataclass(frozen=True)
class RunOptions:
    source_ids: tuple[str, ...]
    query: str | None
    limit: int
    apply: bool
    assume_yes: bool
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


@dataclass(frozen=True)
class VariantInfo:
    full_line: str
    review_line: str
    normalized_line: str
    pages: str | None = None
    entry: str | None = None


@dataclass
class RunStats:
    processed: int = 0
    matched: int = 0
    saved: int = 0
    skipped: int = 0
    errors: int = 0
    learned: int = 0
    ignored: int = 0


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
