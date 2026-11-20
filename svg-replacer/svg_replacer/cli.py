from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from svg_replacer.api import ApiError, ImageInfo, MediaWikiApi, PageRevision
from svg_replacer.creds import Credentials, CredentialsError, default_env_path, load_credentials
from svg_replacer.ui import Decider, confirm
from svg_replacer.ui import safe_print as print
from svg_replacer.wikitext import (
    FileNamespace,
    discover_raster_candidates,
)
from svg_replacer.workflow import (
    Candidate,
    Summary,
    build_page_reviews,
    filter_usage_rows,
    format_candidates,
    propose_vva,
    render_summary,
    review_pages,
)

DEFAULT_WIKI = "all"
WIKI_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FILE_PREFIX_RE = re.compile(r"^(?:file|файл|image|выява)\s*:", re.IGNORECASE)


class CliError(RuntimeError):
    """Operator-input or local-state problem with a clear message."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="svg-replacer",
        description=(
            "Interactively replace raster images with their existing SVG equivalents "
            "across Wikimedia projects. Read-only unless publishing is explicitly "
            "chosen; every edit still needs individual interactive approval."
        ),
    )
    parser.add_argument(
        "svg_url",
        help="Commons URL of the SVG file, e.g. https://commons.wikimedia.org/wiki/File:Example.svg",
        nargs="?",
    )
    parser.add_argument(
        "--raster",
        help="Commons URL or File: title of the original raster (used when automatic "
        "discovery from the SVG page is ambiguous)",
    )
    parser.add_argument(
        "--wiki",
        default=DEFAULT_WIKI,
        help="wikis to scan: 'all' (default, every Wikimedia project using the file) "
        "or comma-separated Wikipedia codes like en,ar",
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
        help="start in PUBLISH mode without the prompt (every edit still requires "
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
    if revision is None or revision.missing:
        return None
    return revision


def _page_text(api: MediaWikiApi, title: str) -> str:
    revision = _page_revision(api, title)
    if revision is None:
        raise CliError(f"page not found on {api.host}: {title}")
    return revision.text


def _print_file_pair(svg: ImageInfo, raster: ImageInfo) -> None:
    for label, info in (("Raster", raster), ("SVG", svg)):
        print(f"{label}: {info.title}", color="36")
        print(f"  {info.description_url}")


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
        return f"File:{discovered[0].name}"
    if discovered:
        print("The SVG page references several raster files; never guessing:")
        for number, candidate in enumerate(discovered, start=1):
            print(f"  {number}. {candidate.name}")
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


def _bot_permission_reason(api: MediaWikiApi, credentials: Credentials | None) -> str | None:
    """Publish-mode gate: a skip reason when this wiki must be ignored.

    A wiki where the account holds no bot flag needs a local bot request
    first, and unflagged bot edits risk a block, so publishing is skipped
    there. Preview has no credentials and never logs in, so it cannot know.
    """
    if credentials is None:
        return None
    api.login(credentials)
    if "bot" in api.user_rights():
        return None
    return f"bot permission required on {api.host} (account has no bot flag there)"


def _publisher(api: MediaWikiApi, credentials: Credentials | None):
    if credentials is None:
        raise AssertionError("publishing requested without credentials")

    def publish(title: str, text: str, summary: str, base_revid: int) -> int:
        api.login(credentials)
        if "bot" not in api.user_rights():
            raise AssertionError(f"refusing edit on {api.host}: no bot permission")
        return api.edit(title=title, text=text, summary=summary, base_revid=base_revid)

    return publish


def _wiki_hosts(value: str) -> set[str] | None:
    """`all` for every project using the file, or comma-separated Wikipedia codes."""
    if value == "all":
        return None
    hosts = set()
    for code in value.split(","):
        code = code.strip()
        if not code or not WIKI_RE.match(code):
            raise CliError(f"invalid Wikipedia edition {code!r}")
        hosts.add(f"{code}.wikipedia.org")
    return hosts or None


def _verify_shared_files(
    target: MediaWikiApi, host: str, raster_info: ImageInfo, svg_info: ImageInfo
) -> None:
    for expected in (raster_info, svg_info):
        actual = target.imageinfo(expected.title)
        # imageinfo adds wiki-specific tracking queries to the same upload URL.
        if (
            actual.missing
            or actual.repository != "shared"
            or not actual.url
            or not expected.url
            or urlsplit(actual.url)[:3] != urlsplit(expected.url)[:3]
        ):
            raise CliError(
                f"{expected.title} does not resolve to the intended Commons file on {host}"
            )


def _run(args: argparse.Namespace) -> int:
    hosts = _wiki_hosts(args.wiki)
    if args.limit < 1:
        raise CliError("--limit must be at least 1")
    if args.apply and not sys.stdin.isatty():
        raise CliError("--apply requires an interactive terminal for per-edit confirmation")
    namespaces = set(args.namespaces or [0])
    apply = args.apply or (
        sys.stdin.isatty() and confirm("Publish approved edits? (each edit still asks separately)")
    )
    if apply:
        print("PUBLISH — each edit needs your approval.", color="32")
    else:
        print("PREVIEW — nothing will be saved.", color="33")
    credentials = load_credentials(args.env or default_env_path()) if apply else None

    commons = MediaWikiApi("commons.wikimedia.org")
    svg_title = parse_commons_file_title(
        args.svg_url if args.svg_url is not None else input("Commons SVG link: ")
    )
    svg_info = commons.imageinfo(svg_title)
    if svg_info.missing:
        raise CliError(f"SVG file does not exist on Commons: {svg_title}")
    if svg_info.mime != "image/svg+xml":
        raise CliError("destination must be an SVG image")
    svg_text = _page_text(commons, svg_info.title)
    commons_files = commons.file_namespaces()

    raster_title = _resolve_raster(args, commons, commons_files, svg_text)
    raster_info = commons.imageinfo(raster_title)
    if raster_info.missing:
        raise CliError(
            f"raster file does not exist on Commons: {raster_title} "
            "(pass --raster if the derivation info is wrong)"
        )
    if raster_info.title == svg_info.title:
        raise CliError("raster and SVG must be different files")
    if raster_info.mime not in {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/tiff",
        "image/webp",
        "image/bmp",
        "image/x-ms-bmp",
    }:
        raise CliError("source must be a supported raster image")

    print()
    _print_file_pair(svg_info, raster_info)
    if not confirm("Same image? Continue"):
        print("Aborted; no changes made.")
        return 0

    if hosts is not None:
        for host in sorted(hosts):
            _verify_shared_files(MediaWikiApi(host), host, raster_info, svg_info)

    svg_name = svg_info.title.partition(":")[2]
    summary = Summary()

    # The Commons raster description edit is proposed first, separately approved;
    # a wiki without bot permission for the account is never touched at all.
    permission_gap = _bot_permission_reason(commons, credentials)
    raster_revision = (
        None if permission_gap is not None else _page_revision(commons, raster_info.title)
    )
    if permission_gap is not None:
        print(f"skip {raster_info.title}: {permission_gap}")
        commons_outcome = "skipped"
    elif raster_revision is None or raster_revision.missing:
        print(f"Commons notice failed: page missing ({raster_info.title}).", color="31")
        commons_outcome = "failed"
    else:
        commons_outcome = propose_vva(
            raster_info.title,
            svg_name,
            raster_revision.text,
            raster_revision.revid,
            apply=apply,
            decide=Decider(apply=apply),
            publish=_publisher(commons, credentials) if apply else _unused,
            out=print,
            confirm=confirm,
        )
    if commons_outcome == "stopped":
        summary.stopped = True
        print("Stopped at the Commons notice step; no article work performed.")
        print()
        print(render_summary(summary, commons_outcome=commons_outcome), color="36")
        return 0

    rows = commons.global_usage(
        raster_info.title, hosts=hosts, namespaces=namespaces, limit=args.limit
    )
    candidates = filter_usage_rows(rows, hosts=hosts, namespaces=namespaces)
    by_host: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_host.setdefault(candidate.wiki, []).append(candidate)
    for host, host_candidates in by_host.items():
        target = MediaWikiApi(host)
        permission_gap = _bot_permission_reason(target, credentials)
        if permission_gap is not None:
            for candidate in host_candidates:
                print(f"skip {candidate.title}: {permission_gap}")
                summary.skipped.append((candidate.title, permission_gap))
            continue
        # all-mode: hosts are only known after GlobalUsage answers.
        if hosts is None:
            _verify_shared_files(target, host, raster_info, svg_info)
        reviews = build_page_reviews(
            host_candidates,
            target.page_revisions,
            target.file_namespaces(),
            raster_name=raster_info.title.partition(":")[2],
        )
        print()
        print(format_candidates(reviews, wiki_host=host, namespaces=namespaces), color="36")
        part = review_pages(
            reviews,
            apply=apply,
            svg_name=svg_name,
            decide=Decider(apply=apply),
            publish=_publisher(target, credentials) if apply else _unused,
            out=print,
            confirm=confirm,
        )
        summary.published.extend(part.published)
        summary.dry_approved.extend(part.dry_approved)
        summary.skipped.extend(part.skipped)
        summary.failed.extend(part.failed)
        summary.not_processed.extend(part.not_processed)
        summary.stopped = summary.stopped or part.stopped
        if summary.stopped:
            break
    if not by_host:
        print()
        print(f"No article uses found (namespace {', '.join(map(str, sorted(namespaces)))}).")

    print()
    failed = bool(summary.failed) or commons_outcome == "failed"
    print(render_summary(summary, commons_outcome=commons_outcome), color="31" if failed else "36")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr, color="31")
        return 2
    except (ApiError, CredentialsError) as exc:
        print(f"error: {exc}", file=sys.stderr, color="31")
        return 1
    except EOFError:
        print("error: input closed; aborting without further changes", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted; no further changes", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
