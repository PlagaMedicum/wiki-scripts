from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class RuntimeJsonError(ValueError):
    pass


def load_json_list(path: Path, *, kind: str) -> list[Any]:
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeJsonError(f"Failed to read {kind} at {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeJsonError(f"Invalid {kind} at {path}: {exc}") from exc

    if not isinstance(data, list):
        raise RuntimeJsonError(
            f"Expected {kind} at {path} to contain a JSON list, got {type(data).__name__}"
        )
    return data


def save_json_list_atomic(path: Path, data: list[Any], *, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)

    try:
        temp_path.replace(path)
    except Exception as exc:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeJsonError(f"Failed to save {kind} at {path}: {exc}") from exc
