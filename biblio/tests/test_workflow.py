from __future__ import annotations

from biblio.bootstrap import create_site
from biblio.workflow import _build_dependencies


def test_build_dependencies_exposes_live_bootstrap_create_site():
    deps = _build_dependencies()

    assert deps.create_site is create_site
