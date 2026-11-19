from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from svg_replacer.api import ApiError, EditConflict
from svg_replacer.wikitext import FileNamespace, assess_usage, usage_context
from svg_replacer.workflow import (
    Candidate,
    PageReview,
    build_page_reviews,
    filter_usage_rows,
    format_candidates,
    propose_vva,
    render_diff,
    review_pages,
)

FILES = FileNamespace.of("File", "Image", "Файл", "Выява")
RASTER = "Foo.png"
SVG = "Foo.svg"
PAGE_URL = "https://be.wikipedia.org/wiki/"


def candidate(title: str, *, wiki: str = "be.wikipedia.org", ns: int = 0) -> Candidate:
    return Candidate(title=title, wiki=wiki, url=f"{PAGE_URL}{title}", ns=ns, pageid=1)


def make_review(
    title: str,
    text: str,
    *,
    revid: int = 100,
    missing: bool = False,
) -> PageReview:
    assessment = None if missing else assess_usage(text, RASTER, FILES)
    return PageReview(
        candidate=candidate(title),
        revid=revid,
        text=text,
        assessment=assessment,
        missing=missing,
        context=[] if missing else usage_context(text, RASTER),
    )


def recording_publish(
    calls: list[tuple[str, str, str, int]] | None = None,
    *,
    fail_with: Exception | None = None,
    fail_on: str | None = None,
) -> Callable[[str, str, str, int], int]:
    calls = [] if calls is None else calls
    counter = {"revid": 500}

    def publish(title: str, text: str, summary: str, base_revid: int) -> int:
        if fail_with is not None and (fail_on is None or fail_on == title):
            raise fail_with
        calls.append((title, text, summary, base_revid))
        counter["revid"] += 1
        return counter["revid"]

    return publish


def scripted_decisions(*decisions: str) -> Callable[[object], str]:
    queue: Iterator[str] = iter(decisions)

    def decide(proposal: object) -> str:
        return next(queue)

    return decide


# --- namespace filtering (GlobalUsage rows) ---


def usage_rows() -> list[dict]:
    return [
        {
            "title": "Артыкул",
            "wiki": "be.wikipedia.org",
            "url": "https://be.wikipedia.org/wiki/Артыкул",
            "ns": 0,
            "pageid": 1,
        },
        {
            "title": "Размова:Артыкул",
            "wiki": "be.wikipedia.org",
            "url": "https://be.wikipedia.org/wiki/Размова:Артыкул",
            "ns": 1,
            "pageid": 2,
        },
        {
            "title": "Карыстальнік:X",
            "wiki": "be.wikipedia.org",
            "url": "https://be.wikipedia.org/wiki/Карыстальнік:X",
            "ns": 2,
            "pageid": 3,
        },
        {
            "title": "Шаблон:Інфабокс",
            "wiki": "be.wikipedia.org",
            "url": "https://be.wikipedia.org/wiki/Шаблон:Інфабокс",
            "ns": 10,
            "pageid": 4,
        },
        {
            "title": "Артыкул",
            "wiki": "ru.wikipedia.org",
            "url": "https://ru.wikipedia.org/wiki/Артыкул",
            "ns": 0,
            "pageid": 5,
        },
        {
            "title": "Артыкул",
            "wiki": "be.wikipedia.org",
            "url": "https://be.wikipedia.org/wiki/Артыкул",
            "ns": 0,
            "pageid": 1,
        },
    ]


def test_namespace_filter_keeps_articles_and_drops_talk_user_template() -> None:
    rows = filter_usage_rows(usage_rows(), wiki_host="be.wikipedia.org", namespaces={0})
    assert [c.title for c in rows] == ["Артыкул"]
    assert rows[0].wiki == "be.wikipedia.org"


def test_namespace_filter_can_include_selected_extra_namespaces() -> None:
    rows = filter_usage_rows(usage_rows(), wiki_host="be.wikipedia.org", namespaces={0, 1})
    assert [c.title for c in rows] == ["Артыкул", "Размова:Артыкул"]


