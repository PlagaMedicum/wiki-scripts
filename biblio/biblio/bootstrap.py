from __future__ import annotations

import importlib
import os
import re
import sys
from importlib import import_module
from pathlib import Path

from dotenv import load_dotenv

from biblio.models import SourceSpec


class BotRightRequiredError(RuntimeError):
    """Raised when the authenticated MediaWiki session cannot mark edits as bot edits."""


def normalize_bot_username(username: str) -> str:
    username = re.sub(r"[_ ]+", " ", username).strip()
    return username[:1].upper() + username[1:]


def resolve_dotenv_path(spec: SourceSpec) -> Path:
    return spec.source_dir.parent.parent / ".env"


def bootstrap_pywikibot_from_env(spec: SourceSpec, base_dir: Path) -> str:
    dotenv_path = resolve_dotenv_path(spec)
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
    else:
        load_dotenv()

    username = os.getenv("WIKI_BOT_USERNAME")
    suffix = os.getenv("WIKI_BOT_PASSWORD_SUFFIX")
    password = os.getenv("WIKI_BOT_PASSWORD")

    missing = [
        name
        for name, value in {
            "WIKI_BOT_USERNAME": username,
            "WIKI_BOT_PASSWORD_SUFFIX": suffix,
            "WIKI_BOT_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        missing_env = ", ".join(missing)
        raise RuntimeError(f"Missing required .env values: {missing_env}")

    normalized_username = normalize_bot_username(username)
    base_dir.mkdir(parents=True, exist_ok=True)
    user_config = base_dir / "user-config.py"
    user_password = base_dir / "user-password.cfg"

    user_config.write_text(
        "# -*- coding: utf-8 -*-\n"
        f"family = {spec.family!r}\n"
        f"mylang = {spec.site_lang!r}\n"
        f"usernames[{spec.family!r}][{spec.site_lang!r}] = {normalized_username!r}\n"
        "password_file = 'user-password.cfg'\n",
        encoding="utf-8",
    )
    user_password.write_text(
        f"({spec.site_lang!r}, {spec.family!r}, {normalized_username!r}, "
        f"BotPassword({suffix!r}, {password!r}))\n",
        encoding="utf-8",
    )

    try:
        os.chmod(base_dir, 0o700)
        os.chmod(user_config, 0o600)
        os.chmod(user_password, 0o600)
    except PermissionError:
        pass

    os.environ["PYWIKIBOT_DIR"] = str(base_dir)
    return normalized_username


def import_fresh_pywikibot():
    for name in list(sys.modules):
        if name == "pywikibot" or name.startswith("pywikibot."):
            del sys.modules[name]
    return importlib.import_module("pywikibot")


def patch_pywikibot_request_connection_error_handling() -> None:
    """Make transport resets surface immediately instead of entering Pywikibot's retry loop."""
    requests_exceptions = import_module("requests.exceptions")
    api_requests = import_module("pywikibot.data.api._requests")
    api_requests.ConnectionError = requests_exceptions.ConnectionError


def site_has_bot_right(site) -> bool:
    has_right = getattr(site, "has_right", None)
    if callable(has_right):
        try:
            return bool(has_right("bot"))
        except Exception:
            pass

    userinfo = getattr(site, "userinfo", None)
    if callable(userinfo):
        try:
            userinfo = userinfo()
        except Exception:
            return False
    if isinstance(userinfo, dict):
        rights = userinfo.get("rights", ())
        return any(right == "bot" for right in rights)
    return False


def require_bot_right(site, username: str) -> None:
    if site_has_bot_right(site):
        return
    raise BotRightRequiredError(
        "Authenticated account "
        f"{username!r} lacks the local wiki `bot` right in this API session; biblio saves "
        "request bot=True for every edit. For BotPasswords, grant High-volume (bot) access."
    )


def create_site(spec: SourceSpec, pywikibot_dir: Path):
    username = bootstrap_pywikibot_from_env(spec, pywikibot_dir)
    pywikibot = import_fresh_pywikibot()
    patch_pywikibot_request_connection_error_handling()
    site = pywikibot.Site(spec.site_lang, spec.family, user=username)
    site.login()
    require_bot_right(site, username)
    return pywikibot, site
