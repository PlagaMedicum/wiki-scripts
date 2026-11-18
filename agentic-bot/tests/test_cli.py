from __future__ import annotations

from unittest.mock import patch

from agentic_bot.cli import main
from agentic_bot.models import PageSnapshot
from agentic_bot.store import ProposalStore


def test_cli_list_empty(tmp_path):
    with patch("agentic_bot.cli.ProposalStore", return_value=ProposalStore(tmp_path)):
        exit_code = main(["list"])
        assert exit_code == 0


def test_cli_create_and_show(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Edit summary", "Rationale", "Issue 1")

    with patch("agentic_bot.cli.ProposalStore", return_value=store):
        assert main(["list"]) == 0
        assert main(["show", "001"]) == 0
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            assert main(["approve", "001"]) == 0
        assert store.load("001").status == "approved"
        assert main(["decline", "001", "--reason", "Not ready"]) == 0
        assert store.load("001").status == "declined"
        assert main(["reopen", "001"]) == 0
        assert store.load("001").status == "pending"


def test_cli_publish_requires_approval(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Summary", "Rationale", "Issue")

    with patch("agentic_bot.cli.ProposalStore", return_value=store):
        # Publishing a pending proposal should fail
        assert main(["publish", "001"]) == 1


def test_cli_approve_requires_terminal(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Summary", "Rationale", "Issue")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("sys.stdin.isatty", return_value=False),
    ):
        assert main(["approve", "001"]) == 1
    assert store.load("001").status == "pending"


def test_cli_publish_requires_terminal_even_with_force(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Summary", "Rationale", "Issue")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.WikiClient") as wiki,
        patch("sys.stdin.isatty", return_value=False),
    ):
        wiki.return_value.publish_page.return_value = (101, "2026-01-01T00:01:00Z")
        assert main(["publish", "001", "--force"]) == 1
        wiki.assert_not_called()


def test_cli_pending_publish_rejected_even_with_force(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Summary", "Rationale", "Issue")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.WikiClient") as wiki,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("rich.prompt.Confirm.ask", return_value=True) as confirm,
    ):
        wiki.return_value.publish_page.return_value = (101, "2026-01-01T00:01:00Z")
        assert main(["publish", "001", "--force"]) == 1
        confirm.assert_not_called()
        wiki.return_value.publish_page.assert_not_called()
        assert store.load("001").status == "pending"


def test_cli_approved_publish_requires_positive_confirmation(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Summary", "Rationale", "Issue")
    store.set_status("001", "approved")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.WikiClient") as wiki,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("rich.prompt.Confirm.ask", return_value=False) as confirm,
    ):
        wiki.return_value.publish_page.return_value = (101, "2026-01-01T00:01:00Z")
        assert main(["publish", "001"]) == 0
        confirm.assert_called_once()
        wiki.return_value.publish_page.assert_not_called()
        assert store.load("001").status == "approved"


def test_cli_approved_publish_allows_confirmed_human(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    store.create(snap, "New text", "Summary", "Rationale", "Issue")
    store.set_status("001", "approved")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.WikiClient") as wiki,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("rich.prompt.Confirm.ask", return_value=True),
    ):
        wiki.return_value.publish_page.return_value = (101, "2026-01-01T00:01:00Z")
        assert main(["publish", "001"]) == 0
        wiki.return_value.publish_page.assert_called_once()
        assert store.load("001").status == "published"


def test_cli_force_does_not_publish_declined_conflict_or_published(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    proposal = store.create(snap, "New text", "Summary", "Rationale", "Issue")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.WikiClient") as wiki,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("rich.prompt.Confirm.ask", return_value=True),
    ):
        wiki.return_value.publish_page.return_value = (101, "2026-01-01T00:01:00Z")
        for status in ("declined", "conflict", "published"):
            store.set_status(proposal.id, status)
            assert main(["publish", proposal.id, "--force"]) == 1
        wiki.assert_not_called()


def test_cli_default_no_args_launches_dashboard(tmp_path):
    store = ProposalStore(tmp_path)
    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.interactive_dashboard_loop") as mock_loop,
    ):
        assert main([]) == 0
        mock_loop.assert_called_once()


def test_cli_propose_bot_and_critical_flags(tmp_path):
    store = ProposalStore(tmp_path)
    content_file = tmp_path / "content.txt"
    content_file.write_text("New content", encoding="utf-8")

    mock_snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("agentic_bot.cli.WikiClient") as mock_wiki_cls,
    ):
        mock_client = mock_wiki_cls.return_value
        mock_client.fetch_page.return_value = mock_snap

        # Propose with --critical
        exit_code = main(
            [
                "propose",
                "TestPage",
                "--content",
                str(content_file),
                "--summary",
                "Fix",
                "--issue",
                "Bug",
                "--critical",
            ]
        )
        assert exit_code == 0
        p1 = store.load("001")
        assert p1.mark_as_bot is False

        # Propose with --bot
        exit_code = main(
            [
                "propose",
                "TestPage",
                "--content",
                str(content_file),
                "--summary",
                "Fix",
                "--issue",
                "Bug",
                "--bot",
            ]
        )
        assert exit_code == 0
        p2 = store.load("002")
        assert p2.mark_as_bot is True


def test_cli_approve_validation(tmp_path):
    store = ProposalStore(tmp_path)
    snap = PageSnapshot("TestPage", 100, "2026-01-01T00:00:00Z", "Old text")
    p1 = store.create(snap, "clean text", "Summary", "R", "I")
    p2 = store.create(snap, "conflict <<<<<<< text", "Summary", "R", "I")

    with (
        patch("agentic_bot.cli.ProposalStore", return_value=store),
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
    ):
        # Conflict markers rejected
        assert main(["approve", p2.id]) == 1
        assert store.load(p2.id).status == "pending"

        # Clean pending proposal approved
        assert main(["approve", p1.id]) == 0
        assert store.load(p1.id).status == "approved"

        # Already approved is a clean success no-op
        assert main(["approve", p1.id]) == 0

        # Non-pending (e.g. declined or published) cannot be directly approved
        store.set_status(p1.id, "declined")
        assert main(["approve", p1.id]) == 1
        assert store.load(p1.id).status == "declined"
