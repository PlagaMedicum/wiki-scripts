from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from svg_replacer.creds import Credentials
from svg_replacer.wikitext import FileNamespace

DEFAULT_USER_AGENT = (
    "svg-replacer/0.1 (wiki-scripts; interactive raster-to-SVG replacement tool) "
    f"Python-urllib/{sys.version_info.major}.{sys.version_info.minor}"
)
REQUEST_INTERVAL_SECONDS = 1.0
RETRYABLE_ERROR_CODES = frozenset({"http429", "http503"})
RETRY_DELAYS_SECONDS = (15.0, 45.0, 90.0)
MAX_URL_LENGTH = 6000
TITLE_BATCH_SIZE = 20
GLOBAL_USAGE_LIMIT = 500
EDIT_REJECTED_CODES = frozenset(
    {
        "assertuserfailed",
        "badtoken",
        "cantcreate",
        "maxlag",
        "noedit",
        "permissiondenied",
        "protectedpage",
        "ratelimited",
        "readonly",
        "spamdetected",
    }
)

Transport = Callable[[str, bytes | None], bytes]


class ApiError(RuntimeError):
    """A MediaWiki API failure; `code` is the API error/warning code."""

    def __init__(self, code: str, info: str = "") -> None:
        super().__init__(f"{code}: {info}" if info else code)
        self.code = code
        self.info = info


class AuthError(ApiError):
    """Login did not establish a session."""


class EditConflict(ApiError):
    """The page changed since the reviewed revision, or the server reported a conflict."""


class EditRejected(ApiError):
    """The server refused the edit (permissions, protection, rate limits, ...)."""


@dataclass(frozen=True)
class ImageInfo:
    title: str
    missing: bool
    url: str | None = None
    description_url: str | None = None
    thumb_url: str | None = None
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    size: int | None = None
    repository: str | None = None


@dataclass(frozen=True)
class PageRevision:
    title: str
    revid: int
    text: str
    missing: bool


