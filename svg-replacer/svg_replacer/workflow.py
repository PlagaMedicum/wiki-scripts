from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import quote

from svg_replacer.api import ApiError, EditConflict, PageRevision
from svg_replacer.wikitext import (
    Assessment,
    FileNamespace,
    add_vector_template,
    assess_usage,
    has_vector_template,
    replace_matches,
    usage_context,
)

Decide = Callable[["Proposal"], str]
Publish = Callable[[str, str, str, int], int]
Emit = Callable[[str], None]

_STATUS_ORDER = {"replace": 0, "blocked": 1, "indirect": 2, "missing": 3}


@dataclass(frozen=True)
class Candidate:
    title: str
    wiki: str
    url: str
    ns: int
    pageid: int | None = None


@dataclass
class PageReview:
    candidate: Candidate
    revid: int
    text: str
    assessment: Assessment | None
    missing: bool
    context: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    kind: str  # "page" or "commons"
    title: str
    url: str
    context: list[str]
    diff: str
    edit_summary: str
    raster: str
    svg: str


@dataclass
class Summary:
    published: list[str] = field(default_factory=list)
    dry_approved: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    not_processed: list[str] = field(default_factory=list)
    stopped: bool = False


def filter_usage_rows(
    rows: Iterable[dict],
    *,
    wiki_host: str,
    namespaces: set[int],
) -> list[Candidate]:
    """Keep GlobalUsage rows for one wiki/namespace set and deduplicate pages."""
    seen: set[tuple[str, str]] = set()
    candidates: list[Candidate] = []
    for row in rows:
        wiki = str(row.get("wiki", ""))
        if wiki != wiki_host:
            continue
        if "ns" not in row:
            raise ApiError("badresponse", "globalusage row has no ns field")
        namespace = int(row["ns"])
        if namespace not in namespaces:
            continue
        title = str(row.get("title", ""))
        key = (wiki, title)
        if not title or key in seen:
            continue
        seen.add(key)
        pageid = row.get("pageid")
        candidates.append(
            Candidate(
                title=title,
                wiki=wiki,
                url=str(row.get("url", "")),
                ns=namespace,
                pageid=int(pageid) if pageid is not None else None,
            )
        )
    return candidates


def build_page_reviews(
    candidates: list[Candidate],
    fetch: Callable[[list[str]], dict[str, PageRevision]],
    file_ns: FileNamespace,
    *,
    raster_name: str,
) -> list[PageReview]:
    fetched = fetch([candidate.title for candidate in candidates]) if candidates else {}
    reviews: list[PageReview] = []
    for candidate in candidates:
        revision = fetched.get(candidate.title)
        if revision is None or revision.missing:
            reviews.append(
                PageReview(
                    candidate=candidate,
                    revid=0,
                    text="",
                    assessment=None,
                    missing=True,
                )
            )
            continue
        assessment = assess_usage(revision.text, raster_name, file_ns)
        reviews.append(
            PageReview(
                candidate=candidate,
                revid=revision.revid,
                text=revision.text,
                assessment=assessment,
                missing=False,
                context=usage_context(revision.text, raster_name),
            )
        )
    reviews.sort(key=lambda review: _STATUS_ORDER[_review_status(review)])
    return reviews


def _review_status(review: PageReview) -> str:
    if review.missing:
        return "missing"
    if review.assessment is None:
        return "missing"
    return review.assessment.status


def format_candidates(reviews: list[PageReview], *, wiki_host: str, namespaces: set[int]) -> str:
    namespace_label = ", ".join(str(value) for value in sorted(namespaces))
    lines = [f"Candidates on {wiki_host} (namespace {namespace_label}): {len(reviews)} page(s)"]
    for number, review in enumerate(reviews, start=1):
        lines.append(f"  {number}. {review.candidate.title} [{_status_label(review)}]")
        lines.append(f"      {review.candidate.url}")
        lines.extend(f"      {line}" for line in review.context)
    return "\n".join(lines)


def _status_label(review: PageReview) -> str:
    if review.missing:
        return "skip: page missing"
    assessment = review.assessment
    if assessment is None:
        return "skip: unknown"
    if assessment.status == "replace":
        return "direct use"
    if assessment.status == "blocked":
        return f"skip: {assessment.blocked_reason}"
    return "skip: usage not directly editable"


def render_diff(old: str, new: str, *, fromfile: str, tofile: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
        n=3,
    )
    return "".join(lines)


def build_edit_summary(raster_name: str, svg_name: str) -> str:
    return f"Replaces File:{raster_name} with File:{svg_name} (vector version available)"


def build_vva_summary(raster_title: str, svg_title: str) -> str:
    return f"Adds {{{{Vector version available|{svg_title}}}}} for [[{raster_title}]]"


def _reject_unknown(decision: str) -> None:
    if decision not in {"approve", "skip", "stop"}:
        raise ValueError(f"unknown decision {decision!r}; never guessing")


