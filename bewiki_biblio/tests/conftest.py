from __future__ import annotations

from pathlib import Path

import pytest
from bewiki_biblio.specs import load_source_spec


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def gvb_spec(repo_root):
    return load_source_spec("gvb1", root=repo_root)
