from __future__ import annotations

import importlib
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agentic_bot.models import PageSnapshot


class WikiError(RuntimeError):
    """Base error for MediaWiki operations."""


class EditConflictDetectedError(WikiError):
    """Raised when page has changed on wiki since proposal was prepared."""


class InsufficientPermissionsError(WikiError):
    """Raised when the bot lacks necessary rights to edit a page."""


_PYWIKIBOT_HOME: tempfile.TemporaryDirectory | None = None


def _load_pywikibot(base_dir: Path | None) -> Any:
    global _PYWIKIBOT_HOME
    if _PYWIKIBOT_HOME is None:
        if "pywikibot" in sys.modules:
            raise WikiError("Pywikibot was initialized outside the isolated bot session.")
        home = tempfile.TemporaryDirectory(prefix="agentic-bot-", dir=base_dir)
        (Path(home.name) / "user-config.py").write_text("", encoding="utf-8")
        settings = {"PYWIKIBOT_DIR": home.name, "PYWIKIBOT_NO_USER_CONFIG": "2"}
        previous = {key: os.environ.get(key) for key in settings}
        os.environ.update(settings)
        try:
            pywikibot = importlib.import_module("pywikibot")
            if Path(pywikibot.config.base_dir).resolve() != Path(home.name).resolve():
                raise WikiError("Pywikibot did not use the isolated configuration directory.")
            if getattr(pywikibot.config, "password_file", ""):
                raise WikiError("Isolated Pywikibot unexpectedly configured a password file.")
            pywikibot.config.put_throttle = 0
            pywikibot.config.minthrottle = 0
            pywikibot.config.write_maxlag = 5
        except BaseException:
            home.cleanup()
            raise
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        _PYWIKIBOT_HOME = home
    return importlib.import_module("pywikibot")


def _reject_implicit_login(*args: Any, **kwargs: Any) -> None:
    raise WikiError("Wiki session expired; restart the bot to authenticate again.")


def normalize_bot_username(username: str) -> str:
    username = re.sub(r"[_ ]+", " ", username).strip()
    return username[:1].upper() + username[1:]


def split_bot_password_login(login: str) -> tuple[str, str]:
    if "@" not in login:
        raise WikiError(
            "WIKI_BOT_USERNAME must use the full BotPasswords login in the form 'Username@label'."
        )
    username, suffix = login.split("@", 1)
    if not username.strip() or not suffix.strip():
        raise WikiError(
            "WIKI_BOT_USERNAME must use the full BotPasswords login in the form 'Username@label'."
        )
    return normalize_bot_username(username), suffix.strip()


def load_credentials_from_env(env_path: Path | None = None) -> tuple[str, str, str]:
    """Load credentials from local .env. Returns (username, password, api_url)."""
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent / ".env"

    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    username = os.getenv("WIKI_BOT_USERNAME", "")
    password = os.getenv("WIKI_BOT_PASSWORD", "")
    api_url = os.getenv("WIKI_API_URL", "https://be.wikipedia.org/w/api.php")

    if not username or not password:
        raise WikiError(
            f"Missing WIKI_BOT_USERNAME or WIKI_BOT_PASSWORD in {env_path}. "
            "Please copy .env.example to .env and supply valid bot credentials."
        )

    return username, password, api_url


