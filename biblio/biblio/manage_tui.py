from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from biblio.manage_import import (
    build_imported_template_forms,
    fetch_template_raw,
    parse_template_facts,
    template_raw_url,
)
from biblio.manage_questions import guess_candidate_defaults
from biblio.models import (
    ImportedTemplateFacts,
    SourceArgumentExtractorScaffold,
    SourceScaffold,
    SourceVolumeScaffold,
    TemplateRoleParams,
)
from biblio.specs import (
    DEFAULT_PAGE_PATTERNS,
    DEFAULT_REJECT_PATTERNS,
    source_root,
    validate_source_id,
)
from biblio.ui import AppUI

_ROLE_LABELS = {
    "volume": "Volume parameter aliases used by the template itself.",
    "entry": "Entry/article title parameter aliases accepted by the template.",
    "author": "Author parameter aliases that can be turned into argument extractors.",
    "pages": "Page-number parameter aliases accepted by the template.",
    "responsible": "Responsible/editor parameter aliases that can be turned into extractors.",
    "ref": "Short-ref target parameter aliases used by templates like {{sfn}}.",
}


class PromptToolkitInput:
    def __init__(self) -> None:
        from prompt_toolkit import PromptSession

        self._session = PromptSession()

    def prompt_text(
        self, label: str, *, default: str = "", multiline: bool = False, help_text: str = ""
    ) -> str:
        prompt_kwargs = {
            "default": default,
            "bottom_toolbar": (lambda: help_text) if help_text else None,
        }
        if multiline:
            prompt_kwargs.update(
                {
                    "multiline": True,
                    "prompt_continuation": lambda width, _line_number, _is_soft_wrap: "." * width,
                }
            )
        return self._session.prompt(f"{label}: ", **prompt_kwargs).strip()

    def prompt_choice(
        self,
        label: str,
        *,
        choices: tuple[str, ...],
        default: str | None = None,
        help_text: str = "",
    ) -> str:
        choice_label = "/".join(choices)
        while True:
            raw = self.prompt_text(
                f"{label} [{choice_label}]",
                default=default or "",
                help_text=help_text,
            ).lower()
            if raw in choices:
                return raw

    def confirm(self, label: str, *, default: bool = True, help_text: str = "") -> bool:
        default_value = "y" if default else "n"
        return (
            self.prompt_choice(
                label,
                choices=("y", "n"),
                default=default_value,
                help_text=help_text,
            )
            == "y"
        )

    def prompt_csv(
        self, label: str, *, default: tuple[str, ...] = (), help_text: str = ""
    ) -> tuple[str, ...]:
        raw = self.prompt_text(
            label,
            default=", ".join(default),
            help_text=help_text,
        )
        values = [item.strip() for part in raw.splitlines() for item in part.split(",")]
        return tuple(value for value in values if value)

    def prompt_int(self, label: str, *, default: int, minimum: int = 0, help_text: str = "") -> int:
        while True:
            raw = self.prompt_text(label, default=str(default), help_text=help_text)
            try:
                value = int(raw)
            except ValueError:
                continue
            if value >= minimum:
                return value


def collect_scaffold_tui(
    ui: AppUI,
    root: Path,
    *,
    input_adapter: PromptToolkitInput | None = None,
    fetcher=fetch_template_raw,
) -> SourceScaffold:
    prompt = input_adapter or PromptToolkitInput()
    basics = _collect_basics_screen(ui, prompt, root)
    imported = _collect_import_screen(ui, prompt, basics["site_lang"], basics["family"], fetcher)
    return _collect_mapping_screen(ui, prompt, root, basics, imported)


