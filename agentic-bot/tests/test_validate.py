"""Regression tests for wikitext proposal validation.

MediaWiki API responses are mocked with realistic formatversion=2 shapes at the
WikiClient.query_api seam. Validation must never report success for content it
could not verify, and must flag only problems NEWLY INTRODUCED by a proposal.
Link/template names come from authoritative parser output (action=parse
links/iwlinks/templates); regex extraction is used only for section fragments
and template named parameters, which the parser does not expose.
"""

from __future__ import annotations

from agentic_bot.models import PageSnapshot
from agentic_bot.store import ProposalStore
from agentic_bot.validate import (
    ValidationResult,
    extract_link_fragments,
    extract_template_params,
    validate_proposal,
)

# ---------------------------------------------------------------------------
# Canned MediaWiki API responses (formatversion=2)
# ---------------------------------------------------------------------------


def exists(title: str, **kwargs) -> dict:
    return {"pageid": 1, "ns": 0, "title": title, "contentmodel": "wikitext", **kwargs}


def missing(title: str) -> dict:
    return {"ns": 0, "title": title, "missing": True}


def link(title: str, ns: int = 0, exists_flag: bool = True) -> dict:
    return {"ns": ns, "title": title, "exists": exists_flag}


def parse_body(**fields) -> dict:
    body = {
        "parsewarnings": [],
        "links": [],
        "iwlinks": [],
        "templates": [],
        "categories": [],
        "images": [],
        "sections": [],
    }
    body.update(fields)
    return {"parse": {"title": "TestPage", **body}}


class Responder:
    """Route validate_proposal's API calls to canned responses.

    titles: requested title -> page entry (default: existing wikitext page).
    redirects: requested title -> redirect target (target must be in titles).
    parse: key (text or page value) -> full parse response.
    templatedata: requested titles value -> full templatedata response.
    interwiki: interwiki prefixes returned by siteinfo interwikimap.
    """

    def __init__(
        self,
        *,
        titles: dict[str, dict] | None = None,
        redirects: dict[str, str] | None = None,
        parse: dict[str, dict] | None = None,
        templatedata: dict[str, dict] | None = None,
        interwiki: set[str] | None = None,
    ):
        self.titles = titles or {}
        self.redirects = redirects or {}
        self.parse = parse or {}
        self.templatedata = templatedata or {}
        self.interwiki = interwiki if interwiki is not None else {"en", "fr"}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, action: str, params: dict) -> dict:
        self.calls.append((action, params))
        if action == "query" and params.get("meta") == "siteinfo":
            return {
                "query": {
                    "interwikimap": [
                        {"prefix": p, "url": f"https://example.org/{p}"}
                        for p in sorted(self.interwiki)
                    ]
                }
            }
        if action == "query":
            titles = params["titles"].split("|")
            body = {"pages": [self.titles.get(t, exists(t)) for t in titles]}
            if any(t in self.redirects for t in titles):
                body["redirects"] = [
                    {"from": t, "to": self.redirects[t]} for t in titles if t in self.redirects
                ]
            return {"query": body}
        if action == "parse":
            key = params.get("text", params.get("page"))
            return self.parse.get(key, parse_body())
        if action == "templatedata":
            return self.templatedata.get(params["titles"], {"pages": {}})
        raise AssertionError(f"unexpected action {action!r}")


