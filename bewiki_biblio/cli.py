from __future__ import annotations

import argparse

from bewiki_biblio.models import RunOptions
from bewiki_biblio.manage import add_source, validate_sources
from bewiki_biblio.runner import list_sources, run_sources
from bewiki_biblio.specs import discover_source_specs
from bewiki_biblio.ui import AppUI


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ui = AppUI(no_color=getattr(args, "no_color", False))

    if args.command == "list":
        return list_sources(ui)
    if args.command == "add-source":
        return add_source(ui)
    if args.command == "validate":
        return validate_sources(ui)

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

    options = RunOptions(
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
    return run_sources(options, ui)