def test_namespace_filter_targets_explicit_wiki_edition() -> None:
    rows = filter_usage_rows(usage_rows(), wiki_host="ru.wikipedia.org", namespaces={0})
    assert [c.title for c in rows] == ["Артыкул"]
    assert rows[0].wiki == "ru.wikipedia.org"
    assert rows[0].url.startswith("https://ru.wikipedia.org/")


def test_namespace_filter_deduplicates_repeated_page_rows() -> None:
    rows = filter_usage_rows(usage_rows(), wiki_host="be.wikipedia.org", namespaces={0})
    assert len(rows) == 1


# --- candidate listing ---


def test_format_candidates_lists_direct_uses_first_and_marks_skips() -> None:
    direct = make_review("Прямая", "Тэкст [[Файл:Foo.png|рамка]] канец.\n")
    indirect = make_review("Непрамая", "{{Партал|Foo.png}}\n")
    listing = format_candidates([direct, indirect], wiki_host="be.wikipedia.org", namespaces={0})

    assert listing.index("Прямая") < listing.index("Непрамая")
    assert "Прямая" in listing and "https://be.wikipedia.org/wiki/" in listing
    assert "[[Файл:Foo.png|рамка]]" in listing
    assert "skip" in listing.lower()


# --- approval gating and publishing ---


def test_readonly_mode_never_publishes_even_when_approved() -> None:
    reviews = [make_review("Артыкул", "[[Файл:Foo.png]]\n")]
    calls: list[tuple[str, str, str, int]] = []

    summary = review_pages(
        reviews,
        svg_name=SVG,
        apply=False,
        decide=scripted_decisions("approve"),
        publish=recording_publish(calls),
        out=[].append,
    )

    assert calls == []
    assert summary.published == []
    assert summary.dry_approved == ["Артыкул"]
    assert summary.failed == []


def test_apply_publishes_only_approved_pages_with_revision_guard() -> None:
    reviews = [
        make_review("Першая", "Перад [[Файл:Foo.png]] пасля.\n", revid=10),
        make_review("Другая", "[[Файл:Foo.png|thumb]]\n", revid=20),
    ]
    calls: list[tuple[str, str, str, int]] = []

    summary = review_pages(
        reviews,
        svg_name=SVG,
        apply=True,
        decide=scripted_decisions("approve", "skip"),
        publish=recording_publish(calls),
        out=[].append,
    )

    assert summary.published == ["Першая"]
    assert summary.skipped == [("Другая", "skipped by operator")]
    assert len(calls) == 1
    title, text, edit_summary, base_revid = calls[0]
    assert title == "Першая"
    assert base_revid == 10
    assert "[[Файл:Foo.svg]]" in text
    assert RASTER not in text and "пасля." in text
    assert "Foo.png" in edit_summary and "Foo.svg" in edit_summary


def test_stop_halts_processing_and_reports_remaining_pages() -> None:
    reviews = [
        make_review("Адна", "[[Файл:Foo.png]]\n"),
        make_review("Два", "[[Файл:Foo.png]]\n"),
        make_review("Тры", "[[Файл:Foo.png]]\n"),
    ]
    calls: list[tuple[str, str, str, int]] = []

    summary = review_pages(
        reviews,
        svg_name=SVG,
        apply=True,
        decide=scripted_decisions("stop"),
        publish=recording_publish(calls),
        out=[].append,
    )

    assert summary.stopped is True
    assert calls == []
    assert summary.not_processed == ["Адна", "Два", "Тры"]
    assert summary.published == []


