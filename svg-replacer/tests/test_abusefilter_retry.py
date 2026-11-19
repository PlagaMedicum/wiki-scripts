"""AbuseFilter warn acknowledgement during PUBLISH.

Server contract (verified read-only against MediaWiki/AbuseFilter sources):
- a warn-level filter aborts action=edit with code ``abusefilter-warning``;
  the identical resubmission in the same session is the acknowledgement
  (AbuseFilter's Warn consequence "warns the user once, allowing the action
  on the second attempt", keyed by session/page/filter/action), so exactly
  one retry of the same edit is the documented confirm gesture.
  ``ignorewarnings`` is not an action=edit parameter and must never be sent.
- ``abusefilter-disallowed`` is final and must never be retried.
- error responses arrive either legacy ``{"error": {code, info}}`` or modern
  ``{"errors": [{code, text}]}`` (errorformat=plaintext); both shapes must map
  to the same typed errors.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs

import pytest
from svg_replacer import api as api_module
from svg_replacer.api import EditRejected, MediaWikiApi
from svg_replacer.wikitext import FileNamespace, assess_usage, usage_context
from svg_replacer.workflow import Candidate, PageReview, propose_vva, review_pages

FILES = FileNamespace.of("File", "Image", "Файл", "Выява")
RASTER = "Foo.png"
SVG = "Foo.svg"
WARN_TEXT = "Ați schimbat descrierea unei imagini; puteți salva pagina în ciuda acestei erori."
MODERN_WARNING = {"errors": [{"code": "abusefilter-warning", "text": WARN_TEXT, "module": "edit"}]}
LEGACY_WARNING = {"error": {"code": "abusefilter-warning", "info": WARN_TEXT}}
MODERN_DISALLOW = {"errors": [{"code": "abusefilter-disallowed", "text": "Acțiune refuzată."}]}

Handler = Callable[[dict[str, list[str]]], dict]


class FakeTransport:
    """Routes canned API responses by action; records every request."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[dict[str, list[str]]] = []

    def __call__(self, url: str, data: bytes | None) -> bytes:
        query = parse_qs(url.split("?", 1)[1]) if "?" in url else {}
        body = parse_qs(data.decode("utf-8")) if data else {}
        params = {**query, **body}
        self.requests.append(params)
        return json.dumps(self.handler(params), ensure_ascii=False).encode("utf-8")


def make_api(handler: Handler) -> MediaWikiApi:
    return MediaWikiApi(
        "ro.wikipedia.org",
        transport=FakeTransport(handler),
        sleep=lambda _seconds: None,
    )


def edit_handler(edit_response: dict) -> Handler:
    def handler(params: dict[str, list[str]]) -> dict:
        if params.get("meta") == ["tokens"]:
            return {"query": {"tokens": {"csrftoken": "CSRF+TOKEN"}}}
        if params.get("prop") == ["revisions"]:
            return {
                "query": {"pages": [{"pageid": 5, "title": "X", "revisions": [{"revid": 100}]}]}
            }
        if params.get("action") == ["edit"]:
            return edit_response
        raise AssertionError(f"unexpected request: {params}")

    return handler


# --- typed errors and request shape ---


def test_editwarning_is_a_typed_editrejection() -> None:
    assert issubclass(api_module.EditWarning, EditRejected)


def test_requests_use_errorformat_plaintext_and_never_ignorewarnings() -> None:
    api = make_api(edit_handler({"edit": {"result": "Success", "newrevid": 101}}))
    api.edit(title="Managementul proiectelor", text="x", summary="s", base_revid=100)

    requests = api.transport.requests  # type: ignore[attr-defined]
    assert requests, "edit flow sent no requests"
    for params in requests:
        assert params.get("errorformat") == ["plaintext"], params
        assert "ignorewarnings" not in params, params


def test_modern_errors_shape_maps_abusefilter_warning_to_editwarning() -> None:
    api = make_api(edit_handler(MODERN_WARNING))
    with pytest.raises(api_module.EditWarning) as excinfo:
        api.edit(title="Managementul proiectelor", text="x", summary="s", base_revid=100)

    assert excinfo.value.code == "abusefilter-warning"
    assert excinfo.value.info == WARN_TEXT
    assert isinstance(excinfo.value, EditRejected)


def test_legacy_error_shape_still_maps_abusefilter_warning() -> None:
    api = make_api(edit_handler(LEGACY_WARNING))
    with pytest.raises(api_module.EditWarning) as excinfo:
        api.edit(title="Managementul proiectelor", text="x", summary="s", base_revid=100)

    assert excinfo.value.code == "abusefilter-warning"
    assert excinfo.value.info == WARN_TEXT


def test_abusefilter_disallowed_is_plain_editrejection_never_retryable() -> None:
    api = make_api(edit_handler(MODERN_DISALLOW))
    with pytest.raises(EditRejected) as excinfo:
        api.edit(title="Managementul proiectelor", text="x", summary="s", base_revid=100)

    assert excinfo.value.code == "abusefilter-disallowed"
    assert type(excinfo.value) is EditRejected


