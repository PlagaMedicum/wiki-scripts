from __future__ import annotations

import os

from biblio import bootstrap
from biblio.bootstrap import BotRightRequiredError, normalize_bot_username
from biblio.models import CandidateSpec, NormalizationOptions, SourceSpec


def test_normalize_bot_username_converts_underscores_to_spaces():
    assert normalize_bot_username("User_Bot") == "User Bot"


def test_resolve_dotenv_path_uses_project_root_from_source_dir(tmp_path):
    spec = SourceSpec(
        source_dir=tmp_path / "sources" / "demo",
        source_id="demo",
        name="Demo",
        site_lang="be",
        family="wikipedia",
        insource_terms=("term",),
        isbns=(),
        keywords=(),
        candidate=CandidateSpec(must_contain_all=("term",), must_contain_any=()),
        template_name="Крыніцы/Тэст",
        template_without_pages="{{Крыніцы/Тэст}}",
        template_with_pages="{{Крыніцы/Тэст||{pages}}}",
        default_summary_format="Замена {{{template_name}}}",
        page_patterns=(),
        reject_patterns=(),
        regex_rules=(),
        alias_rules=(),
        normalization=NormalizationOptions(),
    )

    assert bootstrap.resolve_dotenv_path(spec) == tmp_path / ".env"


def test_create_site_bootstraps_before_import(monkeypatch, tmp_path):
    calls = []

    def fake_bootstrap(spec, base_dir):
        os.environ["PYWIKIBOT_DIR"] = str(base_dir)
        calls.append(("bootstrap", base_dir))
        return "User Bot"

    class FakeSite:
        def __init__(self, code, family, user):
            calls.append(("site", code, family, user))

        def login(self):
            calls.append(("login",))

        def has_right(self, right):
            calls.append(("has_right", right))
            return right == "bot"

    class FakePywikibot:
        Site = FakeSite

    def fake_import():
        calls.append(("import", os.environ.get("PYWIKIBOT_DIR")))
        return FakePywikibot

    spec = SourceSpec(
        source_dir=tmp_path / "sources" / "demo",
        source_id="demo",
        name="Demo",
        site_lang="be",
        family="wikipedia",
        insource_terms=("term",),
        isbns=(),
        keywords=(),
        candidate=CandidateSpec(must_contain_all=("term",), must_contain_any=()),
        template_name="Крыніцы/Тэст",
        template_without_pages="{{Крыніцы/Тэст}}",
        template_with_pages="{{Крыніцы/Тэст||{pages}}}",
        default_summary_format="Замена {{{template_name}}}",
        page_patterns=(),
        reject_patterns=(),
        regex_rules=(),
        alias_rules=(),
        normalization=NormalizationOptions(),
    )

    monkeypatch.setattr(bootstrap, "bootstrap_pywikibot_from_env", fake_bootstrap)
    monkeypatch.setattr(bootstrap, "import_fresh_pywikibot", fake_import)

    pywikibot_module, site = bootstrap.create_site(spec, tmp_path / ".pywikibot")

    assert pywikibot_module is FakePywikibot
    assert isinstance(site, FakeSite)
    assert calls == [
        ("bootstrap", tmp_path / ".pywikibot"),
        ("import", str(tmp_path / ".pywikibot")),
        ("site", "be", "wikipedia", "User Bot"),
        ("login",),
        ("has_right", "bot"),
    ]


def test_create_site_requires_bot_right(monkeypatch, tmp_path):
    def fake_bootstrap(spec, base_dir):
        os.environ["PYWIKIBOT_DIR"] = str(base_dir)
        return "User Bot"

    class FakeSite:
        def __init__(self, code, family, user):
            self.code = code
            self.family = family
            self.user = user

        def login(self):
            pass

        def has_right(self, right):
            return False

    class FakePywikibot:
        Site = FakeSite

    monkeypatch.setattr(bootstrap, "bootstrap_pywikibot_from_env", fake_bootstrap)
    monkeypatch.setattr(bootstrap, "import_fresh_pywikibot", lambda: FakePywikibot)

    spec = SourceSpec(
        source_dir=tmp_path / "sources" / "demo",
        source_id="demo",
        name="Demo",
        site_lang="be",
        family="wikipedia",
        insource_terms=("term",),
        isbns=(),
        keywords=(),
        candidate=CandidateSpec(must_contain_all=("term",), must_contain_any=()),
        template_name="Крыніцы/Тэст",
        template_without_pages="{{Крыніцы/Тэст}}",
        template_with_pages="{{Крыніцы/Тэст||{pages}}}",
        default_summary_format="Замена {{{template_name}}}",
        page_patterns=(),
        reject_patterns=(),
        regex_rules=(),
        alias_rules=(),
        normalization=NormalizationOptions(),
    )

    try:
        bootstrap.create_site(spec, tmp_path / ".pywikibot")
    except BotRightRequiredError as error:
        assert "lacks the local wiki `bot` right in this API session" in str(error)
        assert "High-volume (bot) access" in str(error)
    else:
        raise AssertionError("Expected create_site to require the bot right")
