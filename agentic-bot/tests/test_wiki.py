from __future__ import annotations

import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from agentic_bot.wiki import (
    EditConflictDetectedError,
    InsufficientPermissionsError,
    WikiClient,
    WikiError,
    normalize_bot_username,
    split_bot_password_login,
)


def test_normalize_bot_username():
    assert normalize_bot_username("example_bot") == "Example bot"
    assert normalize_bot_username("example bot") == "Example bot"
    assert normalize_bot_username("Bot") == "Bot"


def test_split_bot_password_login():
    user, suffix = split_bot_password_login("example_bot@local")
    assert user == "Example bot"
    assert suffix == "local"

    with pytest.raises(WikiError):
        split_bot_password_login("InvalidLoginWithoutAt")


def test_login_keeps_bot_password_out_of_files(tmp_path, monkeypatch):
    site = MagicMock()
    site.logged_in.side_effect = [False, True]
    type(site).userinfo = property(lambda _: {"name": "Example bot", "id": 123}, lambda _: None)
    initial_login = site.login
    manager = MagicMock()
    fake_pywikibot = SimpleNamespace(
        Site=MagicMock(return_value=site),
        login=SimpleNamespace(ClientLoginManager=MagicMock(return_value=manager)),
    )
    monkeypatch.setattr("agentic_bot.wiki._PYWIKIBOT_HOME", object(), raising=False)
    monkeypatch.setenv("PYWIKIBOT_DIR", str(tmp_path))
    with (
        patch.dict(sys.modules, {"pywikibot": fake_pywikibot}),
        patch(
            "agentic_bot.wiki.load_credentials_from_env",
            return_value=("Example bot@local", "synthetic-password", "https://example.invalid"),
        ),
    ):
        client = WikiClient(base_dir=tmp_path)
        assert client.site is site

    assert not (tmp_path / "user-password.cfg").exists()
    assert not (tmp_path / "user-config.py").exists()
    manager.login_to_site.assert_called_once()
    initial_login.assert_called_once_with(cookie_only=True)


def test_expired_session_never_uses_implicit_login(tmp_path, monkeypatch):
    site = MagicMock()
    site.logged_in.side_effect = [False, True]
    type(site).userinfo = property(lambda _: {"name": "Example bot", "id": 123}, lambda _: None)
    manager = MagicMock()
    fake_pywikibot = SimpleNamespace(
        Site=MagicMock(return_value=site),
        login=SimpleNamespace(ClientLoginManager=MagicMock(return_value=manager)),
    )
    monkeypatch.setattr("agentic_bot.wiki._PYWIKIBOT_HOME", object(), raising=False)
    with (
        patch.dict(sys.modules, {"pywikibot": fake_pywikibot}),
        patch(
            "agentic_bot.wiki.load_credentials_from_env",
            return_value=("Example bot@local", "synthetic-password", "https://example.invalid"),
        ),
    ):
        client = WikiClient(base_dir=tmp_path)
        client._init_pywikibot()
        with pytest.raises(WikiError, match="session expired"):
            client.site.login()

    assert not list(tmp_path.rglob("user-password.cfg"))
    assert not list(tmp_path.rglob("*.lwp"))


def test_login_refreshes_userinfo_before_verifying_identity(tmp_path, monkeypatch):
    class Site:
        def __init__(self):
            self.authenticated = False
            self._userinfo = {"id": 0}

        @property
        def userinfo(self):
            if not hasattr(self, "_userinfo"):
                self._userinfo = {"id": 123, "name": "Example bot"} if self.authenticated else {}
            return self._userinfo

        @userinfo.deleter
        def userinfo(self):
            del self._userinfo

        def logged_in(self):
            return hasattr(self, "_userinfo") and self._userinfo.get("name") == "Example bot"

        def login(self, *, cookie_only):
            assert cookie_only and self.logged_in()

    site = Site()
    manager = MagicMock()
    manager.login_to_site.side_effect = lambda: setattr(site, "authenticated", True)
    fake_pywikibot = SimpleNamespace(
        Site=MagicMock(return_value=site),
        login=SimpleNamespace(ClientLoginManager=MagicMock(return_value=manager)),
    )
    monkeypatch.setattr("agentic_bot.wiki._PYWIKIBOT_HOME", object(), raising=False)
    with (
        patch.dict(sys.modules, {"pywikibot": fake_pywikibot}),
        patch(
            "agentic_bot.wiki.load_credentials_from_env",
            return_value=("Example bot@local", "synthetic-password", "https://example.invalid"),
        ),
    ):
        assert WikiClient(base_dir=tmp_path).site is site