def review_pages(
    reviews: list[PageReview],
    *,
    apply: bool,
    svg_name: str,
    decide: Decide,
    publish: Publish,
    out: Emit,
) -> Summary:
    """Interactive review loop: every candidate needs an explicit decision.

    Ambiguous or indirect usages are skipped without prompting; publishing
    happens only with apply=True for individually approved candidates.
    """
    summary = Summary()
    for index, review in enumerate(reviews):
        title = review.candidate.title
        status = _review_status(review)
        if status == "missing":
            _record_skip(summary, title, "page missing", out)
            continue
        assessment = review.assessment
        assert assessment is not None
        if status == "blocked":
            _record_skip(summary, title, assessment.blocked_reason, out)
            continue
        if status == "indirect":
            _record_skip(
                summary,
                title,
                "usage not directly editable (transcluded or passed through a template)",
                out,
            )
            continue

        new_text = replace_matches(review.text, assessment.matches, svg_name)
        diff = render_diff(review.text, new_text, fromfile=f"a/{title}", tofile=f"b/{title}")
        proposal = Proposal(
            kind="page",
            title=title,
            url=review.candidate.url,
            context=review.context,
            diff=diff,
            edit_summary=build_edit_summary(assessment.raster, svg_name),
            raster=assessment.raster,
            svg=svg_name,
        )
        decision = decide(proposal)
        _reject_unknown(decision)
        if decision == "stop":
            summary.stopped = True
            summary.not_processed.extend(pending.candidate.title for pending in reviews[index:])
            out(f"stopped; {len(summary.not_processed)} candidate(s) not processed")
            break
        if decision == "skip":
            _record_skip(summary, title, "skipped by operator", out)
            continue
        if not apply:
            summary.dry_approved.append(title)
            out(f"Previewed article: {title} (not saved)")
            continue
        try:
            publish(title, new_text, proposal.edit_summary, review.revid)
        except EditConflict as exc:
            summary.failed.append((title, f"conflict: {exc}"))
            out(f"FAILED {title}: conflict: {exc}")
        except ApiError as exc:
            summary.failed.append((title, f"{exc.code}: {exc.info}"))
            out(f"FAILED {title}: {exc}")
        else:
            summary.published.append(title)
            out(f"published {title}")
    return summary


def _record_skip(summary: Summary, title: str, reason: str, out: Emit) -> None:
    summary.skipped.append((title, reason))
    out(f"skip {title}: {reason}")


def propose_vva(
    raster_title: str,
    svg_name: str,
    text: str,
    revid: int,
    *,
    apply: bool,
    decide: Decide,
    publish: Publish,
    out: Emit,
) -> str:
    """Separately propose adding {{Vector version available}} on Commons."""
    if has_vector_template(text):
        out("Commons notice already present; nothing to add.")
        return "duplicate"
    new_text = add_vector_template(text, svg_name)
    diff = render_diff(text, new_text, fromfile=f"a/{raster_title}", tofile=f"b/{raster_title}")
    proposal = Proposal(
        kind="commons",
        title=raster_title,
        url=f"https://commons.wikimedia.org/wiki/{quote(raster_title.replace(' ', '_'), safe=':')}",
        context=[],
        diff=diff,
        edit_summary=build_vva_summary(raster_title, svg_name),
        raster=raster_title,
        svg=svg_name,
    )
    decision = decide(proposal)
    _reject_unknown(decision)
    if decision == "stop":
        out("stopped before the Commons template step")
        return "stopped"
    if decision == "skip":
        out(f"skipped Commons template for {raster_title}")
        return "skipped"
    if not apply:
        out("Previewed Commons notice (not saved).")
        return "dry"
    try:
        publish(raster_title, new_text, proposal.edit_summary, revid)
    except EditConflict as exc:
        out(f"FAILED {raster_title}: conflict: {exc}")
        return "failed"
    except ApiError as exc:
        out(f"FAILED {raster_title}: {exc}")
        return "failed"
    out(f"published {raster_title}")
    return "published"


def render_summary(summary: Summary, *, commons_outcome: str | None = None) -> str:
    saved = len(summary.published) + (commons_outcome == "published")
    previewed = len(summary.dry_approved) + (commons_outcome == "dry")
    lines = [f"Result: {saved} saved, {previewed} previewed (not saved)"]
    if commons_outcome is not None:
        label = {
            "published": "saved",
            "dry": "previewed",
            "duplicate": "already present",
            "skipped": "skipped",
            "stopped": "not processed (quit)",
            "failed": "failed",
        }[commons_outcome]
        lines.append(f"Commons notice: {label}")
    failed = len(summary.failed) + (commons_outcome == "failed")
    skipped = len(summary.skipped) + (commons_outcome == "skipped")
    if failed:
        lines.append(f"Failed: {failed}")
    if skipped:
        lines.append(f"Skipped: {skipped}")
    if summary.not_processed:
        lines.append(f"Not processed: {len(summary.not_processed)}")
    if summary.stopped:
        lines.append("Stopped by operator.")
    return "\n".join(lines)
