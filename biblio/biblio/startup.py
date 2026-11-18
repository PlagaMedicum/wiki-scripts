from __future__ import annotations

from collections.abc import Callable

from biblio.models import RunOptions
from biblio.specs import discover_source_specs
from biblio.ui import AppUI, ChecklistOption


def _render_command_preview(options: RunOptions) -> str:
    parts = ["biblio", "run"]
    parts.extend(options.source_ids)
    if options.query:
        parts.extend(["--query", options.query])
    if options.limit != 10:
        parts.extend(["--limit", str(options.limit)])
    if options.minor_threshold != 1000:
        parts.extend(["--minor-threshold", str(options.minor_threshold)])
    if options.apply:
        parts.append("--apply")
    if options.assume_yes:
        parts.append("--yes")
    if options.skip_review_required:
        parts.append("--skip-review-required")
    if options.summary:
        parts.extend(["--summary", options.summary])
    if options.context != 3:
        parts.extend(["--context", str(options.context)])
    if options.learn_variants:
        parts.append("--learn-variants")
    if options.show_candidates:
        parts.append("--show-candidates")
    return " ".join(parts)


def run_startup_wizard(
    ui: AppUI,
    run_sources_fn: Callable[[RunOptions, AppUI], int],
) -> int:
    specs = discover_source_specs()
    if not specs:
        ui.error("No configured sources were found under sources/.")
        return 1

    ui.print_startup_wizard_intro(len(specs))
    source_ids = ui.prompt_source_selection(specs)
    if source_ids is None:
        ui.warn("Startup cancelled.")
        return 0

    mode = ui.prompt_run_mode()
    if mode is None:
        ui.warn("Startup cancelled.")
        return 0

    flag_options = [
        ChecklistOption(
            value="learn_variants",
            label="Learn variants",
            detail="Review unknown candidates and manual-review heuristic matches.",
        ),
        ChecklistOption(
            value="show_candidates",
            label="Show unmatched candidates",
            detail="Print candidate lines on pages where no replacement is produced.",
        ),
    ]
    if mode == "i":
        flag_options.append(
            ChecklistOption(
                value="skip_review_required",
                label="Skip review-required matches",
                detail="Save safe matches only and skip pages that still need manual verification.",
            )
        )

    selected_flags = ui.prompt_checklist(
        "Select run flags",
        flag_options,
        allow_empty=True,
    )
    if selected_flags is None:
        ui.warn("Startup cancelled.")
        return 0

    apply = mode in {"i", "b"}
    assume_yes = mode == "b"
    skip_review_required = mode == "b" or "skip_review_required" in selected_flags
    learn_variants = "learn_variants" in selected_flags
    show_candidates = "show_candidates" in selected_flags

    limit = ui.prompt_int("Limit", default=10, minimum=0)
    context = ui.prompt_int("Diff context lines", default=3, minimum=0)
    minor_threshold = ui.prompt_int(
        "Minor edit threshold (UTF-8 bytes)",
        default=1000,
        minimum=0,
    )
    query = ui.prompt_optional_text("Query override (blank = generated)")
    summary = None
    if apply:
        summary = ui.prompt_optional_text("Edit summary override (blank = source default)")

    options = RunOptions(
        source_ids=source_ids,
        query=query,
        limit=limit,
        minor_threshold=minor_threshold,
        apply=apply,
        assume_yes=assume_yes,
        skip_review_required=skip_review_required,
        summary=summary,
        context=context,
        learn_variants=learn_variants,
        show_candidates=show_candidates,
    )

    if mode == "d":
        mode_label = "Dry-run"
    elif mode == "i":
        mode_label = "Interactive apply"
    else:
        mode_label = "Background apply"

    ui.print_startup_run_summary(
        source_ids=options.source_ids,
        mode_label=mode_label,
        options={
            "Learn variants": "yes" if options.learn_variants else "no",
            "Show unmatched candidates": "yes" if options.show_candidates else "no",
            "Skip review-required": "yes" if options.skip_review_required else "no",
            "Limit": str(options.limit),
            "Diff context": str(options.context),
            "Minor threshold": str(options.minor_threshold),
            "Query override": options.query or "generated per source",
            "Edit summary": options.summary or "source default",
        },
        command_preview=_render_command_preview(options),
    )
    if not ui.confirm("Start this run?", default=True):
        ui.warn("Startup cancelled.")
        return 0

    return run_sources_fn(options, ui)