def test_login_rejects_unverified_identity_without_exposing_password(tmp_path, monkeypatch):
    site = MagicMock()
    site.logged_in.return_value = False
    type(site).userinfo = property(lambda _: {"id": 0}, lambda _: None)
    manager = MagicMock()
    fake_pywikibot = SimpleNamespace(
        Site=MagicMock(return_value=site),
        login=SimpleNamespace(ClientLoginManager=MagicMock(return_value=manager)),
    )
    monkeypatch.setattr("agentic_bot.wiki._PYWIKIBOT_HOME", object(), raising=False)
    with (
        patch.dict(sys.modules, {"pywikibot": fake_pywikibot}),
        patch(
            "agentic_bot.wiki.load_credentials_from_env",
            return_value=("Example bot@local", "synthetic-password", "https://example.invalid"),
        ),
    ):
        client = WikiClient(base_dir=tmp_path)
        with pytest.raises(WikiError, match="expected account") as exc:
            client._init_pywikibot()

    assert "synthetic-password" not in str(exc.value)
    assert client._site is None
    assert not list(tmp_path.rglob("user-password.cfg"))


def test_preinitialized_pywikibot_is_rejected(tmp_path, monkeypatch):
    import agentic_bot.wiki as wiki

    monkeypatch.setattr(wiki, "_PYWIKIBOT_HOME", None)
    with patch.dict(sys.modules, {"pywikibot": SimpleNamespace()}):
        with pytest.raises(WikiError, match="initialized outside"):
            wiki._load_pywikibot(tmp_path)

    assert not list(tmp_path.iterdir())


def test_login_does_not_emit_password_in_debug_logs(tmp_path, monkeypatch, caplog):
    site = MagicMock()
    site.logged_in.side_effect = [False, True]
    type(site).userinfo = property(lambda _: {"name": "Example bot", "id": 123}, lambda _: None)
    manager = MagicMock()
    manager.login_to_site.side_effect = lambda: logging.getLogger("pywiki").debug(
        "synthetic-password"
    )

    def create_site(*args, **kwargs):
        logging.getLogger("pywiki").debug("Example bot")
        return site

    fake_pywikibot = SimpleNamespace(
        Site=MagicMock(side_effect=create_site),
        login=SimpleNamespace(ClientLoginManager=MagicMock(return_value=manager)),
    )
    monkeypatch.setattr("agentic_bot.wiki._PYWIKIBOT_HOME", object(), raising=False)
    caplog.set_level(logging.DEBUG, logger="pywiki")
    with (
        patch.dict(sys.modules, {"pywikibot": fake_pywikibot}),
        patch(
            "agentic_bot.wiki.load_credentials_from_env",
            return_value=("Example bot@local", "synthetic-password", "https://example.invalid"),
        ),
    ):
        WikiClient(base_dir=tmp_path)._init_pywikibot()

    assert not any("synthetic-password" in record.getMessage() for record in caplog.records)
    assert not any("Example bot" in record.getMessage() for record in caplog.records)


def test_login_error_does_not_expose_password(tmp_path, monkeypatch):
    site = MagicMock()
    site.logged_in.return_value = False
    manager = MagicMock()
    manager.login_to_site.side_effect = RuntimeError("synthetic-password")
    fake_pywikibot = SimpleNamespace(
        Site=MagicMock(return_value=site),
        login=SimpleNamespace(ClientLoginManager=MagicMock(return_value=manager)),
    )
    monkeypatch.setattr("agentic_bot.wiki._PYWIKIBOT_HOME", object(), raising=False)
    with (
        patch.dict(sys.modules, {"pywikibot": fake_pywikibot}),
        patch(
            "agentic_bot.wiki.load_credentials_from_env",
            return_value=("Example bot@local", "synthetic-password", "https://example.invalid"),
        ),
    ):
        with pytest.raises(WikiError, match="authentication failed") as exc:
            WikiClient(base_dir=tmp_path)._init_pywikibot()

    assert "synthetic-password" not in str(exc.value)
    assert "synthetic-password" not in "".join(traceback.format_exception(exc.value))
    assert not list(tmp_path.rglob("user-password.cfg"))