def test_skip_stop_boundary_with_prior_approval() -> None:
    reviews = [
        make_review("Адна", "[[Файл:Foo.png]]\n"),
        make_review("Два", "[[Файл:Foo.png]]\n"),
        make_review("Тры", "[[Файл:Foo.png]]\n"),
    ]
    calls: list[tuple[str, str, str, int]] = []

    summary = review_pages(
        reviews,
        svg_name=SVG,
        apply=True,
        decide=scripted_decisions("approve", "skip", "stop"),
        publish=recording_publish(calls),
        out=[].append,
    )

    assert summary.published == ["Адна"]
    assert summary.skipped == [("Два", "skipped by operator")]
    assert summary.not_processed == ["Тры"]
    assert summary.stopped is True


def test_invalid_decision_is_never_treated_as_approval() -> None:
    reviews = [make_review("Артыкул", "[[Файл:Foo.png]]\n")]
    with pytest.raises(ValueError):
        review_pages(
            reviews,
            svg_name=SVG,
            apply=True,
            decide=lambda proposal: "yes",
            publish=recording_publish(),
            out=[].append,
        )


def test_auto_skipped_ambiguities_never_prompt_or_publish() -> None:
    indirect = make_review("Непрамая", "{{Партал|Foo.png}}\n")
    blocked = make_review("Унутры шаблону", "{{Інфабокс\n| выява = [[Файл:Foo.png]]\n}}\n")
    missing = make_review("Зніклая", "", missing=True)
    lines: list[str] = []

    def decide(proposal: object) -> str:
        raise AssertionError("auto-skipped candidates must not be prompted")

    summary = review_pages(
        [indirect, blocked, missing],
        svg_name=SVG,
        apply=True,
        decide=decide,
        publish=recording_publish(),
        out=lines.append,
    )

    assert summary.published == []
    assert summary.dry_approved == []
    skipped_titles = [title for title, _ in summary.skipped]
    assert skipped_titles == ["Непрамая", "Унутры шаблону", "Зніклая"]
    reasons = dict(summary.skipped)
    assert "template" in reasons["Унутры шаблону"]
    assert "missing" in reasons["Зніклая"]
    assert any("Непрамая" in line for line in lines)


def test_edit_conflict_is_failure_not_success_and_loop_continues() -> None:
    reviews = [
        make_review("Канфлікт", "[[Файл:Foo.png]]\n"),
        make_review("Ок", "[[Файл:Foo.png]]\n"),
    ]
    calls: list[tuple[str, str, str, int]] = []
    publish = recording_publish(calls, fail_with=EditConflict("page changed"), fail_on="Канфлікт")

    summary = review_pages(
        reviews,
        svg_name=SVG,
        apply=True,
        decide=scripted_decisions("approve", "approve"),
        publish=publish,
        out=[].append,
    )

    assert summary.published == ["Ок"]
    assert len(summary.failed) == 1
    assert summary.failed[0][0] == "Канфлікт"
    assert "conflict" in summary.failed[0][1]
    assert [title for title, *_ in calls] == ["Ок"]


def test_api_error_is_failure_never_reported_as_published() -> None:
    reviews = [make_review("Артыкул", "[[Файл:Foo.png]]\n")]
    publish = recording_publish(fail_with=ApiError("permissiondenied", "denied"))

    summary = review_pages(
        reviews,
        svg_name=SVG,
        apply=True,
        decide=scripted_decisions("approve"),
        publish=publish,
        out=[].append,
    )

    assert summary.published == []
    assert summary.failed == [("Артыкул", "permissiondenied: denied")]


def test_render_diff_shows_exact_replacement_lines() -> None:
    old = "Радок перад.\n[[Файл:Foo.png|thumb|Падпіс ўцэнтр]]\nРадок пасля.\n"
    new = old.replace("Foo.png", "Foo.svg")
    diff = render_diff(old, new, fromfile="a/Артыкул", tofile="b/Артыкул")

    assert "-[[Файл:Foo.png|thumb|Падпіс ўцэнтр]]" in diff
    assert "+[[Файл:Foo.svg|thumb|Падпіс ўцэнтр]]" in diff
    assert " Радок перад.\n" in diff  # unchanged lines appear only as context


# --- build_page_reviews ---