# --- workflow: show the server warning, default-NO confirm, one resubmission ---


def make_review(title: str = "Managementul proiectelor") -> PageReview:
    text = f"Тэкст [[Файл:{RASTER}|рамка]] канец.\n"
    return PageReview(
        candidate=Candidate(title=title, wiki="ro.wikipedia.org", url=f"https://r/{title}", ns=0),
        revid=100,
        text=text,
        assessment=assess_usage(text, RASTER, FILES),
        missing=False,
        context=usage_context(text, RASTER),
    )


def scripted_publish(*outcomes: object):
    calls: list[tuple[str, str, str, int]] = []
    queue = list(outcomes)

    def publish(title: str, text: str, summary: str, base_revid: int) -> int:
        calls.append((title, text, summary, base_revid))
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return int(outcome)

    return publish, calls


def scripted_confirm(*answers: bool):
    questions: list[str] = []
    queue = list(answers)

    def confirm(question: str) -> bool:
        questions.append(question)
        return queue.pop(0)

    return confirm, questions


def approve(_proposal: object) -> str:
    return "approve"


def run_review(publish, out, confirm=None):
    kwargs = {} if confirm is None else {"confirm": confirm}
    return review_pages(
        [make_review()],
        apply=True,
        svg_name=SVG,
        decide=approve,
        publish=publish,
        out=out,
        **kwargs,
    )


def test_review_pages_declined_warn_skips_after_showing_server_warning() -> None:
    warning = api_module.EditWarning("abusefilter-warning", WARN_TEXT)
    publish, calls = scripted_publish(warning)
    confirm, questions = scripted_confirm(False)
    lines: list[str] = []

    summary = run_review(publish, lines.append, confirm)

    assert len(calls) == 1, "declined warn must not be resubmitted"
    assert questions and questions[0].strip(), "operator must be asked"
    assert any(WARN_TEXT in line for line in lines), "server warning must be shown"
    assert [title for title, _reason in summary.skipped] == ["Managementul proiectelor"]
    assert summary.published == [] and summary.failed == []


def test_review_pages_without_confirm_defaults_to_decline() -> None:
    warning = api_module.EditWarning("abusefilter-warning", WARN_TEXT)
    publish, calls = scripted_publish(warning)

    summary = run_review(publish, lambda _line: None)

    assert len(calls) == 1
    assert [title for title, _reason in summary.skipped] == ["Managementul proiectelor"]


def test_review_pages_confirmed_warn_resubmits_identical_edit_once() -> None:
    warning = api_module.EditWarning("abusefilter-warning", WARN_TEXT)
    publish, calls = scripted_publish(warning, 101)
    confirm, _questions = scripted_confirm(True)

    summary = run_review(publish, lambda _line: None, confirm)

    assert len(calls) == 2, "exactly one resubmission of the same edit"
    assert calls[0] == calls[1], "resubmission must reuse title, text, summary and baserevid"
    assert summary.published == ["Managementul proiectelor"]
    assert summary.failed == [] and summary.skipped == []


def test_review_pages_failed_retry_stays_failed() -> None:
    warning = api_module.EditWarning("abusefilter-warning", WARN_TEXT)
    publish, calls = scripted_publish(warning, warning)
    confirm, _questions = scripted_confirm(True)

    summary = run_review(publish, lambda _line: None, confirm)

    assert len(calls) == 2, "a failed retry must not be attempted again"
    assert [title for title, _reason in summary.failed] == ["Managementul proiectelor"]
    assert summary.published == [] and summary.skipped == []


def test_review_pages_disallow_never_prompts_or_retries() -> None:
    publish, calls = scripted_publish(EditRejected("abusefilter-disallowed", "Acțiune refuzată."))
    confirm, questions = scripted_confirm(True)

    summary = run_review(publish, lambda _line: None, confirm)

    assert len(calls) == 1 and not questions
    assert [title for title, _reason in summary.failed] == ["Managementul proiectelor"]


def test_propose_vva_declined_warn_skips_and_confirmed_warn_retries_once() -> None:
    text = f"Тэкст [[Файл:{RASTER}]].\n"
    warning = api_module.EditWarning("abusefilter-warning", WARN_TEXT)

    publish, calls = scripted_publish(warning)
    confirm, questions = scripted_confirm(False)
    lines: list[str] = []
    outcome = propose_vva(
        f"File:{RASTER}",
        SVG,
        text,
        100,
        apply=True,
        decide=approve,
        publish=publish,
        out=lines.append,
        confirm=confirm,
    )
    assert outcome == "skipped"
    assert len(calls) == 1 and questions
    assert any(WARN_TEXT in line for line in lines)

    publish, calls = scripted_publish(warning, 101)
    confirm, _questions = scripted_confirm(True)
    outcome = propose_vva(
        f"File:{RASTER}",
        SVG,
        text,
        100,
        apply=True,
        decide=approve,
        publish=publish,
        out=lambda _line: None,
        confirm=confirm,
    )
    assert outcome == "published"
    assert len(calls) == 2 and calls[0] == calls[1]