class MediaWikiApi:
    """Narrow read/write client for one MediaWiki host.

    Reads are anonymous and side-effect free. Login happens only when explicitly
    requested, and edits only through `edit()`.
    """

    def __init__(
        self,
        host: str,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.host = host
        self.user_agent = user_agent
        self.sleep = sleep
        self.transport = transport if transport is not None else self._build_transport()
        self._file_namespaces: FileNamespace | None = None
        self._logged_in = False

    def _build_transport(self) -> Transport:
        opener = build_opener(HTTPCookieProcessor(CookieJar()))

        def transport(url: str, data: bytes | None) -> bytes:
            headers = {"User-Agent": self.user_agent}
            if data is not None:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            request = Request(url, data=data, headers=headers)
            try:
                with opener.open(request, timeout=30) as response:
                    return response.read()
            except HTTPError as exc:
                raise ApiError(f"http{exc.code}", "HTTP request failed") from None
            except URLError as exc:
                raise ApiError("network", str(exc.reason)) from None

        return transport

    @property
    def api_url(self) -> str:
        return f"https://{self.host}/w/api.php"

    def _request(self, params: dict[str, Any], *, post: bool = False) -> dict[str, Any]:
        full = {"format": "json", "formatversion": "2", **params}
        self.sleep(REQUEST_INTERVAL_SECONDS)
        encoded = urlencode(full, doseq=True)
        if post or len(encoded) > MAX_URL_LENGTH:
            url, data = self.api_url, encoded.encode("utf-8")
        else:
            url, data = f"{self.api_url}?{encoded}", None
        raw = self._send(url, data, retryable=not post)
        try:
            response = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError, json.JSONDecodeError:
            raise ApiError("badresponse", f"non-JSON response from {self.host}") from None
        if not isinstance(response, dict):
            raise ApiError("badresponse", f"unexpected response shape from {self.host}")
        if "error" in response:
            error = response["error"]
            raise ApiError(str(error.get("code", "error")), str(error.get("info", "")))
        if "warnings" in response:
            raise ApiError("warning", json.dumps(response["warnings"], ensure_ascii=False))
        return response

    def _send(self, url: str, data: bytes | None, *, retryable: bool) -> bytes:
        """Send one request; retry transient throttling on reads only.

        Writes (login/edit) are never retried automatically so an ambiguous
        failure surfaces to the operator instead of being re-attempted.
        """
        attempt = 0
        while True:
            try:
                return self.transport(url, data)
            except ApiError as exc:
                if (
                    retryable
                    and exc.code in RETRYABLE_ERROR_CODES
                    and attempt < len(RETRY_DELAYS_SECONDS)
                ):
                    self.sleep(RETRY_DELAYS_SECONDS[attempt])
                    attempt += 1
                    continue
                raise

    @staticmethod
    def _single_page(response: dict[str, Any]) -> dict[str, Any]:
        pages = response.get("query", {}).get("pages", [])
        if not isinstance(pages, list) or not pages:
            raise ApiError("badresponse", "query returned no pages")
        page = pages[0]
        if not isinstance(page, dict):
            raise ApiError("badresponse", "query returned an unexpected page shape")
        return page

    def imageinfo(self, title: str) -> ImageInfo:
        response = self._request(
            {
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|size|mime",
                "iiurlwidth": "400",
            }
        )
        page = self._single_page(response)
        page_title = str(page.get("title", title))
        if not page.get("imageinfo"):
            return ImageInfo(title=page_title, missing=True)
        info = page["imageinfo"][0]
        return ImageInfo(
            title=page_title,
            missing=False,
            url=info.get("url"),
            description_url=info.get("descriptionurl"),
            thumb_url=info.get("thumburl"),
            mime=info.get("mime"),
            width=info.get("width"),
            height=info.get("height"),
            size=info.get("size"),
            repository=page.get("imagerepository"),
        )

    def file_namespaces(self) -> FileNamespace:
        if self._file_namespaces is None:
            response = self._request(
                {
                    "action": "query",
                    "meta": "siteinfo",
                    "siprop": "namespaces|namespacealiases",
                }
            )
            info = response.get("query", {})
            namespaces = FileNamespace.from_siteinfo(
                info.get("namespaces", {}), info.get("namespacealiases", [])
            )
            if not namespaces.aliases:
                raise ApiError("badresponse", f"no file namespace found on {self.host}")
            self._file_namespaces = namespaces
        return self._file_namespaces

    def page_revisions(self, titles: list[str]) -> dict[str, PageRevision]:
        results: dict[str, PageRevision] = {}
        for start in range(0, len(titles), TITLE_BATCH_SIZE):
            batch = titles[start : start + TITLE_BATCH_SIZE]
            response = self._request(
                {
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "revisions",
                    "rvslots": "main",
                    "rvprop": "content|ids",
                }
            )
            query = response.get("query", {})
            # Callers hold raw GlobalUsage titles (often underscored); the API
            # answers with its normalized form. Map back so lookups never miss.
            aliases: dict[str, str] = {}
            for kind in ("normalized", "converted"):
                for entry in query.get(kind) or []:
                    source, target = entry.get("from"), entry.get("to")
                    if source and target:
                        aliases[str(source)] = str(target)
            requested_by_final: dict[str, str] = {}
            for requested in batch:
                final = requested
                for _ in range(len(aliases) + 1):
                    if final not in aliases:
                        break
                    final = aliases[final]
                requested_by_final[final] = requested
            for page in query.get("pages", []):
                title = str(page.get("title", ""))
                key = requested_by_final.get(title, title)
                if page.get("missing") or not page.get("revisions"):
                    results[key] = PageRevision(title=title, revid=0, text="", missing=True)
                    continue
                revision = page["revisions"][0]
                content = revision.get("slots", {}).get("main", {}).get("content", "")
                results[key] = PageRevision(
                    title=title,
                    revid=int(revision.get("revid", 0)),
                    text=str(content),
                    missing=False,
                )
        return results

    def current_revid(self, title: str) -> int | None:
        response = self._request(
            {
                "action": "query",
                "titles": title,
                "prop": "revisions",
                "rvslots": "main",
                "rvprop": "ids",
                "rvlimit": "1",
            }
        )
        page = self._single_page(response)
        revisions = page.get("revisions")
        if page.get("missing") or not revisions:
            return None
        return int(revisions[0]["revid"])

    def global_usage(
        self,
        file_title: str,
        *,
        hosts: set[str] | None = None,
        namespaces: set[int] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List GlobalUsage rows, bounded by eligible rows seen for `hosts`."""
        params: dict[str, Any] = {
            "action": "query",
            "prop": "globalusage",
            "titles": file_title,
            "guprop": "namespace|pageid|url",
            "gulimit": str(GLOBAL_USAGE_LIMIT),
        }
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        while True:
            response = self._request(params)
            page = self._single_page(response)
            for row in page.get("globalusage", []):
                if "ns" not in row:
                    raise ApiError("badresponse", "globalusage row has no ns field")
                wiki = str(row.get("wiki", ""))
                if hosts is not None and wiki not in hosts:
                    continue
                if namespaces is not None and int(row.get("ns", -1)) not in namespaces:
                    continue
                key = (str(row.get("wiki", "")), str(row.get("title", "")))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
                if limit is not None and len(rows) >= limit:
                    return rows
            continuation = response.get("continue")
            if not continuation:
                return rows
            params.update(continuation)

    def login(self, credentials: Credentials) -> None:
        """Establish a session with a BotPasswords login (`Username@label`).

        Bot passwords authenticate through the legacy `action=login` endpoint,
        matching pywikibot's proven flow; `clientlogin` is for plain accounts.
        """
        if self._logged_in:
            return
        try:
            token_response = self._request({"action": "query", "meta": "tokens", "type": "login"})
            login_token = token_response["query"]["tokens"]["logintoken"]
            response = self._request(
                {
                    "action": "login",
                    "lgname": credentials.username,
                    "lgpassword": credentials.password,
                    "lgtoken": login_token,
                },
                post=True,
            )
        except ApiError:
            raise AuthError("loginfailed", "authentication request failed") from None
        result = response.get("login", {})
        if result.get("result") != "Success":
            raise AuthError("loginfailed", "login did not establish a session")
        self._logged_in = True

    def csrf_token(self) -> str:
        response = self._request({"action": "query", "meta": "tokens", "type": "csrf"})
        token = str(response["query"]["tokens"]["csrftoken"])
        if token == "+\\":
            raise AuthError("notauthenticated", "no CSRF token; log in before editing")
        return token

    def edit(self, *, title: str, text: str, summary: str, base_revid: int) -> int:
        """Publish one edit; returns the new revision id.

        Fails with EditConflict before submitting if the page is no longer at
        `base_revid`, and passes `baserevid` so the server enforces it too.
        """
        current = self.current_revid(title)
        if current is None:
            raise EditConflict("pagelost", f"{title} no longer exists")
        if current != base_revid:
            raise EditConflict(
                "editconflict", f"latest revision is {current}, expected {base_revid}"
            )
        token = self.csrf_token()
        try:
            response = self._request(
                {
                    "action": "edit",
                    "title": title,
                    "text": text,
                    "summary": summary,
                    "baserevid": str(base_revid),
                    "token": token,
                    "assert": "user",
                    "maxlag": "5",
                },
                post=True,
            )
        except ApiError as exc:
            if exc.code == "editconflict":
                raise EditConflict(exc.code, exc.info) from None
            if exc.code in EDIT_REJECTED_CODES:
                raise EditRejected(exc.code, exc.info) from None
            raise
        result = response.get("edit", {})
        if result.get("result") != "Success":
            raise EditRejected(str(result.get("result", "unknown")), "edit did not succeed")
        revid = result.get("newrevid")
        if not isinstance(revid, int) or isinstance(revid, bool) or revid <= 0:
            raise ApiError("badresponse", "edit response has no valid revision acknowledgement")
        if "nochange" in result:
            raise EditRejected("nochange", "no edit was made")
        return revid