def test_build_page_reviews_fetches_texts_and_orders_direct_first() -> None:
    candidates = [candidate("Непрамая"), candidate("Прамая")]

    def fetch(titles: list[str]) -> dict[str, object]:
        assert titles == ["Непрамая", "Прамая"]
        from svg_replacer.api import PageRevision

        return {
            "Непрамая": PageRevision(
                title="Непрамая", revid=7, text="{{Партал|Foo.png}}", missing=False
            ),
            "Прамая": PageRevision(title="Прамая", revid=8, text="[[Файл:Foo.png]]", missing=False),
        }

    (reviews,) = (build_page_reviews(candidates, fetch, FILES, raster_name="Foo.png"),)
    assert [r.candidate.title for r in reviews] == ["Прамая", "Непрамая"]
    assert reviews[0].revid == 8
    assert reviews[0].assessment is not None
    assert reviews[0].assessment.status == "replace"
    assert reviews[0].context  # usage context extracted


def test_build_page_reviews_marks_missing_pages() -> None:
    from svg_replacer.api import PageRevision

    def fetch(titles: list[str]) -> dict[str, PageRevision]:
        return {"Артыкул": PageRevision(title="Артыкул", revid=0, text="", missing=True)}

    (reviews,) = (build_page_reviews([candidate("Артыкул")], fetch, FILES, raster_name="Foo.png"),)
    assert reviews[0].missing is True


# --- Commons Vector-version-available step ---


def test_vva_duplicate_detected_without_prompt_or_publish() -> None:
    text = "{{Vector version available|Foo.svg}}\n{{Information|x}}\n"
    calls: list[tuple[str, str, str, int]] = []

    def decide(proposal: object) -> str:
        raise AssertionError("duplicate templates must not prompt")

    outcome = propose_vva(
        "File:Foo.png",
        SVG,
        text,
        revid=9,
        apply=True,
        decide=decide,
        publish=recording_publish(calls),
        out=[].append,
    )

    assert outcome == "duplicate"
    assert calls == []


def test_vva_step_requires_separate_approval_and_apply() -> None:
    text = "{{Information|description=x}}\n"
    calls: list[tuple[str, str, str, int]] = []

    outcome = propose_vva(
        "File:Foo.png",
        SVG,
        text,
        revid=9,
        apply=False,
        decide=scripted_decisions("approve"),
        publish=recording_publish(calls),
        out=[].append,
    )
    assert outcome == "dry"
    assert calls == []

    outcome = propose_vva(
        "File:Foo.png",
        SVG,
        text,
        revid=9,
        apply=True,
        decide=scripted_decisions("approve"),
        publish=recording_publish(calls),
        out=[].append,
    )
    assert outcome == "published"
    assert len(calls) == 1
    title, new_text, summary, base_revid = calls[0]
    assert title == "File:Foo.png"
    assert base_revid == 9
    assert new_text.startswith("{{Vector version available|Foo.svg}}")
    assert "{{Information|description=x}}" in new_text
    assert "Foo.svg" in summary and "Foo.png" in summary


def test_vva_skip_and_conflict_outcomes() -> None:
    text = "{{Information|x}}\n"
    skipped = propose_vva(
        "File:Foo.png",
        SVG,
        text,
        revid=9,
        apply=True,
        decide=scripted_decisions("skip"),
        publish=recording_publish(),
        out=[].append,
    )
    assert skipped == "skipped"

    failed = propose_vva(
        "File:Foo.png",
        SVG,
        text,
        revid=9,
        apply=True,
        decide=scripted_decisions("approve"),
        publish=recording_publish(fail_with=EditConflict("changed")),
        out=[].append,
    )
    assert failed == "failed"


def test_vva_stop_leaves_page_untouched() -> None:
    outcome = propose_vva(
        "File:Foo.png",
        SVG,
        "{{Information|x}}\n",
        revid=9,
        apply=True,
        decide=scripted_decisions("stop"),
        publish=recording_publish(),
        out=[].append,
    )
    assert outcome == "stopped"
