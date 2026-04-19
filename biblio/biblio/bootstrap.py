from __future__ import annotations

import importlib
import os
import re
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from dotenv import load_dotenv

from biblio.models import SourceSpec
from biblio.observability import format_elapsed
from biblio.transport import report_transport_wait


class BotRightRequiredError(RuntimeError):
    """Raised when the authenticated MediaWiki session cannot mark edits as bot edits."""


@dataclass(frozen=True)
class PywikibotRuntimeConfig:
    min_throttle: float = 0.0
    put_throttle: float = 0.2
    max_retries: int = 3
    retry_wait: int = 1
    retry_max: int = 8
    maxlag: int = 5
    noisysleep: float = 0.0


def normalize_bot_username(username: str) -> str:
    username = re.sub(r"[_ ]+", " ", username).strip()
    return username[:1].upper() + username[1:]


def split_bot_password_login(login: str) -> tuple[str, str]:
    if "@" not in login:
        raise RuntimeError(
            "WIKI_BOT_USERNAME must use the full BotPasswords login in the form "
            "'Username@label'."
        )
    username, suffix = login.split("@", 1)
    if not username.strip() or not suffix.strip():
        raise RuntimeError(
            "WIKI_BOT_USERNAME must use the full BotPasswords login in the form "
            "'Username@label'."
        )
    return normalize_bot_username(username), suffix.strip()


def resolve_dotenv_path(spec: SourceSpec) -> Path:
    return spec.source_dir.parent.parent / ".env"


def bootstrap_pywikibot_from_env(spec: SourceSpec, base_dir: Path) -> str:
    dotenv_path = resolve_dotenv_path(spec)
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
    else:
        load_dotenv()

    login = os.getenv("WIKI_BOT_USERNAME")
    password = os.getenv("WIKI_BOT_PASSWORD")

    missing = [
        name
        for name, value in {
            "WIKI_BOT_USERNAME": login,
            "WIKI_BOT_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        missing_env = ", ".join(missing)
        raise RuntimeError(f"Missing required .env values: {missing_env}")

    normalized_username, suffix = split_bot_password_login(login)
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


def load_pywikibot_runtime_config() -> PywikibotRuntimeConfig:
    return PywikibotRuntimeConfig(
        min_throttle=_env_float("BIBLIO_MIN_THROTTLE", 0.0),
        put_throttle=_env_float("BIBLIO_PUT_THROTTLE", 0.2),
        max_retries=_env_int("BIBLIO_MAX_RETRIES", 3),
        retry_wait=_env_int("BIBLIO_RETRY_WAIT", 1),
        retry_max=_env_int("BIBLIO_RETRY_MAX", 8),
        maxlag=_env_int("BIBLIO_MAXLAG", 5),
        noisysleep=_env_float("BIBLIO_NOISYSLEEP", 0.0),
    )


def import_fresh_pywikibot():
    for name in list(sys.modules):
        if name == "pywikibot" or name.startswith("pywikibot."):
            del sys.modules[name]
    return importlib.import_module("pywikibot")


def apply_pywikibot_runtime_config(pywikibot, config: PywikibotRuntimeConfig) -> None:
    pywikibot.config.minthrottle = config.min_throttle
    pywikibot.config.put_throttle = config.put_throttle
    pywikibot.config.max_retries = config.max_retries
    pywikibot.config.retry_wait = config.retry_wait
    pywikibot.config.retry_max = config.retry_max
    pywikibot.config.maxlag = config.maxlag
    pywikibot.config.noisysleep = config.noisysleep


def patch_pywikibot_request_connection_error_handling() -> None:
    """Make transport resets surface immediately instead of entering Pywikibot's retry loop."""
    requests_exceptions = import_module("requests.exceptions")
    api_requests = import_module("pywikibot.data.api._requests")
    api_requests.ConnectionError = requests_exceptions.ConnectionError


def patch_pywikibot_wait_reporting() -> None:
    pywikibot = import_module("pywikibot")
    api_requests = import_module("pywikibot.data.api._requests")
    throttle_module = import_module("pywikibot.throttle")

    if not getattr(api_requests.Request.wait, "_biblio_patched", False):
        original_request_wait = api_requests.Request.wait

        def request_wait(self, delay: int | None = None) -> None:
            retry_wait = delay or getattr(self, "retry_wait", pywikibot.config.retry_wait)
            next_retry = getattr(self, "current_retries", 0) + 1
            actual_delay = min(retry_wait * (2 ** (next_retry - 1)), pywikibot.config.retry_max)
            action = getattr(self, "action", "request")
            report_transport_wait(
                f"[retry] API {action}: retrying in {format_elapsed(actual_delay)}",
                delay=actual_delay,
            )
            original_request_wait(self, delay)

        request_wait._biblio_patched = True
        api_requests.Request.wait = request_wait

    if not getattr(throttle_module.Throttle.__call__, "_biblio_patched", False):
        original_throttle_call = throttle_module.Throttle.__call__

        def throttle_call(self, *args, **kwargs) -> None:
            write = bool(kwargs.get("write", False))
            delay = self.waittime(write=write)
            report_transport_wait(
                f"[throttle] {'write' if write else 'read'} throttle: waiting {format_elapsed(delay)}",
                delay=delay,
            )
            original_throttle_call(self, *args, **kwargs)

        throttle_call._biblio_patched = True
        throttle_module.Throttle.__call__ = throttle_call

    if not getattr(throttle_module.Throttle.lag, "_biblio_patched", False):
        original_throttle_lag = throttle_module.Throttle.lag

        def throttle_lag(self, lagtime: float | None = None) -> None:
            delay = lagtime or pywikibot.config.retry_wait
            if self.retry_after:
                delay = max(self.retry_after, delay / 5)
            delay = min(delay, pywikibot.config.retry_max)
            report_transport_wait(
                f"[maxlag] API lag backoff: waiting {format_elapsed(delay)}",
                delay=delay,
            )
            original_throttle_lag(self, lagtime)

        throttle_lag._biblio_patched = True
        throttle_module.Throttle.lag = throttle_lag


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
    runtime_config = load_pywikibot_runtime_config()
    pywikibot = import_fresh_pywikibot()
    apply_pywikibot_runtime_config(pywikibot, runtime_config)
    patch_pywikibot_request_connection_error_handling()
    patch_pywikibot_wait_reporting()
    site = pywikibot.Site(spec.site_lang, spec.family, user=username)
    site.login()
    require_bot_right(site, username)
    return pywikibot, site


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return int(raw)
