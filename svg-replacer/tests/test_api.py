from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs

import pytest
from svg_replacer.api import (
    ApiError,
    AuthError,
    EditConflict,
    EditRejected,
    MediaWikiApi,
)
from svg_replacer.creds import Credentials

JSONDict = dict[str, object]
Handler = Callable[[str, dict[str, list[str]], dict[str, list[str]]], JSONDict]


class FakeTransport:
    """Routes canned API responses by action; records every request."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[tuple[str, dict[str, list[str]], dict[str, list[str]]]] = []

    def __call__(self, url: str, data: bytes | None) -> bytes:
        query = parse_qs(url.split("?", 1)[1]) if "?" in url else {}
        body = parse_qs(data.decode("utf-8")) if data else {}
        self.requests.append((url, query, body))
        response = self.handler(url, query, body)
        return json.dumps(response, ensure_ascii=False).encode("utf-8")

    def actions(self) -> list[str]:
        seen = []
        for _url, query, body in self.requests:
            params = {**query, **body}
            seen.append(str(params.get("action", ["?"])[0]))
        return seen


def make_api(handler: Handler) -> MediaWikiApi:
    return MediaWikiApi(
        "be.wikipedia.org",
        transport=FakeTransport(handler),
        sleep=lambda _seconds: None,
    )


def test_reads_never_authenticate_or_edit() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("prop") == ["imageinfo"]:
            return {
                "batchcomplete": True,
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "ns": 6,
                            "title": "File:Foo.png",
                            "imageinfo": [
                                {
                                    "url": "https://upload.example/Foo.png",
                                    "descriptionurl": "https://be.wikipedia.org/wiki/File:Foo.png",
                                    "mime": "image/png",
                                    "width": 100,
                                    "height": 50,
                                    "size": 1234,
                                    "thumburl": "https://upload.example/400px-Foo.png",
                                }
                            ],
                        }
                    ]
                },
            }
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    info = api.imageinfo("File:Foo.png")

    assert info.missing is False
    assert info.mime == "image/png"
    assert info.description_url.endswith("Foo.png")
    assert api.transport.actions() == ["query"]
    # No login, no token, no edit during read-only discovery.
    for url, query, body in api.transport.requests:  # type: ignore[attr-defined]
        params = {**query, **body}
        assert "clientlogin" not in params
        assert params.get("type") != ["login"]
        assert params.get("token") is None


def test_edit_sends_baserevid_token_summary_and_assert_user() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("meta") == ["tokens"]:
            return {"query": {"tokens": {"csrftoken": "CSRF+TOKEN"}}}
        if params.get("prop") == ["revisions"]:
            return {
                "query": {
                    "pages": [{"pageid": 5, "title": "Артыкул", "revisions": [{"revid": 100}]}]
                }
            }
        if params.get("action") == ["edit"]:
            return {"edit": {"result": "Success", "oldrevid": 100, "newrevid": 101}}
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    new_revid = api.edit(
        title="Артыкул",
        text="новы тэкст з [[Файл:Foo.svg]] і словам «ўцёс»",
        summary="Replaces File:Foo.png with File:Foo.svg",
        base_revid=100,
    )

    assert new_revid == 101
    edit_calls = [
        {**query, **body}
        for _url, query, body in api.transport.requests  # type: ignore[attr-defined]
        if {**query, **body}.get("action") == ["edit"]
    ]
    assert len(edit_calls) == 1
    edit = edit_calls[0]
    assert edit["baserevid"] == ["100"]
    assert edit["token"] == ["CSRF+TOKEN"]
    assert edit["assert"] == ["user"]
    assert edit["summary"] == ["Replaces File:Foo.png with File:Foo.svg"]
    assert "maxlag" in edit
    # Unicode round-trips through the URL-encoded body.
    assert edit["text"][0].startswith("новы тэкст")
    assert "«ўцёс»" in edit["text"][0]


def test_edit_aborts_without_request_when_revision_changed() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("prop") == ["revisions"]:
            return {
                "query": {
                    "pages": [{"pageid": 5, "title": "Артыкул", "revisions": [{"revid": 999}]}]
                }
            }
        raise AssertionError(f"edit must not be attempted: {params}")

    api = make_api(handler)
    with pytest.raises(EditConflict):
        api.edit(title="Артыкул", text="x", summary="s", base_revid=100)
    assert api.transport.actions() == ["query"]


def test_edit_conflict_response_raises_conflict_not_success() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("meta") == ["tokens"]:
            return {"query": {"tokens": {"csrftoken": "T"}}}
        if params.get("prop") == ["revisions"]:
            return {
                "query": {
                    "pages": [{"pageid": 5, "title": "Артыкул", "revisions": [{"revid": 100}]}]
                }
            }
        if params.get("action") == ["edit"]:
            return {"error": {"code": "editconflict", "info": "Someone else changed the page."}}
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    with pytest.raises(EditConflict):
        api.edit(title="Артыкул", text="x", summary="s", base_revid=100)


def test_permission_error_is_reported_as_rejected() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("meta") == ["tokens"]:
            return {"query": {"tokens": {"csrftoken": "T"}}}
        if params.get("prop") == ["revisions"]:
            return {
                "query": {
                    "pages": [{"pageid": 5, "title": "Абаронены", "revisions": [{"revid": 100}]}]
                }
            }
        if params.get("action") == ["edit"]:
            return {"error": {"code": "permissiondenied", "info": "You do not have permission."}}
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    with pytest.raises(EditRejected) as excinfo:
        api.edit(title="Абаронены", text="x", summary="s", base_revid=100)
    assert "permission" in str(excinfo.value)


def test_successful_login_flow_uses_legacy_botpassword_login() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("meta") == ["tokens"] and params.get("type") == ["login"]:
            return {"query": {"tokens": {"logintoken": "LOGIN+TOKEN"}}}
        if params.get("action") == ["login"]:
            return {"login": {"result": "Success", "username": "Рэдактар@тэст"}}
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    api.login(Credentials(username="Рэдактар@тэст", password="s3cret-pass"))

    login_calls = [
        {**query, **body}
        for _url, query, body in api.transport.requests  # type: ignore[attr-defined]
        if {**query, **body}.get("action") == ["login"]
    ]
    assert len(login_calls) == 1
    assert login_calls[0]["lgname"] == ["Рэдактар@тэст"]
    assert login_calls[0]["lgpassword"] == ["s3cret-pass"]
    assert login_calls[0]["lgtoken"] == ["LOGIN+TOKEN"]
    # Bot-password logins must not leak through clientlogin.
    assert all("clientlogin" not in str(req) for req in api.transport.requests)  # type: ignore[attr-defined]


def test_failed_login_raises_auth_error_without_leaking_password() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("meta") == ["tokens"]:
            return {"query": {"tokens": {"logintoken": "T"}}}
        if params.get("action") == ["login"]:
            return {"login": {"result": "Failed", "reason": "wrongpassword"}}
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    with pytest.raises(AuthError) as excinfo:
        api.login(Credentials(username="User@label", password="s3cret-pass"))
    assert "s3cret-pass" not in str(excinfo.value)
    assert "login did not establish a session" in str(excinfo.value)


def test_globalusage_pagination_and_site_filter() -> None:
    pages = [
        {
            "title": "File:Foo.png",
            "globalusage": [
                {
                    "title": "Артыкул",
                    "wiki": "be.wikipedia.org",
                    "url": "u1",
                    "ns": 0,
                    "pageid": 1,
                }
            ],
        },
        {
            "title": "File:Foo.png",
            "globalusage": [
                {
                    "title": "Другая",
                    "wiki": "be.wikipedia.org",
                    "url": "u2",
                    "ns": 0,
                    "pageid": 2,
                }
            ],
        },
    ]
    call_count = {"n": 0}

    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        assert params.get("prop") == ["globalusage"]
        assert params.get("guprop") == ["namespace|pageid|url"]
        index = call_count["n"]
        call_count["n"] += 1
        response: JSONDict = {"batchcomplete": True, "query": {"pages": [pages[index]]}}
        if index == 0:
            response["continue"] = {"gucontinue": "Foo.png|bewiki|1", "continue": "||"}
        return response

    api = make_api(handler)
    rows = api.global_usage("File:Foo.png", hosts={"be.wikipedia.org"})

    assert [row["title"] for row in rows] == ["Артыкул", "Другая"]
    assert call_count["n"] == 2


def test_api_warnings_fail_closed() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        return {"warnings": {"main": {"warnings": "Unrecognized parameters: gullimit"}}}

    api = make_api(handler)
    with pytest.raises(ApiError):
        api.imageinfo("File:Foo.png")


def test_api_error_carries_code_and_info() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        return {"error": {"code": "missingtitle", "info": "The page you specified does not exist."}}

    api = make_api(handler)
    with pytest.raises(ApiError) as excinfo:
        api.imageinfo("File:Gone.png")
    assert excinfo.value.code == "missingtitle"
    assert "does not exist" in str(excinfo.value)


def test_transient_throttling_is_retried_on_reads_only() -> None:
    attempts = {"n": 0}

    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("prop") == ["imageinfo"]:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ApiError("http429", "throttled")
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "ns": 6,
                            "title": "File:Foo.png",
                            "imageinfo": [{"url": "u", "descriptionurl": "d", "mime": "image/png"}],
                        }
                    ]
                },
            }
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    assert api.imageinfo("File:Foo.png").missing is False
    assert attempts["n"] == 2


def test_throttled_edit_is_never_retried_automatically() -> None:
    edit_attempts = {"n": 0}

    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        if params.get("prop") == ["revisions"]:
            return {
                "query": {
                    "pages": [{"pageid": 5, "title": "Артыкул", "revisions": [{"revid": 100}]}]
                }
            }
        if params.get("meta") == ["tokens"]:
            return {"query": {"tokens": {"csrftoken": "T"}}}
        if params.get("action") == ["edit"]:
            edit_attempts["n"] += 1
            raise ApiError("http429", "throttled")
        raise AssertionError(f"unexpected request: {params}")

    api = make_api(handler)
    with pytest.raises(ApiError) as excinfo:
        api.edit(title="Артыкул", text="x", summary="s", base_revid=100)
    assert excinfo.value.code == "http429"
    assert edit_attempts["n"] == 1


def test_page_revisions_keys_results_by_requested_titles_despite_normalization() -> None:
    def handler(url: str, query: dict, body: dict) -> JSONDict:
        params = {**query, **body}
        assert params.get("prop") == ["revisions"]
        assert params.get("titles") == ["Жалезная_карона|Італія"]
        return {
            "query": {
                "normalized": [{"from": "Жалезная_карона", "to": "Жалезная карона"}],
                "pages": [
                    {
                        "pageid": 9,
                        "ns": 0,
                        "title": "Жалезная карона",
                        "revisions": [{"revid": 555, "slots": {"main": {"content": "тэкст"}}}],
                    },
                    {
                        "pageid": 10,
                        "ns": 0,
                        "title": "Італія",
                        "revisions": [{"revid": 556, "slots": {"main": {"content": "тэкст"}}}],
                    },
                ],
            }
        }

    api = make_api(handler)
    revisions = api.page_revisions(["Жалезная_карона", "Італія"])

    # Callers hold GlobalUsage titles (underscores); normalization must not hide them.
    assert set(revisions) == {"Жалезная_карона", "Італія"}
    assert revisions["Жалезная_карона"].revid == 555
    assert revisions["Жалезная_карона"].missing is False
    assert revisions["Італія"].revid == 556


def test_user_rights_parsed_and_fetched_once() -> None:
    calls: list[str] = []

    def handler(url, query, body):
        params = {**query, **body}
        calls.append(str(params.get("action", ["?"])[0]))
        assert params.get("meta") == ["userinfo"]
        assert params.get("uiprop") == ["rights"]
        return {
            "query": {
                "userinfo": {"id": 5, "name": "Example@bot", "rights": ["read", "edit", "bot"]}
            }
        }

    api = make_api(handler)
    assert api.user_rights() == frozenset({"read", "edit", "bot"})
    assert api.user_rights() == frozenset({"read", "edit", "bot"})
    assert calls == ["query"]
