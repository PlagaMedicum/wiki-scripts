from __future__ import annotations

import os
import sys
import types

from biblio import bootstrap
from biblio.bootstrap import BotRightRequiredError, normalize_bot_username
from biblio.models import CandidateSpec, NormalizationOptions, SourceSpec


def test_normalize_bot_username_converts_underscores_to_spaces():
    assert normalize_bot_username("User_Bot") == "User Bot"


def test_split_bot_password_login_splits_full_login():
    assert bootstrap.split_bot_password_login("User_Bot@local-run") == ("User Bot", "local-run")


def test_split_bot_password_login_requires_suffix():
    try:
        bootstrap.split_bot_password_login("User Bot")
    except RuntimeError as error:
        assert "Username@label" in str(error)
    else:
        raise AssertionError("Expected split_bot_password_login to require a suffix")


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
    monkeypatch.setattr(
        bootstrap,
        "patch_pywikibot_request_connection_error_handling",
        lambda: calls.append(("patch",)),
    )
    monkeypatch.setattr(
        bootstrap,
        "apply_pywikibot_runtime_config",
        lambda pywikibot, config: calls.append(("config", config.put_throttle)),
    )
    monkeypatch.setattr(
        bootstrap,
        "patch_pywikibot_wait_reporting",
        lambda: calls.append(("wait-hooks",)),
    )

    pywikibot_module, site = bootstrap.create_site(spec, tmp_path / ".pywikibot")

    assert pywikibot_module is FakePywikibot
    assert isinstance(site, FakeSite)
    assert calls == [
        ("bootstrap", tmp_path / ".pywikibot"),
        ("import", str(tmp_path / ".pywikibot")),
        ("config", 0.2),
        ("patch",),
        ("wait-hooks",),
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
    monkeypatch.setattr(
        bootstrap,
        "patch_pywikibot_request_connection_error_handling",
        lambda: None,
    )
    monkeypatch.setattr(bootstrap, "apply_pywikibot_runtime_config", lambda pywikibot, config: None)
    monkeypatch.setattr(bootstrap, "patch_pywikibot_wait_reporting", lambda: None)

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


def test_patch_pywikibot_request_connection_error_handling(monkeypatch):
    fake_api_requests = types.ModuleType("pywikibot.data.api._requests")
    fake_requests_exceptions = types.ModuleType("requests.exceptions")

    class FakeRequestsConnectionError(Exception):
        pass

    fake_requests_exceptions.ConnectionError = FakeRequestsConnectionError
    monkeypatch.setitem(sys.modules, "pywikibot.data.api._requests", fake_api_requests)
    monkeypatch.setitem(sys.modules, "requests.exceptions", fake_requests_exceptions)

    bootstrap.patch_pywikibot_request_connection_error_handling()

    assert fake_api_requests.ConnectionError is FakeRequestsConnectionError


def test_load_pywikibot_runtime_config_defaults(monkeypatch):
    monkeypatch.delenv("BIBLIO_MIN_THROTTLE", raising=False)
    monkeypatch.delenv("BIBLIO_PUT_THROTTLE", raising=False)
    monkeypatch.delenv("BIBLIO_MAX_RETRIES", raising=False)
    monkeypatch.delenv("BIBLIO_RETRY_WAIT", raising=False)
    monkeypatch.delenv("BIBLIO_RETRY_MAX", raising=False)
    monkeypatch.delenv("BIBLIO_MAXLAG", raising=False)
    monkeypatch.delenv("BIBLIO_NOISYSLEEP", raising=False)

    config = bootstrap.load_pywikibot_runtime_config()

    assert config == bootstrap.PywikibotRuntimeConfig()


def test_apply_pywikibot_runtime_config_sets_known_fields():
    class FakeConfig:
        minthrottle = 10
        put_throttle = 10
        max_retries = 10
        retry_wait = 10
        retry_max = 10
        maxlag = 10
        noisysleep = 10

    class FakePywikibot:
        config = FakeConfig()

    bootstrap.apply_pywikibot_runtime_config(
        FakePywikibot,
        bootstrap.PywikibotRuntimeConfig(
            min_throttle=0.2,
            put_throttle=1.5,
            max_retries=4,
            retry_wait=3,
            retry_max=12,
            maxlag=6,
            noisysleep=0.0,
        ),
    )

    assert FakePywikibot.config.minthrottle == 0.2
    assert FakePywikibot.config.put_throttle == 1.5
    assert FakePywikibot.config.max_retries == 4
    assert FakePywikibot.config.retry_wait == 3
    assert FakePywikibot.config.retry_max == 12
    assert FakePywikibot.config.maxlag == 6
    assert FakePywikibot.config.noisysleep == 0.0
