from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class CredentialsError(RuntimeError):
    """Raised when bot credentials cannot be loaded from the local environment file."""


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


def default_env_path() -> Path:
    """The repository keeps the bot password for all wiki-scripts projects in biblio/.env."""
    return Path(__file__).resolve().parents[2] / "biblio" / ".env"


def load_credentials(path: Path) -> Credentials:
    if not path.is_file():
        raise CredentialsError(f"credential file not found: {path}")

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value

    missing = [key for key in ("WIKI_BOT_USERNAME", "WIKI_BOT_PASSWORD") if not values.get(key)]
    if missing:
        raise CredentialsError(f"missing {' and '.join(missing)} in {path}")

    username = values["WIKI_BOT_USERNAME"]
    if "@" not in username:
        raise CredentialsError(
            "WIKI_BOT_USERNAME must be a BotPasswords login in the form 'Username@label'"
        )
    return Credentials(username=username, password=values["WIKI_BOT_PASSWORD"])