def _collect_basics_screen(
    ui: AppUI,
    prompt: PromptToolkitInput,
    root: Path,
) -> dict[str, str | bool]:
    ui.print(_build_basics_panel(ui))
    name = _required_text(prompt, "Source name")
    while True:
        source_id = _required_text(
            prompt,
            "Source ID",
            help_text="Lowercase ASCII letters, digits, and hyphens only.",
        )
        try:
            validate_source_id(source_id)
        except ValueError as exc:
            ui.warn(str(exc))
            continue
        if (source_root(root) / source_id).exists():
            ui.warn(f"sources/{source_id} already exists.")
            continue
        break
    site_lang = _required_text(prompt, "Site language", default="be")
    family = _required_text(prompt, "Family", default="wikipedia")
    single_volume = prompt.confirm(
        "Single-volume source?",
        default=True,
        help_text="Choose 'n' for merged book sources with multiple internal volumes.",
    )
    return {
        "name": name,
        "source_id": source_id,
        "site_lang": site_lang,
        "family": family,
        "single_volume": single_volume,
    }


def _collect_import_screen(
    ui: AppUI,
    prompt: PromptToolkitInput,
    site_lang: str,
    family: str,
    fetcher,
) -> ImportedTemplateFacts | None:
    ui.print(_build_import_panel(ui))
    import_mode = prompt.prompt_choice(
        "Import mode",
        choices=("f", "p", "s"),
        default="f",
        help_text="f=fetch by template title, p=paste raw template text, s=skip import",
    )
    if import_mode == "s":
        return None
    if import_mode == "f":
        template_title = _required_text(
            prompt,
            "Template title",
            default="Шаблон:",
            help_text="Example: Шаблон:Крыніцы/БелЭн",
        )
        ui.info(
            "[import] Fetching raw template from "
            + template_raw_url(template_title, site_lang=site_lang, family=family)
        )
        raw_text = fetcher(template_title, site_lang=site_lang, family=family)
        ui.info(f"[import] Loaded raw template: {template_title}")
    else:
        template_title = _required_text(
            prompt,
            "Template title",
            default="Шаблон:",
            help_text="Used for template_name derivation and README notes.",
        )
        raw_text = _required_text(
            prompt,
            "Paste raw template source",
            multiline=True,
            help_text="Paste the full raw wiki template source. Press Esc+Enter to accept.",
        )
    imported = parse_template_facts(template_title, raw_text)
    ui.print(_build_import_summary_panel(ui, imported))
    return imported


