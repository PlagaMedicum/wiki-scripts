"""AI-assisted latest-revision/editor regressions; entirely offline."""

from unittest.mock import MagicMock, patch

import pytest
from agentic_bot.cli import main
from agentic_bot.models import PageSnapshot
from agentic_bot.review import get_file_suffix_for_page, review_proposal_interactive
from agentic_bot.store import ProposalStore
from agentic_bot.wiki import WikiError
from rich.console import Console


@pytest.mark.parametrize("surface", ["tui", "cli"])
def test_failed_latest_fetch_does_not_open_editor_or_modify_proposal(tmp_path, surface):
    store = ProposalStore(tmp_path)
    proposal = store.create(PageSnapshot("Page", 100, "", "base"), "local", "S", "R", "I")
    wiki = MagicMock()
    wiki.fetch_page.side_effect = WikiError("fixture fetch failed")
    before = store.load(proposal.id)
    with (
        patch("agentic_bot.review.WikiClient", return_value=wiki),
        patch("agentic_bot.cli.WikiClient", return_value=wiki),
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.review.read_key", side_effect=["e", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)) as render,
        patch(
            "agentic_bot.review.edit_text_in_editor", return_value=("local", False)
        ) as tui_editor,
        patch("agentic_bot.cli.edit_text_in_editor", return_value=("local", False)) as cli_editor,
    ):
        if surface == "tui":
            review_proposal_interactive(Console(), proposal, store, wiki)
            assert "fixture fetch failed" in render.call_args.kwargs["notice"]
        else:
            assert main(["edit", proposal.id]) == 1
    tui_editor.assert_not_called()
    cli_editor.assert_not_called()
    assert store.load(proposal.id) == before


@pytest.mark.parametrize(
    "live_content,conflicted", [("a\nb\nc live\n", False), ("a local2\nb\nc\n", True)]
)
def test_editor_receives_latest_three_way_merge_and_resets_approval(
    tmp_path, live_content, conflicted
):
    store = ProposalStore(tmp_path)
    proposal = store.create(
        PageSnapshot("Page", 100, "", "a\nb\nc\n"), "a local\nb\nc\n", "S", "R", "I"
    )
    proposal = store.set_status(proposal.id, "approved")
    wiki = MagicMock()
    live = PageSnapshot("Page", 101, "", live_content)
    wiki.fetch_page.return_value = live

    def editor(text, suffix):
        assert suffix == ".wiki"
        assert "a local" in text
        assert ("<<<<<<<" in text) == conflicted
        if not conflicted:
            assert "c live" in text
        return text, False

    with (
        patch("agentic_bot.review.read_key", side_effect=["e", "b"]),
        patch("agentic_bot.review.render_proposal_view", return_value=(0, 0, 10)),
        patch("agentic_bot.review.edit_text_in_editor", side_effect=editor),
    ):
        review_proposal_interactive(Console(), proposal, store, wiki)
    current = store.load(proposal.id)
    assert current.page == live
    assert current.status == "pending"
    assert ("<<<<<<<" in current.proposed_content) == conflicted
    assert current.decisions[-1].action == ("rebase_with_conflicts" if conflicted else "rebase")
    assert current.current_version == 2


def test_article_tempfiles_select_native_mediawiki_syntax():
    assert get_file_suffix_for_page("Article") == ".wiki"
    assert get_file_suffix_for_page("User:Example/common.js") == ".js"
    assert get_file_suffix_for_page("MediaWiki:Common.css") == ".css"
