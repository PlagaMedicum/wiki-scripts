from __future__ import annotations

import argparse
import sys

from bewiki_biblio.models import RunOptions
from bewiki_biblio.manage import add_source, validate_sources
from bewiki_biblio.runner import list_sources, run_sources
from bewiki_biblio.specs import discover_source_specs
from bewiki_biblio.ui import AppUI, ChecklistOption


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bewiki-biblio",
        description="English operator CLI for reusable be.wiki bibliography replacers.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--no-color",
        action="store_true",
        help="Disable Rich colors and styling while keeping the same CLI flow.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list",
        parents=[common],
        help="List available bibliography sources.",
    )
    list_parser.set_defaults(command="list")

    add_source_parser = subparsers.add_parser(
        "add-source",
        parents=[common],
        help="Interactively create a new source folder with canonical filenames.",
    )
    add_source_parser.set_defaults(command="add-source")

    validate_parser = subparsers.add_parser(
        "validate",
        parents=[common],
        help="Validate source layouts, filenames, and source.toml parsing.",
    )
    validate_parser.set_defaults(command="validate")

    run_parser = subparsers.add_parser(
        "run",
        parents=[common],
        help="Run a bibliography replacer against be.wiki search results.",
    )
    run_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_sources",
        help="Run every configured source in discovery order.",
    )
    run_parser.add_argument(
        "source_ids",
        nargs="*",
        help="One or more source identifiers from sources/<source_id>/. Commas are also accepted.",
    )
    run_parser.add_argument(
        "--query",
        help="Override the generated insource query.",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of pages to inspect.",
    )
    run_parser.add_argument(
        "--minor-threshold",
        type=_non_negative_int,
        default=1000,
        help="Mark a saved edit as minor when total changed UTF-8 bytes stay below this threshold.",
    )
    run_parser.add_argument(
        "--apply",
        action="store_true",
        help="Save changes to the wiki instead of running a dry-run.",
    )
    run_parser.add_argument(
        "--yes",
        action="store_true",
        help="Save all matched pages without per-page confirmation.",
    )
    run_parser.add_argument(
        "--skip-review-required",
        action="store_true",
        help="Skip matches that still require manual verification instead of prompting for them.",
    )
    run_parser.add_argument(
        "--summary",
        help="Override the default Belarusian edit summary for this run.",
    )
    run_parser.add_argument(
        "--context",
        type=int,
        default=3,
        help="Unified diff context line count.",
    )
    run_parser.add_argument(
        "--learn-variants",
        action="store_true",
        help="Offer to add unknown candidate variants to review or ignore state.",
    )
    run_parser.add_argument(
        "--show-candidates",
        action="store_true",
        help="Show candidate source lines when a page search hit has no replacement.",
    )
    return parser


def _is_startup_wizard_argv(raw_argv: list[str]) -> tuple[bool, bool]:
    if not raw_argv:
        return True, False
    if raw_argv == ["--no-color"]:
        return True, True
    return False, False


def _render_command_preview(options: RunOptions) -> str:
    parts = ["python3 -m bewiki_biblio", "run"]
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


def _build_run_options_from_args(args, parser: argparse.ArgumentParser) -> RunOptions:
    source_ids: list[str] = []
    for raw in args.source_ids:
        source_ids.extend(part.strip() for part in raw.split(",") if part.strip())
    if args.all_sources and source_ids:
        parser.error("run accepts either --all or explicit source identifiers, not both")
    if args.all_sources:
        source_ids = [spec.source_id for spec in discover_source_specs()]
        if not source_ids:
            parser.error("run --all found no configured sources")
    if not source_ids:
        parser.error("run requires at least one source identifier or --all")

    return RunOptions(
        source_ids=tuple(source_ids),
        query=args.query,
        limit=args.limit,
        minor_threshold=args.minor_threshold,
        apply=args.apply,
        assume_yes=args.yes,
        skip_review_required=args.skip_review_required,
        summary=args.summary,
        context=args.context,
        learn_variants=args.learn_variants,
        show_candidates=args.show_candidates,
    )


def _interactive_startup(ui: AppUI) -> int:
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

    return run_sources(options, ui)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    startup_wizard, startup_no_color = _is_startup_wizard_argv(raw_argv)
    if startup_wizard:
        return _interactive_startup(AppUI(no_color=startup_no_color))

    parser = build_parser()
    args = parser.parse_args(raw_argv)
    ui = AppUI(no_color=getattr(args, "no_color", False))

    if args.command == "list":
        return list_sources(ui)
    if args.command == "add-source":
        return add_source(ui)
    if args.command == "validate":
        return validate_sources(ui)

    options = _build_run_options_from_args(args, parser)
    return run_sources(options, ui)