def _collect_mapping_screen(
    ui: AppUI,
    prompt: PromptToolkitInput,
    _root: Path,
    basics: dict[str, str | bool],
    imported: ImportedTemplateFacts | None,
) -> SourceScaffold:
    ui.print(_build_mapping_panel(ui, imported))
    inferred_multi_volume = bool(imported and imported.volumes)
    single_volume = bool(basics["single_volume"]) and not inferred_multi_volume
    if imported and imported.volumes:
        single_volume = not prompt.confirm(
            "Treat this as a merged multi-volume source?",
            default=True,
            help_text="Imported volume switches were detected in the template.",
        )
    if imported:
        template_name = imported.template_name
        ui.info(f"[import] Using template name: {template_name}")
        without_pages, with_pages = build_imported_template_forms(
            template_name,
            imported.role_params,
            single_volume=single_volume,
        )
        ui.info(f"[import] Default template without pages: {without_pages}")
        ui.info(f"[import] Default template with pages: {with_pages}")
    else:
        template_name = _required_text(
            prompt,
            "Template name",
            default="",
        )
        without_pages, with_pages = _prompt_template_forms(
            prompt, template_name, single_volume=single_volume
        )
    default_summary = _prompt_default_summary(prompt, template_name)
    role_params = list(imported.role_params if imported else ())
    role_params, import_notes = _resolve_extra_params(
        ui, prompt, role_params, imported.extra_params if imported else ()
    )
    argument_extractors = _build_argument_extractors(role_params)
    insource_default = imported.source_search_seed if imported else ()
    while True:
        insource_terms = prompt.prompt_csv(
            "Insource terms",
            default=insource_default,
            help_text="MediaWiki retrieval terms used in the initial wiki search.",
        )
        isbns = prompt.prompt_csv(
            "ISBNs",
            default=(),
            help_text="Stable ISBN tokens useful for search or candidate filtering.",
        )
        keywords = prompt.prompt_csv(
            "Keywords",
            default=(),
            help_text="Human-readable bibliography fragments used as additional search hints.",
        )
        if insource_terms or isbns or keywords:
            break
        ui.warn("Add at least one insource term, ISBN, or keyword.")
    candidate_default_all, candidate_default_any = guess_candidate_defaults(
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
    )
    while True:
        candidate_all = prompt.prompt_csv(
            "Candidate must contain all",
            default=candidate_default_all,
            help_text="Validation terms applied after wiki retrieval. These are not the initial search query.",
        )
        candidate_any = prompt.prompt_csv(
            "Candidate must contain any",
            default=candidate_default_any,
            help_text="At least one of these terms must appear in the candidate line or page.",
        )
        if candidate_all or candidate_any:
            break
        ui.warn("Add at least one candidate term in must_contain_all or must_contain_any.")
    volumes = () if single_volume else _collect_volume_rows(prompt, imported)
    description = _required_text(
        prompt,
        "README summary line",
        default=(
            f"This source targets {basics['name']} bibliography references on {basics['site_lang']}.{basics['family']}.org."
            if single_volume
            else f"This source targets merged multi-volume bibliography references for {basics['name']} on {basics['site_lang']}.{basics['family']}.org."
        ),
    )
    return SourceScaffold(
        source_id=str(basics["source_id"]),
        name=str(basics["name"]),
        site_lang=str(basics["site_lang"]),
        family=str(basics["family"]),
        template_name=template_name,
        template_without_pages=without_pages,
        template_with_pages=with_pages,
        default_summary_format=default_summary,
        insource_terms=insource_terms,
        isbns=isbns,
        keywords=keywords,
        candidate_all=candidate_all,
        candidate_any=candidate_any,
        page_patterns=DEFAULT_PAGE_PATTERNS,
        reject_patterns=DEFAULT_REJECT_PATTERNS,
        description=description,
        argument_extractors=argument_extractors,
        template_role_params=tuple(role_params),
        import_notes=tuple(import_notes),
        imported_from_title=imported.template_title if imported else None,
        volumes=volumes,
    )


def _prompt_template_forms(
    prompt: PromptToolkitInput,
    template_name: str,
    *,
    single_volume: bool,
) -> tuple[str, str]:
    without_pages = (
        f"{{{{{template_name}}}}}" if single_volume else "{{" + template_name + "|{volume}}}"
    )
    with_pages = (
        f"{{{{{template_name}|{{pages}}}}}}"
        if single_volume
        else "{{" + template_name + "|{volume}|{pages}}}"
    )
    while True:
        actual_without = _required_text(prompt, "Template without pages", default=without_pages)
        actual_with = _required_text(prompt, "Template with pages", default=with_pages)
        if "{pages}" not in actual_with:
            continue
        if not single_volume and (
            "{volume}" not in actual_without or "{volume}" not in actual_with
        ):
            continue
        return actual_without, actual_with


def _prompt_default_summary(prompt: PromptToolkitInput, template_name: str) -> str:
    default_summary = _required_text(
        prompt,
        "Default edit summary",
        default="Замена бібліяграфічнай спасылкі шаблонам {{{template_name}}}",
    )
    while "{template_name}" not in default_summary:
        default_summary = _required_text(
            prompt,
            "Default edit summary",
            default=default_summary
            or f"Замена бібліяграфічнай спасылкі шаблонам {{{template_name}}}",
        )
    return default_summary


