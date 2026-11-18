from __future__ import annotations

from biblio.models import RunOptions
from biblio.startup import _render_command_preview


def test_render_command_preview_uses_public_biblio_command():
    options = RunOptions(
        source_ids=("gvb1",),
        query=None,
        limit=10,
        minor_threshold=1000,
        apply=False,
        assume_yes=False,
        skip_review_required=False,
        summary=None,
        context=3,
        learn_variants=False,
        show_candidates=False,
    )

    assert _render_command_preview(options) == "biblio run gvb1"