def test_pywikibot_configuration_is_isolated_from_repository(tmp_path):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
    }
    script = """
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
from agentic_bot.wiki import _load_pywikibot

module = _load_pywikibot(None)
base = Path(module.config.base_dir).resolve()
assert base.is_relative_to(Path(sys.argv[1]).resolve())
assert not module.config.password_file

site = MagicMock()
site.family.ldapDomain = None
site.tokens = {"login": "synthetic-token"}
request = site._request.return_value
request.submit.return_value = {"login": {"result": "Success"}}
manager = module.login.ClientLoginManager(
    site=site, user="Example bot@local", password="synthetic-password"
)
with patch.object(module.comms.http.cookie_jar, "save") as save:
    manager.login_to_site()
    assert site._request.call_args.kwargs["parameters"]["lgname"] == "Example bot@local"
    save.assert_not_called()

from pywikibot.site import APISite
site.logged_in.return_value = True
with patch.object(module.comms.http.cookie_jar, "load") as load:
    APISite.login(site, cookie_only=True)
    load.assert_not_called()

import agentic_bot.wiki as wiki
state = {"logged_in": False}

class FakeRequest:
    def __init__(self, params):
        self.params = params

    def submit(self):
        if self.params.get("action") == "query" and self.params.get("meta") == "userinfo":
            info = {"id": 123, "name": "Example bot"} if state["logged_in"] else {"id": 0, "name": "Anonymous", "anon": ""}
            return {"query": {"userinfo": info}}
        if self.params.get("action") == "login":
            assert self.params["lgname"] == "Example bot@local"
            assert self.params["lgpassword"] == "synthetic-password"
            state["logged_in"] = True
            return {"login": {"result": "Success"}}
        raise AssertionError("Unexpected API request")

def fake_request(site, **kwargs):
    return FakeRequest(kwargs.get("parameters", kwargs))

with (
    patch.object(APISite, "simple_request", fake_request),
    patch.object(APISite, "_request", fake_request),
    patch.object(APISite, "get_tokens", return_value={"login": "synthetic-token"}),
    patch.object(module.comms.http.cookie_jar, "save") as save,
    patch("agentic_bot.wiki.load_credentials_from_env",
          return_value=("Example bot@local", "synthetic-password", "https://example.invalid")),
):
    actual_site = wiki.WikiClient().site
    assert actual_site.logged_in()
    save.assert_not_called()
    try:
        actual_site.login()
    except wiki.WikiError:
        pass
    else:
        raise AssertionError("Implicit login was not blocked")
assert not list(base.rglob("user-password.cfg"))
assert not list(base.rglob("*.lwp"))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.rglob("user-password.cfg"))
    assert not list(tmp_path.rglob("*.lwp"))


def test_permission_checks():
    client = WikiClient(site_lang="be", family="wikipedia")
    client._site = MagicMock()

    # User with only 'bot' and 'read' rights
    client._site.userinfo = {"rights": ["bot", "read"]}

    with pytest.raises(InsufficientPermissionsError) as exc:
        client.check_permissions_for_page("MediaWiki:Gadget-wikificator.js")
    assert "editsitejs" in str(exc.value)

    with pytest.raises(InsufficientPermissionsError) as exc:
        client.check_permissions_for_page("MediaWiki:Gadget-wikificator.css")
    assert "editsitecss" in str(exc.value)

    with pytest.raises(InsufficientPermissionsError) as exc:
        client.check_permissions_for_page("MediaWiki:Common.js")
    assert "editsitejs" in str(exc.value)

    # User with editsitejs and editinterface
    client._site.userinfo = {"rights": ["bot", "editinterface", "editsitejs", "editsitecss"]}
    # Should not raise
    client.check_permissions_for_page("MediaWiki:Gadget-wikificator.js")
    client.check_permissions_for_page("MediaWiki:Gadget-wikificator.css")
    client.check_permissions_for_page("Вікіпедыя:Гаджэты/Вікіфікатар")


def test_edit_conflict_detection():
    client = WikiClient(site_lang="be", family="wikipedia")
    client._site = MagicMock()
    client._site.userinfo = {"rights": ["bot"]}

    mock_page = MagicMock()
    mock_page.exists.return_value = True
    mock_page.latest_revision_id = 200
    mock_page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:00:00Z"

    client._pywikibot = MagicMock()
    client._pywikibot.Page.return_value = mock_page

    # Expected rev is 100, but wiki is at 200 -> conflict
    with pytest.raises(EditConflictDetectedError) as exc:
        client.publish_page(
            title="Some Page",
            text="New text",
            summary="Test",
            expected_revid=100,
        )
    assert "Edit conflict" in str(exc.value)
    # Page.save must NOT have been called
    mock_page.save.assert_not_called()


def test_publish_rejects_unresolved_merge_markers_without_saving():
    client = WikiClient(site_lang="be", family="wikipedia")
    client._site = MagicMock()
    client._site.userinfo = {"rights": ["bot"]}
    page = MagicMock()
    page.exists.return_value = True
    page.latest_revision_id = 100
    page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:00:00Z"
    client._pywikibot = MagicMock()
    client._pywikibot.Page.return_value = page

    with pytest.raises(WikiError, match="conflict markers"):
        client.publish_page(
            title="Some Page",
            text="<<<<<<< proposal\nnew\n=======\nother\n>>>>>>> live\n",
            summary="Test",
            expected_revid=100,
        )

    page.save.assert_not_called()


def test_dry_run_does_not_save():
    client = WikiClient(site_lang="be", family="wikipedia")
    client._site = MagicMock()
    client._site.userinfo = {"rights": ["bot"]}

    mock_page = MagicMock()
    mock_page.exists.return_value = True
    mock_page.latest_revision_id = 100
    mock_page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:00:00Z"

    client._pywikibot = MagicMock()
    client._pywikibot.Page.return_value = mock_page

    revid, ts = client.publish_page(
        title="Some Page",
        text="New text",
        summary="Test",
        expected_revid=100,
        dry_run=True,
    )

    assert revid == 100
    mock_page.save.assert_not_called()


def test_publish_critical_default_no_bot():
    client = WikiClient(site_lang="be", family="wikipedia")
    client._site = MagicMock()
    client._site.userinfo = {"rights": ["bot", "editsitejs", "editinterface"]}

    mock_page = MagicMock()
    mock_page.exists.return_value = True
    mock_page.latest_revision_id = 100
    mock_page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:00:00Z"

    def fake_save(**kwargs):
        mock_page.latest_revision_id = 101
        mock_page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:05:00Z"

    mock_page.save.side_effect = fake_save

    client._pywikibot = MagicMock()
    client._pywikibot.Page.return_value = mock_page

    new_revid, ts = client.publish_page(
        title="MediaWiki:Gadget-wikificator.js",
        text="New text",
        summary="Test summary",
        expected_revid=100,
        dry_run=False,
        mark_as_bot=False,
    )

    assert new_revid == 101
    mock_page.save.assert_called_once_with(
        summary="Test summary",
        baserevid=100,
        bot=False,
    )


def test_publish_with_bot_flag():
    client = WikiClient(site_lang="be", family="wikipedia")
    client._site = MagicMock()
    client._site.userinfo = {"rights": ["bot"]}

    mock_page = MagicMock()
    mock_page.exists.return_value = True
    mock_page.latest_revision_id = 100
    mock_page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:00:00Z"

    def fake_save(**kwargs):
        mock_page.latest_revision_id = 101
        mock_page.latest_revision.timestamp.isoformat.return_value = "2026-02-01T12:05:00Z"

    mock_page.save.side_effect = fake_save

    client._pywikibot = MagicMock()
    client._pywikibot.Page.return_value = mock_page

    new_revid, ts = client.publish_page(
        title="Some Page",
        text="New text",
        summary="Test summary",
        expected_revid=100,
        dry_run=False,
        mark_as_bot=True,
    )

    assert new_revid == 101
    mock_page.save.assert_called_once_with(
        summary="Test summary",
        baserevid=100,
        bot=True,
    )