def _resolve_extra_params(
    ui: AppUI,
    prompt: PromptToolkitInput,
    role_params: list[TemplateRoleParams],
    extra_params: Iterable[str],
) -> tuple[list[TemplateRoleParams], list[str]]:
    import_notes: list[str] = []
    for param in extra_params:
        action = prompt.prompt_choice(
            f"Extra template param `{param}`",
            choices=("m", "n", "i"),
            default="n",
            help_text="m=map to a known role, n=keep as README note, i=ignore",
        )
        if action == "i":
            continue
        if action == "n":
            import_notes.append(f"Unmapped template parameter retained as note: {param}")
            continue
        role = prompt.prompt_choice(
            f"Map `{param}` to role",
            choices=("v", "e", "a", "p", "r", "f"),
            default="e",
            help_text="v=volume, e=entry, a=author, p=pages, r=responsible, f=ref",
        )
        target_role = {
            "v": "volume",
            "e": "entry",
            "a": "author",
            "p": "pages",
            "r": "responsible",
            "f": "ref",
        }[role]
        role_params = _merge_role_param(role_params, target_role, param)
        ui.info(f"[import] mapped {param} -> {target_role}")
    return role_params, import_notes


def _merge_role_param(
    role_params: list[TemplateRoleParams],
    role: str,
    param: str,
) -> list[TemplateRoleParams]:
    merged: list[TemplateRoleParams] = []
    updated = False
    for binding in role_params:
        if binding.role != role:
            merged.append(binding)
            continue
        params = tuple(dict.fromkeys((*binding.params, param)))
        merged.append(TemplateRoleParams(role=binding.role, params=params, default=binding.default))
        updated = True
    if not updated:
        merged.append(TemplateRoleParams(role=role, params=(param,)))
    return merged


def _build_argument_extractors(
    role_params: Iterable[TemplateRoleParams],
) -> tuple[SourceArgumentExtractorScaffold, ...]:
    extractors: list[SourceArgumentExtractorScaffold] = []
    for binding in role_params:
        if binding.role not in {"author", "responsible"} or not binding.params:
            continue
        extractors.append(
            SourceArgumentExtractorScaffold(
                name=binding.role,
                template_params=binding.params,
                normalizer="whitespace",
            )
        )
    return tuple(extractors)


def _collect_volume_rows(
    prompt: PromptToolkitInput,
    imported: ImportedTemplateFacts | None,
) -> tuple[SourceVolumeScaffold, ...]:
    imported_volumes = imported.volumes if imported else ()
    if imported_volumes and not prompt.confirm(
        "Edit imported volume rows?",
        default=False,
        help_text="Choose 'n' to accept imported volume labels, years, and ISBNs as defaults.",
    ):
        return tuple(
            SourceVolumeScaffold(
                volume=volume.volume,
                name=volume.title,
                aliases=(),
                insource_terms=(volume.title,),
                isbns=(volume.isbn,) if volume.isbn else (),
                keywords=(),
                candidate_all=(volume.title,),
                candidate_any=(volume.isbn,) if volume.isbn else (),
                short_ref_ref=_role_default(imported.role_params if imported else (), "ref"),
                short_ref_year=volume.year,
            )
            for volume in imported_volumes
        )

    count = len(imported_volumes) or prompt.prompt_int(
        "How many volume entries?",
        default=2,
        minimum=1,
        help_text="Merged sources keep a single source id and one row per internal volume.",
    )
    volumes: list[SourceVolumeScaffold] = []
    ref_default = _role_default(imported.role_params if imported else (), "ref")
    for index in range(count):
        imported_volume = imported_volumes[index] if index < len(imported_volumes) else None
        prefix = f"Volume {index + 1} "
        name = _required_text(
            prompt, f"{prefix}name", default=imported_volume.title if imported_volume else ""
        )
        volume = _required_text(
            prompt,
            f"{prefix}template parameter",
            default=imported_volume.volume if imported_volume else str(index + 1),
        )
        aliases = prompt.prompt_csv(
            f"{prefix}aliases",
            default=(),
            help_text="Legacy or shorthand source ids that should remain discoverable.",
        )
        while True:
            insource_terms = prompt.prompt_csv(
                f"{prefix}insource terms",
                default=(imported_volume.title,) if imported_volume else (),
            )
            isbns = prompt.prompt_csv(
                f"{prefix}ISBNs",
                default=(imported_volume.isbn,) if imported_volume and imported_volume.isbn else (),
            )
            keywords = prompt.prompt_csv(f"{prefix}keywords", default=())
            if insource_terms or isbns or keywords:
                break
        candidate_default_all, candidate_default_any = guess_candidate_defaults(
            insource_terms=insource_terms,
            isbns=isbns,
            keywords=keywords,
        )
        while True:
            candidate_all = prompt.prompt_csv(
                f"{prefix}candidate all",
                default=candidate_default_all,
            )
            candidate_any = prompt.prompt_csv(
                f"{prefix}candidate any",
                default=candidate_default_any,
            )
            if candidate_all or candidate_any:
                break
        short_ref_ref = _required_text(
            prompt,
            f"{prefix}short ref target",
            default=ref_default or "",
        )
        short_ref_year = _required_text(
            prompt,
            f"{prefix}short ref year",
            default=imported_volume.year if imported_volume and imported_volume.year else "",
        )
        volumes.append(
            SourceVolumeScaffold(
                volume=volume,
                name=name,
                aliases=aliases,
                insource_terms=insource_terms,
                isbns=isbns,
                keywords=keywords,
                candidate_all=candidate_all,
                candidate_any=candidate_any,
                short_ref_ref=short_ref_ref,
                short_ref_year=short_ref_year,
            )
        )
    return tuple(volumes)


