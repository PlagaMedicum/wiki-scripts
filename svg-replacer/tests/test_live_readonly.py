"""Opt-in read-only tests against the real Wikimedia APIs.

These never authenticate and never edit. Run with:

    SVG_REPLACER_LIVE=1 uv run --locked pytest tests/test_live_readonly.py
"""

from __future__ import annotations

import os

import pytest
from svg_replacer.api import MediaWikiApi
from svg_replacer.wikitext import (
    assess_usage,
    discover_raster_candidates,
    has_vector_template,
)
from svg_replacer.workflow import filter_usage_rows

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SVG_REPLACER_LIVE") != "1",
        reason="set SVG_REPLACER_LIVE=1 to run read-only Wikimedia API tests",
    ),
]

# Commons SVG page whose source/derivation info links its original raster.
DISCOVERY_SVG = "File:M4A4 cutaway.svg"
DISCOVERY_RASTER = "M4A4 cutaway.png"

# A real converted pair: the raster's Commons page carries
# {{Vector version available|Corona ferrea monza (heraldry).svg}}.
PAIR_SVG = "File:Corona ferrea monza (heraldry).svg"
PAIR_RASTER = "File:Iron Crown.JPG"
PAIR_RASTER_NAME = "Iron Crown.JPG"
PAIR_SVG_NAME = "Corona ferrea monza (heraldry).svg"
SAMPLE_ARTICLE = "Італія"


def test_commons_raster_discovery_live() -> None:
    commons = MediaWikiApi("commons.wikimedia.org")
    files_ns = commons.file_namespaces()

    svg = commons.imageinfo(DISCOVERY_SVG)
    assert not svg.missing, f"{svg.title} should exist on Commons"
    assert svg.mime == "image/svg+xml"

    page = commons.page_revisions([svg.title]).get(svg.title)
    assert page is not None and not page.missing

    candidates = discover_raster_candidates(page.text, files_ns)
    names = [candidate.name for candidate in candidates]
    assert DISCOVERY_RASTER in names, f"expected {DISCOVERY_RASTER} in {names}"

    raster = commons.imageinfo(f"File:{DISCOVERY_RASTER}")
    assert not raster.missing, f"{DISCOVERY_RASTER} should exist on Commons"
    assert raster.description_url


def test_belarusian_wikipedia_usage_pipeline_live() -> None:
    commons = MediaWikiApi("commons.wikimedia.org")
    be = MediaWikiApi("be.wikipedia.org")

    svg = commons.imageinfo(PAIR_SVG)
    raster = commons.imageinfo(PAIR_RASTER)
    assert not svg.missing and not raster.missing
    assert svg.description_url and raster.description_url

    raster_page = commons.page_revisions([raster.title]).get(raster.title)
    assert raster_page is not None and not raster_page.missing
    assert has_vector_template(raster_page.text)
    assert PAIR_SVG_NAME in raster_page.text  # the VVA template names the SVG

    rows = commons.global_usage(raster.title, site=be.site_db_name())
    assert rows, "GlobalUsage should report at least one usage"
    candidates = filter_usage_rows(rows, wiki_host="be.wikipedia.org", namespaces={0})
    assert candidates, "expected namespace-0 usages on be.wikipedia.org"
    assert all(candidate.ns == 0 for candidate in candidates)
    assert all(candidate.url.startswith("https://be.wikipedia.org/") for candidate in candidates)

    be_files = be.file_namespaces()
    for alias in ("File", "Файл", "Image", "Выява"):
        assert be_files.matches(alias), f"be.wiki should accept {alias}"

    sample = be.page_revisions([SAMPLE_ARTICLE]).get(SAMPLE_ARTICLE)
    assert sample is not None and not sample.missing and sample.revid > 0

    assessment = assess_usage(sample.text, PAIR_RASTER_NAME, be_files)
    assert assessment.status in {"replace", "blocked", "indirect"}