class WikiClient:
    """Wrapper around pywikibot for safe, auditable Wikipedia operations."""

    def __init__(
        self,
        site_lang: str = "be",
        family: str = "wikipedia",
        env_path: Path | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self.site_lang = site_lang
        self.family = family
        self.env_path = env_path
        self.base_dir = Path(base_dir) if base_dir is not None else None
        self._site: Any = None
        self._pywikibot: Any = None

    def _init_pywikibot(self) -> None:
        if self._site is not None:
            return

        username, password, _ = load_credentials_from_env(self.env_path)
        norm_username, suffix = split_bot_password_login(username)

        pywikibot = _load_pywikibot(self.base_dir)
        logger = logging.getLogger("pywiki")
        previous_level = logger.level
        logger.setLevel(max(logger.getEffectiveLevel(), logging.INFO))
        try:
            site = pywikibot.Site(self.site_lang, self.family, user=norm_username)
            if not site.logged_in():
                manager = pywikibot.login.ClientLoginManager(
                    site=site, user=f"{norm_username}@{suffix}", password=password
                )
                manager.login_to_site()
                del site.userinfo
                _ = site.userinfo
                if not site.logged_in():
                    raise WikiError("Wiki authentication did not establish the expected account.")
                site.login(cookie_only=True)
        except WikiError:
            raise
        except Exception as exc:
            raise WikiError(f"Wiki authentication failed ({type(exc).__name__}).") from None
        finally:
            logger.setLevel(previous_level)
        site.login = _reject_implicit_login
        self._pywikibot = pywikibot
        self._site = site

    @property
    def site(self) -> Any:
        self._init_pywikibot()
        return self._site

    def get_user_rights(self) -> set[str]:
        userinfo = getattr(self.site, "userinfo", {})
        if callable(userinfo):
            userinfo = userinfo()
        return set(userinfo.get("rights", []))

    def check_permissions_for_page(self, title: str) -> None:
        """Verify the authenticated bot account has rights to edit the page."""
        rights = self.get_user_rights()
        is_mediawiki_js = title.startswith("MediaWiki:") and title.endswith(".js")
        is_mediawiki_css = title.startswith("MediaWiki:") and title.endswith(".css")
        is_mediawiki = title.startswith("MediaWiki:")

        if is_mediawiki_js and "editsitejs" not in rights:
            raise InsufficientPermissionsError(
                f"Page '{title}' requires 'editsitejs' right (interface-admin). "
                f"Authenticated rights: {sorted(rights)}"
            )
        if is_mediawiki_css and "editsitecss" not in rights:
            raise InsufficientPermissionsError(
                f"Page '{title}' requires 'editsitecss' right (interface-admin). "
                f"Authenticated rights: {sorted(rights)}"
            )
        if is_mediawiki and "editinterface" not in rights:
            raise InsufficientPermissionsError(
                f"Page '{title}' requires 'editinterface' right. "
                f"Authenticated rights: {sorted(rights)}"
            )

    def fetch_page(self, title: str) -> PageSnapshot:
        """Fetch raw page source and current revision metadata."""
        site = self.site
        page = self._pywikibot.Page(site, title)
        if not page.exists():
            raise WikiError(f"Page '{title}' does not exist on {self.site_lang}.{self.family}.org")

        revid = page.latest_revision_id
        ts = page.latest_revision.timestamp.isoformat()
        content = page.text

        return PageSnapshot(
            title=title,
            revid=revid,
            timestamp=ts,
            content=content,
            wiki=f"{self.site_lang}.{self.family}.org",
            site_lang=self.site_lang,
            family=self.family,
        )

    def check_page_current(self, title: str, expected_revid: int) -> tuple[bool, int, str]:
        """Check if page's current revision matches expected_revid.

        Returns:
            tuple[bool, int, str]: (is_current, latest_revid, latest_timestamp)
        """
        site = self.site
        page = self._pywikibot.Page(site, title)
        if not page.exists():
            raise WikiError(f"Page '{title}' does not exist on {self.site_lang}.{self.family}.org")

        latest_revid = page.latest_revision_id
        latest_ts = page.latest_revision.timestamp.isoformat()
        is_current = latest_revid == expected_revid
        return is_current, latest_revid, latest_ts

    def publish_page(
        self,
        title: str,
        text: str,
        summary: str,
        expected_revid: int,
        dry_run: bool = False,
        mark_as_bot: bool = False,
    ) -> tuple[int, str]:
        """Publish proposed text to Wikipedia after strict conflict and permission checks.

        Returns:
            tuple[int, str]: (new_revid, timestamp)
        """
        if re.search(r"(?m)^(?:<{7}(?:\s|$)|={7}\s*$|>{7}(?:\s|$))", text):
            raise WikiError("Publication blocked: unresolved conflict markers.")

        self.check_permissions_for_page(title)

        is_current, current_revid, current_ts = self.check_page_current(title, expected_revid)
        if not is_current:
            raise EditConflictDetectedError(
                f"Edit conflict: Page '{title}' changed on wiki (base rev: {expected_revid}, "
                f"current rev: {current_revid} at {current_ts}). Publication blocked."
            )

        if dry_run:
            return expected_revid, current_ts

        site = self.site
        page = self._pywikibot.Page(site, title)
        has_bot = "bot" in self.get_user_rights()
        apply_bot_flag = bool(mark_as_bot and has_bot)

        try:
            page.text = text
            page.save(
                summary=summary,
                baserevid=expected_revid,
                bot=apply_bot_flag,
            )
        except self._pywikibot.exceptions.EditConflictError as exc:
            raise EditConflictDetectedError(
                f"MediaWiki API reported an edit conflict on '{title}': {exc}"
            ) from exc
        except Exception as exc:
            raise WikiError(f"Failed to publish edit on '{title}': {exc}") from exc

        new_revid = page.latest_revision_id
        new_ts = page.latest_revision.timestamp.isoformat()
        return new_revid, new_ts
