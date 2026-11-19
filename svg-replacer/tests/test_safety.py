"""AI-assisted regressions for reviewed safety boundaries; no network or credentials."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from svg_replacer import cli
from svg_replacer.api import ApiError, MediaWikiApi
from svg_replacer.creds import Credentials
from svg_replacer.ui import Decider
from svg_replacer.wikitext import FileNamespace, assess_usage, replace_usage
from svg_replacer.workflow import Proposal


@pytest.mark.parametrize(
    "opening,closing",
    [
        ("<nowiki >", "</nowiki>"),
        ('<nowiki class="x">', "</nowiki>"),
        ("<pre>", "</pre>"),
        ('<syntaxhighlight lang="wikitext">', "</syntaxhighlight>"),
        ('<source lang="text">', "</source>"),
        ("<math>", "</math>"),
        ("<!--", "-->"),
        ("<nowiki>", ""),
    ],
)
def test_literal_content_is_never_replaceable(opening, closing):
    text = f"{opening}[[File:Old.png]]{closing}"
    assert assess_usage(text, "Old.png", FileNamespace.of("File")).status != "replace"


def test_braces_in_comments_do_not_block_real_image():
    text = "<!-- {{ -->\n[[File:Old.png|caption]]"
    new, count = replace_usage(text, "Old.png", "New.svg", FileNamespace.of("File"))
    assert count == 1
    assert new == "<!-- {{ -->\n[[File:New.svg|caption]]"


def test_credentials_repr_hides_password():
    assert "SYNTHETIC_SECRET" not in repr(Credentials("example@bot", "SYNTHETIC_SECRET"))


@pytest.mark.parametrize(
    "result",
    [
        {"result": "Success"},
        {"result": "Success", "newrevid": 0},
        {"result": "Success", "newrevid": "garbage"},
        {"result": "Success", "nochange": True},
        {"result": "Success", "nochange": True, "newrevid": 123},
    ],
)
def test_edit_requires_revision_acknowledgement(result):
    def transport(url, data):
        p = parse_qs(data.decode() if data else urlsplit(url).query)
        if p.get("action") == ["edit"]:
            response = {"edit": result}
        elif p.get("meta") == ["tokens"]:
            response = {"query": {"tokens": {"csrftoken": "synthetic"}}}
        else:
            response = {"query": {"pages": [{"revisions": [{"revid": 123}]}]}}
        return json.dumps(response).encode()

    api = MediaWikiApi("example.invalid", transport=transport, sleep=lambda _: None)
    with pytest.raises(ApiError):
        api.edit(title="Example", text="new", summary="test", base_revid=123)


def test_login_errors_do_not_echo_server_secrets():
    def transport(url, data):
        if data:
            return json.dumps({"error": {"code": "failed", "info": "SYNTHETIC_SECRET"}}).encode()
        return json.dumps({"query": {"tokens": {"logintoken": "synthetic"}}}).encode()

    api = MediaWikiApi("example.invalid", transport=transport, sleep=lambda _: None)
    with pytest.raises(ApiError) as exc:
        api.login(Credentials("example@bot", "SYNTHETIC_SECRET"))
    assert "SYNTHETIC_SECRET" not in str(exc.value)


def test_http_errors_do_not_display_raw_bodies(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError(
                "https://example.invalid", 403, "Forbidden", {}, io.BytesIO(b"SYNTHETIC_SECRET")
            )

    monkeypatch.setattr("svg_replacer.api.build_opener", lambda *args: Opener())
    api = MediaWikiApi("example.invalid", sleep=lambda _: None)
    with pytest.raises(ApiError) as exc:
        api.imageinfo("File:Example.png")
    assert "SYNTHETIC_SECRET" not in str(exc.value)


def test_terminal_controls_are_visible_not_executed():
    out = io.StringIO()
    proposal = Proposal(
        "page",
        "Title",
        "",
        ["\x1b[2Jhidden"],
        "-old\n+new\x1b]52;c;payload\x07\n",
        "summary",
        "Old.png",
        "New.svg",
    )
    Decider(input_fn=lambda _: "s", out=out)(proposal)
    assert "\x1b" not in out.getvalue()
    assert "\x07" not in out.getvalue()
    assert "payload" in out.getvalue()


@pytest.mark.parametrize(
    "case",
    [
        "not-svg",
        "not-raster",
        "same-file",
        "local-raster",
        "local-svg",
        "wrong-shared",
        "valid",
        "tracking",
        "preview",
        "missing-commons",
    ],
)
def test_cli_validates_file_pair_before_discovery(monkeypatch, capsys, case):
    class FakeApi:
        def __init__(self, host):
            self.host = host

        def imageinfo(self, title):
            svg = title.endswith(".svg")
            mime = "image/svg+xml" if svg else "image/png"
            if case == "not-svg" and svg:
                mime = "image/png"
            if case == "not-raster" and not svg:
                mime = "application/pdf"
            repository = "shared"
            if self.host != "commons.wikimedia.org" and (
                (case == "local-svg" and svg) or (case == "local-raster" and not svg)
            ):
                repository = "local"
            url = "https://upload.wikimedia.org/" + title
            if self.host != "commons.wikimedia.org" and case == "wrong-shared":
                url += "-different"
            if case == "tracking":
                url += f"?utm_source={self.host}"
            return SimpleNamespace(
                title=title,
                missing=False,
                mime=mime,
                repository=repository,
                url=url,
                width=10,
                height=10,
                description_url="https://example.invalid",
                thumb_url=None,
            )

        def page_revisions(self, titles):
            return {
                title: SimpleNamespace(
                    title=title,
                    missing=case == "missing-commons" and title.endswith(".png"),
                    text=(
                        ""
                        if case == "preview"
                        or (case == "missing-commons" and title.endswith(".png"))
                        else "{{Vector version available|New.svg}}"
                    ),
                    revid=1,
                )
                for title in titles
            }

        def file_namespaces(self):
            return FileNamespace.of("File")

        def site_db_name(self):
            return "bewiki"

        def global_usage(self, *args, **kwargs):
            if case in {"valid", "tracking", "preview", "missing-commons"}:
                return []
            pytest.fail("invalid files reached discovery")

    monkeypatch.setattr(cli, "MediaWikiApi", FakeApi)
    monkeypatch.setattr(cli, "confirm", lambda _: True)
    monkeypatch.setattr(cli, "Decider", lambda **kwargs: lambda proposal: "approve")
    raster = "File:New.svg" if case == "same-file" else "File:Old.png"
    result = cli.main(["File:New.svg", "--raster", raster, "--wiki", "be"])
    if case == "preview":
        assert result == 0
        shown = capsys.readouterr().out
        assert "PREVIEW" in shown
        assert "0 saved, 1 previewed" in shown
        assert "not saved" in shown
    elif case == "missing-commons":
        assert result == 1
        assert "failed" in capsys.readouterr().out.lower()
    elif case in {"valid", "tracking"}:
        assert result == 0
        assert "0 saved, 0 previewed" in capsys.readouterr().out
    else:
        assert result != 0
        assert "error:" in capsys.readouterr().err


def test_globalusage_limit_counts_only_eligible_unique_pages():
    calls = []

    def transport(url, data):
        calls.append(url)
        pages = [
            {
                "title": "File:Old.png",
                "globalusage": [
                    {"wiki": "be.wikipedia.org", "title": "Talk:X", "ns": 1},
                    {"wiki": "be.wikipedia.org", "title": "A", "ns": 0},
                    {"wiki": "be.wikipedia.org", "title": "A", "ns": 0},
                    {"wiki": "be.wikipedia.org", "title": "B", "ns": 0},
                ],
            }
        ]
        return json.dumps({"query": {"pages": pages}, "continue": {"gucontinue": "next"}}).encode()

    api = MediaWikiApi("example.invalid", transport=transport, sleep=lambda _: None)
    rows = api.global_usage("File:Old.png", hosts={"be.wikipedia.org"}, namespaces={0}, limit=2)
    assert [row["title"] for row in rows] == ["A", "B"]
    assert len(calls) == 1


def test_cli_without_arguments_prompts_for_svg_link(monkeypatch, capsys):
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return "https://not-commons.invalid/wiki/File:Example.svg"

    monkeypatch.setattr("builtins.input", answer)
    assert cli.main([]) == 2
    assert prompts and "SVG" in prompts[0]
    assert "expected a commons.wikimedia.org URL" in capsys.readouterr().err


def _recording_api(log: list) -> type:
    """Multi-wiki stand-in that records discovery and write calls in order."""

    class FakeApi:
        def __init__(self, host):
            self.host = host

        def imageinfo(self, title):
            svg = title.endswith(".svg")
            return SimpleNamespace(
                title=title,
                missing=False,
                mime="image/svg+xml" if svg else "image/png",
                repository="shared",
                url="https://upload.wikimedia.org/" + title,
                width=10,
                height=10,
                description_url="https://example.invalid",
                thumb_url=None,
            )

        def page_revisions(self, titles):
            pages = {}
            for title in titles:
                if title.endswith(".svg"):
                    text = "{{Derived from|File:Old.png}}"
                elif title.endswith(".png"):
                    text = "{{Convert to SVG}}\n[[File:Old.png|thumb|x]]"
                else:
                    text = "[[File:Old.png|thumb|Апісанне]]"
                pages[title] = SimpleNamespace(title=title, missing=False, text=text, revid=1)
            return pages

        def file_namespaces(self):
            return FileNamespace.of("File")

        def global_usage(self, *args, **kwargs):
            log.append(("discovery", self.host))
            return [
                {
                    "wiki": "be.wikipedia.org",
                    "title": "Артыкул",
                    "ns": 0,
                    "pageid": 1,
                    "url": "https://be.wikipedia.org/wiki/Артыкул",
                }
            ]

        def login(self, credentials):
            log.append(("login", self.host))

        def edit(self, *, title, text, summary, base_revid):
            log.append(("edit", self.host, title))
            return 7

    return FakeApi


def _drive_cli(monkeypatch, log: list, decision: str) -> int:
    monkeypatch.setattr(cli, "MediaWikiApi", _recording_api(log))
    monkeypatch.setattr(cli, "load_credentials", lambda path: Credentials("user@bot", "synthetic"))
    monkeypatch.setattr(cli, "confirm", lambda _: True)
    monkeypatch.setattr(cli, "Decider", lambda **kwargs: lambda proposal: decision)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    return cli.main(["File:New.svg", "--raster", "File:Old.png", "--wiki", "be"])


def test_cli_commons_description_edit_precedes_discovery_and_article_edits(monkeypatch):
    log: list = []
    result = _drive_cli(monkeypatch, log, "approve")

    assert result == 0
    assert log.count(("edit", "commons.wikimedia.org", "File:Old.png")) == 1
    assert log.count(("edit", "be.wikipedia.org", "Артыкул")) == 1
    assert log.index(("edit", "commons.wikimedia.org", "File:Old.png")) < log.index(
        ("discovery", "commons.wikimedia.org")
    )
    assert log.index(("discovery", "commons.wikimedia.org")) < log.index(
        ("edit", "be.wikipedia.org", "Артыкул")
    )


def test_cli_quit_at_commons_step_stops_before_article_work(monkeypatch, capsys):
    log: list = []
    result = _drive_cli(monkeypatch, log, "stop")

    assert result == 0
    assert [entry for entry in log if entry[0] == "edit"] == []
    assert [entry for entry in log if entry[0] == "discovery"] == []
    assert "Stopped" in capsys.readouterr().out


def test_cli_commons_skip_leaves_article_review_untouched(monkeypatch):
    log: list = []
    decisions = iter(["skip", "approve"])
    monkeypatch.setattr(cli, "MediaWikiApi", _recording_api(log))
    monkeypatch.setattr(cli, "load_credentials", lambda path: Credentials("user@bot", "synthetic"))
    monkeypatch.setattr(cli, "confirm", lambda _: True)
    monkeypatch.setattr(cli, "Decider", lambda **kwargs: lambda proposal: next(decisions))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    result = cli.main(["File:New.svg", "--raster", "File:Old.png", "--wiki", "be"])

    assert result == 0
    assert log.count(("edit", "commons.wikimedia.org", "File:Old.png")) == 0
    assert log.count(("edit", "be.wikipedia.org", "Артыкул")) == 1


def test_shared_image_does_not_need_local_description_page():
    response = {
        "query": {
            "pages": [
                {
                    "title": "File:Example.svg",
                    "missing": True,
                    "imagerepository": "shared",
                    "imageinfo": [
                        {"url": "https://upload.wikimedia.org/example.svg", "mime": "image/svg+xml"}
                    ],
                }
            ]
        }
    }
    api = MediaWikiApi(
        "example.invalid", transport=lambda *_: json.dumps(response).encode(), sleep=lambda _: None
    )
    info = api.imageinfo("File:Example.svg")
    assert not info.missing
    assert info.repository == "shared"


EDITS: list = []


class MultiWikiApi:
    """Stand-in covering the whole multi-wiki publishing surface."""

    def __init__(self, host):
        self.host = host

    def imageinfo(self, title):
        svg = title.endswith(".svg")
        return SimpleNamespace(
            title=title,
            missing=False,
            mime="image/svg+xml" if svg else "image/png",
            repository="shared",
            url="https://upload.wikimedia.org/" + title,
            width=10,
            height=10,
            description_url="https://example.invalid",
            thumb_url=None,
        )

    def page_revisions(self, titles):
        return {
            title: SimpleNamespace(title=title, missing=False, text="[[File:Old.png]]", revid=1)
            for title in titles
        }

    def file_namespaces(self):
        return FileNamespace.of("File")

    def global_usage(self, title, **kwargs):
        return [
            {"wiki": "en.wikipedia.org", "title": "En page", "ns": 0, "url": "u"},
            {"wiki": "ar.wikipedia.org", "title": "Ar page", "ns": 0, "url": "u"},
            {"wiki": "de.wikiversity.org", "title": "User:X", "ns": 2, "url": "u"},
        ]

    def login(self, credentials):
        pass

    def edit(self, title, text, summary, base_revid):
        EDITS.append((self.host, title))
        return 7


def run_multiwiki(
    monkeypatch, capsys, *, argv_extra=(), publish_answer=None, tty=False, decision="skip"
):
    EDITS.clear()
    asked = []

    def confirm(question):
        asked.append(question)
        return (publish_answer is True) if question.startswith("Publish") else True

    if tty:

        class Tty:
            def isatty(self):
                return True

        monkeypatch.setattr(cli.sys, "stdin", Tty())
    monkeypatch.setattr(cli, "MediaWikiApi", MultiWikiApi)
    monkeypatch.setattr(cli, "confirm", confirm)
    monkeypatch.setattr(cli, "Decider", lambda **kwargs: lambda proposal: decision)
    monkeypatch.setattr(
        cli, "load_credentials", lambda path: SimpleNamespace(username="u", password="p")
    )
    result = cli.main(["File:New.svg", "--raster", "File:Old.png", *argv_extra])
    return result, capsys.readouterr().out, asked


def test_default_scans_every_wiki_and_keeps_ns_filter(monkeypatch, capsys):
    result, shown, asked = run_multiwiki(monkeypatch, capsys)
    assert result == 0
    assert "Candidates on en.wikipedia.org" in shown
    assert "Candidates on ar.wikipedia.org" in shown
    assert "En page" in shown and "Ar page" in shown
    assert "User:X" not in shown
    assert shown.count("Commons notice:") == 1
    assert not any("Publish" in question for question in asked)


def test_wiki_selection_restricts_to_named_editions(monkeypatch, capsys):
    result, shown, _ = run_multiwiki(monkeypatch, capsys, argv_extra=("--wiki", "ar"))
    assert result == 0
    assert "Ar page" in shown
    assert "En page" not in shown


def test_publish_question_decides_mode(monkeypatch, capsys):
    result, shown, asked = run_multiwiki(
        monkeypatch, capsys, tty=True, publish_answer=True, decision="approve"
    )
    assert result == 0
    assert "PUBLISH" in shown
    assert any("Publish" in question for question in asked)
    assert ("en.wikipedia.org", "En page") in EDITS
    assert ("ar.wikipedia.org", "Ar page") in EDITS
    assert ("commons.wikimedia.org", "File:Old.png") in EDITS

    result, shown, asked = run_multiwiki(
        monkeypatch, capsys, tty=True, publish_answer=False, decision="approve"
    )
    assert result == 0
    assert "PREVIEW" in shown
    assert EDITS == []
