from __future__ import annotations

from pathlib import Path

import pytest
from biblio.specs import load_source_spec


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PROJECT_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "project"


@pytest.fixture
def repo_root() -> Path:
    return FIXTURE_PROJECT_ROOT


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def gvb_spec(repo_root):
    return load_source_spec("gvb1", root=repo_root)
