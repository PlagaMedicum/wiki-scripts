from __future__ import annotations

from pathlib import Path

import pytest
from svg_replacer.creds import Credentials, CredentialsError, default_env_path, load_credentials

SECRET = "s3cret-pass-value"


def write_env(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_credentials_parses_quoted_and_plain_values(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        f'WIKI_BOT_USERNAME=Рэдактар@бот\nWIKI_BOT_PASSWORD="{SECRET}"\n',
    )
    creds = load_credentials(env)
    assert creds == Credentials(username="Рэдактар@бот", password=SECRET)


def test_password_may_contain_equals_and_spaces_when_quoted(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        f"WIKI_BOT_USERNAME=User@label\nWIKI_BOT_PASSWORD='{SECRET}=with=parts'\n",
    )
    creds = load_credentials(env)
    assert creds.password == f"{SECRET}=with=parts"


def test_comments_and_blank_lines_are_ignored(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        f"# local secrets\n\nWIKI_BOT_USERNAME=User@label\nWIKI_BOT_PASSWORD={SECRET}\n",
    )
    assert load_credentials(env).password == SECRET


def test_missing_file_raises_without_content(tmp_path: Path) -> None:
    with pytest.raises(CredentialsError) as excinfo:
        load_credentials(tmp_path / "absent.env")
    assert SECRET not in str(excinfo.value)


def test_missing_variable_raises_naming_key_not_value(tmp_path: Path) -> None:
    env = write_env(tmp_path / ".env", "WIKI_BOT_USERNAME=User@label\n")
    with pytest.raises(CredentialsError) as excinfo:
        load_credentials(env)
    assert "WIKI_BOT_PASSWORD" in str(excinfo.value)


def test_username_must_be_botpassword_login(tmp_path: Path) -> None:
    env = write_env(
        tmp_path / ".env",
        f"WIKI_BOT_USERNAME=PlainUser\nWIKI_BOT_PASSWORD={SECRET}\n",
    )
    with pytest.raises(CredentialsError) as excinfo:
        load_credentials(env)
    assert "@" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)


def test_default_env_path_points_at_biblio_env() -> None:
    path = default_env_path()
    assert path.name == ".env"
    assert path.parent.name == "biblio"