class FakeWiki:
    """Duck-typed WikiClient stub recording query_api calls."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[tuple[str, dict]] = []

    def query_api(self, action: str, **params) -> dict:
        self.calls.append((action, params))
        return self._handler(action, params)


def make_proposal(tmp_path, original: str, proposed: str, revid: int = 100):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", revid, "2026-01-01T00:00:00Z", original)
    return store.create(snap, proposed, "Edit summary", "Rationale", "Issue")


# ---------------------------------------------------------------------------
# Extraction: fragments and template parameters only (names come from the
# parser). Deliberately not a wikitext parser.
# ---------------------------------------------------------------------------


def test_extract_link_fragments_includes_namespaced_targets():
    text = (
        "[[Foo]] and [[Bar#Sec One]] and [[Baz|label]] and [[#Local Anchor]] "
        "and [[Вікіпедыя:П#Сэкцыя]] and [[en:Earth#Hist]]"
    )
    fragments = extract_link_fragments(text)
    assert set(fragments) == {"Foo", "Bar", "Baz", "", "Вікіпедыя:П", "en:Earth"}
    assert fragments["Foo"] == frozenset({""})
    assert fragments["Bar"] == frozenset({"Sec One"})
    assert fragments[""] == frozenset({"Local Anchor"})
    assert fragments["Вікіпедыя:П"] == frozenset({"Сэкцыя"})
    assert fragments["en:Earth"] == frozenset({"Hist"})


def test_extract_link_fragments_ignores_comments_and_nowiki():
    text = "<nowiki>[[Ghost]]</nowiki> <!-- [[Cmt]] --> [[Real]]"
    assert set(extract_link_fragments(text)) == {"Real"}


def test_extract_template_params_names():
    text = (
        "{{Infobox|known=1|other=2}} {{subst:Foo}} {{#if:x|y}} {{!}} "
        "{{{1}}} {{A|{{B|c=1}}}} {{Template:Prefixed|p=1}} {{Вікіпедыя:Х|q=1}}"
    )
    params, complex_args = extract_template_params(text)
    assert set(params) == {"Infobox", "Foo", "!", "A", "B", "Prefixed", "Вікіпедыя:Х"}
    assert params["Infobox"] == frozenset({"known", "other"})
    assert params["Foo"] == frozenset()
    assert params["B"] == frozenset({"c"})
    assert params["Prefixed"] == frozenset({"p"})
    assert params["Вікіпедыя:Х"] == frozenset({"q"})
    assert complex_args == 1  # {{A|{{B|c=1}}}}


# ---------------------------------------------------------------------------
# validate_proposal: regression detection and classification
# ---------------------------------------------------------------------------


def test_introduced_missing_namespaced_link_is_warning(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[Вікіпедыя:Няісная]]")
    resp = Responder(
        titles={"Вікіпедыя:Няісная": missing("Вікіпедыя:Няісная")},
        parse={
            proposal.proposed_content: parse_body(
                links=[link("Вікіпедыя:Няісная", ns=4, exists_flag=False)]
            )
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("Вікіпедыя:Няісная" in w for w in result.warnings)


def test_introduced_existing_namespaced_link_is_clean(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[Вікіпедыя:Гаджэты]]")
    resp = Responder(
        parse={proposal.proposed_content: parse_body(links=[link("Вікіпедыя:Гаджэты", ns=4)])}
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert not result.warnings


def test_introduced_missing_link_is_warning_regression_only(tmp_path):
    old = "[[OldMissing]] [[Exists]]"
    proposal = make_proposal(tmp_path, old, "[[OldMissing]] [[Exists]] [[NewMissing]]")
    resp = Responder(
        titles={
            "OldMissing": missing("OldMissing"),
            "NewMissing": missing("NewMissing"),
            "Exists": exists("Exists"),
        },
        parse={
            old: parse_body(links=[link("OldMissing", exists_flag=False), link("Exists")]),
            proposal.proposed_content: parse_body(
                links=[
                    link("OldMissing", exists_flag=False),
                    link("Exists"),
                    link("NewMissing", exists_flag=False),
                ]
            ),
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("NewMissing" in w for w in result.warnings)
    assert not any("OldMissing" in w for w in result.warnings)
    assert not any("Exists" in w for w in result.warnings)


def test_introduced_redirect_link_is_warning_not_error(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[R]]")
    resp = Responder(
        titles={"R": exists("Target"), "Target": exists("Target")},
        redirects={"R": "Target"},
        parse={proposal.proposed_content: parse_body(links=[link("R")])},
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("R" in w and "redirect" in w for w in result.warnings)


def test_introduced_missing_template_is_error(tmp_path):
    proposal = make_proposal(tmp_path, "", "{{GhostBox|x=1}}")
    resp = Responder(
        titles={"Template:GhostBox": missing("Template:GhostBox")},
        parse={
            proposal.proposed_content: parse_body(
                templates=[link("Template:GhostBox", ns=10, exists_flag=False)],
                links=[link("Template:GhostBox", ns=10, exists_flag=False)],
            )
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert result.has_errors
    assert any("GhostBox" in e for e in result.errors)


def test_missing_transclusion_reported_once(tmp_path):
    proposal = make_proposal(tmp_path, "", "{{GhostBox}}")
    resp = Responder(
        titles={"Template:GhostBox": missing("Template:GhostBox")},
        parse={
            proposal.proposed_content: parse_body(
                templates=[link("Template:GhostBox", ns=10, exists_flag=False)],
                links=[link("Template:GhostBox", ns=10, exists_flag=False)],
            )
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    ghost_errors = [e for e in result.errors if "GhostBox" in e]
    assert len(ghost_errors) == 1


def test_link_to_missing_template_is_warning_but_transclusion_blocks(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[Шаблон:Red]] {{Ghost}} {{#invoke:Absent|main}}")
    resp = Responder(
        titles={t: missing(t) for t in ("Шаблон:Red", "Шаблон:Ghost", "Модуль:Absent")},
        parse={
            proposal.proposed_content: parse_body(
                links=[
                    link(t, exists_flag=False)
                    for t in ("Шаблон:Red", "Шаблон:Ghost", "Модуль:Absent")
                ],
                templates=[
                    link("Шаблон:Ghost", ns=10, exists_flag=False),
                    link("Модуль:Absent", ns=828, exists_flag=False),
                ],
            )
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert len(result.warnings) == 1 and "Шаблон:Red" in result.warnings[0]
    assert len(result.errors) == 2
    assert any("Шаблон:Ghost" in e for e in result.errors)
    assert any("Модуль:Absent" in e for e in result.errors)


def test_new_transclusion_of_preexisting_red_link_still_blocks(tmp_path):
    proposal = make_proposal(tmp_path, "[[Template:Ghost]]", "[[Template:Ghost]] {{Ghost}}")
    resp = Responder(
        titles={"Template:Ghost": missing("Template:Ghost")},
        parse={
            proposal.page.content: parse_body(
                links=[link("Template:Ghost", ns=10, exists_flag=False)]
            ),
            proposal.proposed_content: parse_body(
                links=[link("Template:Ghost", ns=10, exists_flag=False)],
                templates=[link("Template:Ghost", ns=10, exists_flag=False)],
            ),
        },
    )
    assert validate_proposal(FakeWiki(resp), proposal).has_errors


def test_complex_argument_note_scoped_to_introduced(tmp_path):
    """Pre-existing complex invocations are not the proposal's problem —
    live: Мінск had 34/34 old/new and every proposal showed INCOMPLETE."""
    base = "{{A|{{B}}}}"
    proposal = make_proposal(tmp_path, base, base)
    result = validate_proposal(FakeWiki(Responder()), proposal)
    assert not any("complex" in u for u in result.unverified)


def test_newly_introduced_complex_argument_note(tmp_path):
    base = "{{A|{{B}}}}"
    proposal = make_proposal(tmp_path, base, base + " і яшчэ {{A|{{C}}}}")
    result = validate_proposal(FakeWiki(Responder()), proposal)
    note = next((u for u in result.unverified if "complex" in u), "")
    assert "1 template invocation" in note  # diff count (1), not total (2)


def test_missing_template_skips_templatedata_query(tmp_path):
    """A confirmed-missing template must not also produce a TemplateData
    availability note — the existence error is the whole verdict."""
    proposal = make_proposal(tmp_path, "", "{{GhostBox|x=1}}")
    resp = Responder(
        titles={"Template:GhostBox": missing("Template:GhostBox")},
        parse={
            proposal.proposed_content: parse_body(
                templates=[link("Template:GhostBox", ns=10, exists_flag=False)],
                links=[link("Template:GhostBox", ns=10, exists_flag=False)],
            )
        },
    )
    fake = FakeWiki(resp)
    result = validate_proposal(fake, proposal)
    assert result.has_errors
    assert not any("TemplateData" in u for u in result.unverified)
    assert not any(action == "templatedata" for action, _ in fake.calls)


def test_missing_template_skip_matches_localized_parser_title(tmp_path):
    """On be.wiki the parser lists transclusions in the local namespace
    spelling ('Шаблон:X') while a bare '{{X|p=1}}' invocation keys as 'X' —
    the skip must map the invocation through the parser's listing, not
    compare English-only namespace spellings."""
    proposal = make_proposal(tmp_path, "", "{{Ghost|x=1}}")
    resp = Responder(
        titles={"Шаблон:Ghost": missing("Шаблон:Ghost")},
        parse={
            proposal.proposed_content: parse_body(
                templates=[link("Шаблон:Ghost", ns=10, exists_flag=False)],
                links=[link("Шаблон:Ghost", ns=10, exists_flag=False)],
            )
        },
    )
    fake = FakeWiki(resp)
    result = validate_proposal(fake, proposal)
    assert result.has_errors
    assert any("Шаблон:Ghost" in e for e in result.errors)
    assert not any("TemplateData" in u for u in result.unverified)
    assert not any(action == "templatedata" for action, _ in fake.calls)


def test_interwiki_links_noted_not_flagged(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[en:Earth]]")
    resp = Responder(
        parse={
            proposal.proposed_content: parse_body(
                iwlinks=[{"prefix": "en", "url": "u", "title": "en:Earth"}]
            )
        }
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("not checked" in u for u in result.unverified)


def test_plain_form_interwiki_counted_via_interwikimap(tmp_path):
    """Plain ``[[en:Earth]]`` is invisible to parse (links/iwlinks both empty,
    verified live); interwikimap is the authoritative fallback for counting."""
    proposal = make_proposal(tmp_path, "", "бачым [[en:Earth]] тут")
    resp = Responder()  # parse returns empty links/iwlinks, interwikimap has "en"
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert not result.warnings
    assert any("not checked" in u for u in result.unverified)


def test_plain_interwiki_anchor_pair_is_counted_not_warned(tmp_path):
    """A fragment on a plain interwiki link must not trigger a sections check
    against a non-local title (live: parse&page=en:Earth raises invalidtitle)."""
    proposal = make_proposal(tmp_path, "", "[[en:Earth#History]]")
    resp = Responder()
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert not result.warnings  # no false "no such heading" warning
    assert all("not checked" in u for u in result.unverified)


def test_namespaced_page_anchor_is_checked(tmp_path):
    """Anchors on local namespaced pages are checked, never skipped as
    interwiki (interwiki classification must not swallow local namespaces)."""
    proposed = "[[Вікіпедыя:Гаджэты#НяіснаяСэкцыя]]"
    proposal = make_proposal(tmp_path, "", proposed)
    resp = Responder(
        parse={
            proposed: parse_body(links=[link("Вікіпедыя:Гаджэты", ns=4)]),
            "Вікіпедыя:Гаджэты": parse_body(sections=[{"index": "1", "anchor": "Іншая"}]),
        }
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("НяіснаяСэкцыя" in w for w in result.warnings)


def test_categories_and_files_noted_not_flagged(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[Катэгорыя:НяіснаяКатэгорыя]] [[Файл:Example.jpg]]")
    resp = Responder(
        parse={
            proposal.proposed_content: parse_body(
                categories=[{"sortkey": "", "category": "НяіснаяКатэгорыя", "missing": True}],
                images=["Example.jpg"],
            )
        }
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("not checked" in u for u in result.unverified)


def test_parser_resolved_magic_words_need_no_checks(tmp_path):
    proposal = make_proposal(tmp_path, "", "{{PAGENAME}} and {{!}}")
    resp = Responder()  # parse.templates is empty: parser resolved them
    fake = FakeWiki(resp)
    result = validate_proposal(fake, proposal)
    assert not result.has_errors
    template_queries = [
        c for c in fake.calls if c[0] == "query" and "Template:" in c[1].get("titles", "")
    ]
    assert not template_queries


def test_unknown_named_parameter_is_warning(tmp_path):
    proposal = make_proposal(tmp_path, "", "{{Infobox|known=1|bogus=2}}")
    resp = Responder(
        parse={
            proposal.proposed_content: parse_body(
                templates=[link("Template:Infobox", ns=10)],
                links=[link("Template:Infobox", ns=10)],
            )
        },
        templatedata={
            "Template:Infobox": {
                "pages": {
                    "5": {
                        "pageid": 5,
                        "title": "Template:Infobox",
                        "params": {"known": {"label": "k"}},
                    }
                }
            }
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("bogus" in w for w in result.warnings)
    assert not any("'known'" in w for w in result.warnings)


def test_templatedata_absent_is_unverified_not_success(tmp_path):
    proposal = make_proposal(tmp_path, "", "{{Infobox|known=1}}")
    resp = Responder(
        parse={
            proposal.proposed_content: parse_body(
                templates=[link("Template:Infobox", ns=10)],
                links=[link("Template:Infobox", ns=10)],
            )
        },
        templatedata={
            "Template:Infobox": {"pages": {"5": {"pageid": 5, "title": "Template:Infobox"}}}
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("Template:Infobox" in u for u in result.unverified)
    assert "PASSED" not in result.summary()


def test_parse_warning_regression_diff(tmp_path):
    proposal = make_proposal(tmp_path, "a", "b")
    resp = Responder(
        parse={
            "a": parse_body(parsewarnings=["w1"]),
            "b": parse_body(parsewarnings=["w1", "w2"]),
        }
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("w2" in w for w in result.warnings)
    assert not any("w1" in w for w in result.warnings)


def test_anchor_mismatch_is_warning(tmp_path):
    proposed = "[[Page#Nope]] [[Page#Yep]] [[#Here]]"
    proposal = make_proposal(tmp_path, "", proposed)
    resp = Responder(
        titles={"Page": exists("Page")},
        parse={
            proposed: parse_body(
                links=[link("Page")],
                sections=[{"index": "1", "anchor": "Here"}],
            ),
            "Page": parse_body(sections=[{"index": "1", "anchor": "Yep"}]),
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert any("Nope" in w for w in result.warnings)
    assert not any("Yep" in w or "Here" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# validate_proposal: failure handling — never a false success
# ---------------------------------------------------------------------------


def test_non_wikitext_page_is_skipped_unverified(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[NewMissing]]")
    resp = Responder(titles={"TestPage": exists("TestPage", contentmodel="javascript")})
    fake = FakeWiki(resp)
    result = validate_proposal(fake, proposal)
    assert not result.has_errors
    assert any("javascript" in u for u in result.unverified)
    assert len(fake.calls) == 1  # content-model query only; no other checks ran
    assert "PASSED" not in result.summary()


def test_api_failure_yields_unverified_never_success(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[NewMissing]]")

    def broken(action, params):
        raise RuntimeError("api down")

    result = validate_proposal(FakeWiki(broken), proposal)
    assert not result.has_errors
    assert result.unverified
    assert "PASSED" not in result.summary()
    assert "FAILED" not in result.summary()


def test_unrecognized_response_shape_yields_unverified(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[X]]")
    result = validate_proposal(FakeWiki(lambda a, p: {"unexpected": True}), proposal)
    assert not result.has_errors
    assert result.unverified
    assert "PASSED" not in result.summary()


def test_malformed_parsewarnings_is_unverified_not_clean(tmp_path):
    proposal = make_proposal(tmp_path, "old", "new")
    bad = parse_body(parsewarnings=[{"unexpected": "warning"}])
    resp = Responder(parse={"old": bad, "new": bad})
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert result.unverified
    assert "INCOMPLETE" in result.summary()
    assert "PASSED" not in result.summary()


def test_missing_requested_parse_fields_is_unverified(tmp_path):
    proposal = make_proposal(tmp_path, "old", "new")
    resp = Responder(
        parse={
            "old": {"parse": {"title": "TestPage"}},  # requested fields not returned
            "new": parse_body(),
        }
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert result.unverified
    assert "PASSED" not in result.summary()
    assert any("base revision" in u for u in result.unverified)


def test_malformed_link_entry_is_unverified_not_clean(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[X]]")
    resp = Responder(
        parse={proposal.proposed_content: parse_body(links=[{"ns": 0, "exists": True}])}
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert result.unverified
    assert "PASSED" not in result.summary()


def test_malformed_section_entry_is_unverified_no_false_warning(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[Page#X]]")
    resp = Responder(
        titles={"Page": exists("Page")},
        parse={
            proposal.proposed_content: parse_body(links=[link("Page")]),
            "Page": parse_body(sections=[{"line": "X"}]),
        },
    )
    result = validate_proposal(FakeWiki(resp), proposal)
    assert not result.has_errors
    assert not result.warnings  # unverifiable, not a mismatch warning
    assert any("could not be checked" in u for u in result.unverified)


def test_missing_client_is_unverified(tmp_path):
    proposal = make_proposal(tmp_path, "", "[[X]]")
    result = validate_proposal(None, proposal)
    assert not result.has_errors
    assert result.unverified
    assert "PASSED" not in result.summary()


# ---------------------------------------------------------------------------
# ValidationResult semantics
# ---------------------------------------------------------------------------


def test_validation_result_freshness():
    result = ValidationResult(version=2, base_revid=105)
    assert result.is_fresh(2, 105)
    assert not result.is_fresh(3, 105)
    assert not result.is_fresh(2, 106)


def test_summary_success_only_when_fully_verified():
    passed = ValidationResult(version=1, base_revid=1)
    assert "PASSED" in passed.summary()
    assert "PASSED" not in ValidationResult(version=1, base_revid=1, warnings=("w",)).summary()
    assert "PASSED" not in ValidationResult(version=1, base_revid=1, unverified=("u",)).summary()
    assert "FAILED" in ValidationResult(version=1, base_revid=1, errors=("e",)).summary()
