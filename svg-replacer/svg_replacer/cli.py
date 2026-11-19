from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from svg_replacer.api import ApiError, ImageInfo, MediaWikiApi, PageRevision
from svg_replacer.creds import Credentials, CredentialsError, default_env_path, load_credentials
from svg_replacer.ui import Decider, confirm
from svg_replacer.wikitext import (
    FileNamespace,
    discover_raster_candidates,
    has_vector_template,
    usage_context,
)
from svg_replacer.workflow import (
    build_page_reviews,
    filter_usage_rows,
    format_candidates,
    propose_vva,
    render_summary,
    review_pages,
)

DEFAULT_WIKI = "be"
WIKI_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FILE_PREFIX_RE = re.compile(r"^(?:file|файл|image|выява)\s*:", re.IGNORECASE)


class CliError(RuntimeError):
    """Operator-input or local-state problem with a clear message."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="svg-replacer",
        description=(
            "Interactively replace raster images with their existing SVG equivalents "
            "on a Wikipedia edition. Read-only unless --apply is given; every edit "
            "still needs individual interactive approval."
        ),
    )
    parser.add_argument(
        "svg_url",
        help="Commons URL of the SVG file, e.g. https://commons.wikimedia.org/wiki/File:Example.svg",
    )
    parser.add_argument(
        "--raster",
        help="Commons URL or File: title of the original raster (used when automatic "
        "discovery from the SVG page is ambiguous)",
    )
    parser.add_argument(
        "--wiki",
        default=DEFAULT_WIKI,
        help=f"Wikipedia language edition (default: {DEFAULT_WIKI})",
    )
    parser.add_argument(
        "--ns",
        type=int,
        action="append",
        dest="namespaces",
        metavar="N",
        help="namespace to search, repeatable (default: 0, articles)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="maximum number of candidate pages to review (default: 25)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="enable publishing (default is read-only; every edit still requires "
        "interactive approval)",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help="credential file (default: biblio/.env in the repository)",
    )
    return parser


def parse_commons_file_title(value: str) -> str:
    """Accept a commons.wikimedia.org File: URL or a File: title."""
    text = value.strip()
    if not text:
        raise CliError("empty file reference")
    if "://" not in text and ":" in text and FILE_PREFIX_RE.match(text):
        return text
    if "://" not in text and "/" not in text:
        return f"File:{text}"
    parts = urlsplit(text if "://" in text else f"https://{text}")
    host = parts.netloc.lower().removeprefix("www.")
    if host != "commons.wikimedia.org":
        raise CliError(f"expected a commons.wikimedia.org URL, got host {parts.netloc or '(none)'}")
    title = None
    if parts.path.startswith("/wiki/"):
        title = unquote(parts.path[len("/wiki/") :])
    elif parts.path.endswith("/index.php"):
        title = (parse_qs(parts.query).get("title") or [None])[0]
    if not title or not FILE_PREFIX_RE.match(title):
        raise CliError(f"URL does not point to a File: page: {text}")
    return title


def _page_revision(api: MediaWikiApi, title: str) -> PageRevision | None:
    """Fetch one page, tolerating server-side title normalization."""
    result = api.page_revisions([title])
    revision = result.get(title)
    if revision is None and len(result) == 1:
        revision = next(iter(result.values()))
    if revision is None or revision.missing:
        return None
    return revision


def _page_text(api: MediaWikiApi, title: str) -> str:
    revision = _page_revision(api, title)
    if revision is None:
        raise CliError(f"page not found on {api.host}: {title}")
    return revision.text


def _print_file_pair(svg: ImageInfo, raster: ImageInfo) -> None:
    for label, info in (("SVG   ", svg), ("raster", raster)):
        dimensions = f"{info.width}x{info.height}" if info.width and info.height else "unknown size"
        print(f"{label}: {info.title} ({info.mime}, {dimensions})")
        print(f"        description page: {info.description_url}")
        print(f"        direct file:      {info.url}")
        if info.thumb_url:
            print(f"        thumbnail:        {info.thumb_url}")


def _resolve_raster(
    args: argparse.Namespace,
    commons: MediaWikiApi,
    file_ns: FileNamespace,
    svg_text: str,
) -> str:
    if args.raster:
        title = parse_commons_file_title(args.raster)
        info = commons.imageinfo(title)
        if info.missing:
            raise CliError(f"raster does not exist on Commons: {title}")
        return info.title

    discovered = discover_raster_candidates(svg_text, file_ns)
    if len(discovered) == 1:
        candidate = discovered[0]
        print(f"Original raster from source/derivation info: {candidate.name} [{candidate.origin}]")
        return f"File:{candidate.name}"
    if discovered:
        print("The SVG page references several raster files; never guessing:")
        for number, candidate in enumerate(discovered, start=1):
            evidence = candidate.evidence[:120]
            print(f"  {number}. {candidate.name} [{candidate.origin}] {evidence}")
    else:
        print("No raster found in the SVG page's source/derivation information.")
    while True:
        answer = input("Raster Commons URL or File: title (empty to abort): ").strip()
        if not answer:
            raise CliError("no raster selected; aborting without changes")
        try:
            title = parse_commons_file_title(answer)
        except CliError as exc:
            print(f"  {exc}")
            continue
        info = commons.imageinfo(title)
        if info.missing:
            print(f"  file does not exist on Commons: {title}")
            continue
        return info.title


def _unused(title: str, text: str, summary: str, base_revid: int) -> int:
    raise AssertionError("publishing requested in read-only mode")


def _make_publishers(
    commons: MediaWikiApi,
    target: MediaWikiApi,
    credentials: Credentials | None,
):
    if credentials is None:
        raise AssertionError("publishing requested without credentials")

    def publish_page(title: str, text: str, summary: str, base_revid: int) -> int:
        target.login(credentials)
        return target.edit(title=title, text=text, summary=summary, base_revid=base_revid)

    def publish_commons(title: str, text: str, summary: str, base_revid: int) -> int:
        commons.login(credentials)
        return commons.edit(title=title, text=text, summary=summary, base_revid=base_revid)

    return publish_page, publish_commons


def _run(args: argparse.Namespace) -> int:
    if not WIKI_RE.match(args.wiki):
        raise CliError(f"invalid Wikipedia edition {args.wiki!r}")
    if args.limit < 1:
        raise CliError("--limit must be at least 1")
    if args.apply and not sys.stdin.isatty():
        raise CliError("--apply requires an interactive terminal for per-edit confirmation")
    namespaces = set(args.namespaces or [0])
    credentials = load_credentials(args.env or default_env_path()) if args.apply else None

    commons = MediaWikiApi("commons.wikimedia.org")
    svg_title = parse_commons_file_title(args.svg_url)
    svg_info = commons.imageinfo(svg_title)
    if svg_info.missing:
        raise CliError(f"SVG file does not exist on Commons: {svg_title}")
    svg_text = _page_text(commons, svg_info.title)
    commons_files = commons.file_namespaces()

    raster_title = _resolve_raster(args, commons, commons_files, svg_text)
    raster_info = commons.imageinfo(raster_title)
    if raster_info.missing:
        raise CliError(
            f"raster file does not exist on Commons: {raster_title} "
            "(pass --raster if the derivation info is wrong)"
        )
    raster_text = _page_text(commons, raster_info.title)

    print("Both files exist; compare them visually before any replacement:")
    _print_file_pair(svg_info, raster_info)
    if has_vector_template(raster_text):
        for line in usage_context(raster_text, "ector version available", limit=1):
            print(f"note: {raster_info.title} already carries a vector notice: {line}")
    if not confirm("Compare the two files and continue"):
        print("Aborted; no changes made.")
        return 0

    host = f"{args.wiki}.wikipedia.org"
    target = MediaWikiApi(host)
    site_db = target.site_db_name()
    rows = commons.global_usage(raster_info.title, site=site_db)
    candidates = filter_usage_rows(rows, wiki_host=host, namespaces=namespaces)
    candidates = candidates[: args.limit]

    target_files = target.file_namespaces()
    reviews = build_page_reviews(
        candidates,
        target.page_revisions,
        target_files,
        raster_name=raster_info.title.partition(":")[2],
    )
    print()
    print(format_candidates(reviews, wiki_host=host, namespaces=namespaces))
    if not reviews:
        print("No pages to review; continuing to the Commons template step.")
    print()

    svg_name = svg_info.title.partition(":")[2]
    publish_page, publish_commons = (
        _make_publishers(commons, target, credentials) if args.apply else (_unused, _unused)
    )
    summary = review_pages(
        reviews,
        apply=args.apply,
        svg_name=svg_name,
        decide=Decider(),
        publish=publish_page,
        out=print,
    )

    print()
    vva_failed = False
    if summary.stopped:
        print("Stopped during article review; skipping the Commons template step.")
    else:
        print("Commons file-description page (separate step, separate approval):")
        raster_revision = _page_revision(commons, raster_info.title)
        if raster_revision is None or raster_revision.missing:
            print(f"Cannot edit {raster_info.title}: page missing on Commons.")
        else:
            outcome = propose_vva(
                raster_info.title,
                svg_name,
                raster_revision.text,
                raster_revision.revid,
                apply=args.apply,
                decide=Decider(),
                publish=publish_commons,
                out=print,
            )
            vva_failed = outcome == "failed"

    print()
    print(render_summary(summary))
    return 1 if summary.failed or vva_failed else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ApiError, CredentialsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except EOFError:
        print("error: input closed; aborting without further changes", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted; no further changes", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