def _role_default(bindings: Iterable[TemplateRoleParams], role: str) -> str | None:
    for binding in bindings:
        if binding.role == role:
            return binding.default
    return None


def _required_text(
    prompt: PromptToolkitInput,
    label: str,
    *,
    default: str = "",
    multiline: bool = False,
    help_text: str = "",
) -> str:
    while True:
        value = prompt.prompt_text(
            label,
            default=default,
            multiline=multiline,
            help_text=help_text,
        )
        if value.strip():
            return value.strip()


def _build_basics_panel(ui: AppUI) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="" if ui.no_color else "bold cyan")
    table.add_column()
    table.add_row("Screen", "Basics")
    table.add_row("Alias", "Alternate or legacy ids for the same source or volume.")
    table.add_row("Insource term", "MediaWiki retrieval term used in the initial page search.")
    table.add_row("Keyword", "Stable human text used to narrow candidate matching.")
    table.add_row("Candidate all/any", "Post-search filters, not the initial insource query.")
    return Panel(table, title="Add source: basics", border_style="blue")


def _build_import_panel(ui: AppUI) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="" if ui.no_color else "bold cyan")
    table.add_column()
    table.add_row("Screen", "Import")
    table.add_row("Fetch", "Download raw template source by template title.")
    table.add_row("Paste", "Paste raw template wikitext directly into a multiline editor.")
    table.add_row(
        "Scope", "Only fields the template truly exposes are auto-filled; regex/macros stay manual."
    )
    return Panel(table, title="Add source: template import", border_style="blue")


def _build_import_summary_panel(ui: AppUI, imported: ImportedTemplateFacts) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="" if ui.no_color else "bold cyan")
    table.add_column()
    table.add_row("Template", imported.template_name)
    table.add_row("Source seed", ", ".join(imported.source_search_seed) or "none")
    table.add_row("Volumes", str(len(imported.volumes) or 1))
    table.add_row(
        "Known params",
        ", ".join(f"{item.role}={','.join(item.params)}" for item in imported.role_params),
    )
    table.add_row("Extra params", ", ".join(imported.extra_params) or "none")
    return Panel(table, title="Imported template facts", border_style="green")


def _build_mapping_panel(ui: AppUI, imported: ImportedTemplateFacts | None) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="" if ui.no_color else "bold cyan")
    table.add_column()
    table.add_row("Screen", "Mapping")
    if imported:
        table.add_row("Imported template", imported.template_title)
    for role, description in _ROLE_LABELS.items():
        table.add_row(role, description)
    table.add_row(
        "Extra params", "Each unknown template param must be mapped, kept as note, or ignored."
    )
    return Panel(table, title="Add source: mapping", border_style="blue")
