from __future__ import annotations

import io

from svg_replacer.ui import Decider, colorize, confirm
from svg_replacer.workflow import Proposal


def make_proposal() -> Proposal:
    return Proposal(
        kind="page",
        title="Артыкул",
        url="https://be.wikipedia.org/wiki/Артыкул",
        context=["12: Радок з [[Файл:Foo.png|рамка]]"],
        diff="-[[Файл:Foo.png|рамка]]\n+[[Файл:Foo.svg|рамка]]\n",
        edit_summary="Replaces File:Foo.png with File:Foo.svg",
        raster="Foo.png",
        svg="Foo.svg",
    )


def scripted_input(*answers: str):
    queue = iter(answers)

    def read(prompt: str) -> str:
        return next(queue)

    return read


def test_decider_reprompts_on_invalid_choice_then_approves() -> None:
    out = io.StringIO()
    decider = Decider(input_fn=scripted_input("maybe", "approve"), out=out)

    assert decider(make_proposal()) == "approve"


def test_decider_maps_short_and_long_tokens() -> None:
    for token, expected in (
        ("s", "skip"),
        ("quit", "stop"),
        ("a", "approve"),
        ("skip", "skip"),
        ("stop", "stop"),
    ):
        decider = Decider(input_fn=scripted_input(token), out=io.StringIO())
        assert decider(make_proposal()) == expected


def test_decider_shows_target_and_exact_diff_before_prompt() -> None:
    out = io.StringIO()
    decider = Decider(input_fn=scripted_input("s"), out=out)
    decider(make_proposal())
    shown = out.getvalue()

    assert "Артыкул" in shown
    assert "https://be.wikipedia.org/wiki/Артыкул" in shown
    assert "-[[Файл:Foo.png|рамка]]" in shown
    assert "+[[Файл:Foo.svg|рамка]]" in shown
    assert "Foo.png" in shown and "Foo.svg" in shown


def test_confirm_defaults_to_no_on_empty_or_rejected_answer() -> None:
    assert confirm("Proceed?", input_fn=scripted_input("")) is False
    assert confirm("Proceed?", input_fn=scripted_input("n")) is False
    assert confirm("Proceed?", input_fn=scripted_input("y")) is True
    assert confirm("Proceed?", input_fn=scripted_input("yes")) is True


def test_colorize_only_emits_escape_codes_when_enabled() -> None:
    assert "\x1b[" in colorize("x", "31", enabled=True)
    assert "\x1b[" not in colorize("x", "31", enabled=False)


def test_enter_approves():
    decider = Decider(input_fn=scripted_input(""), out=io.StringIO())
    assert decider(make_proposal()) == "approve"


def test_preview_prompt_cannot_be_mistaken_for_publishing():
    out = io.StringIO()
    Decider(input_fn=scripted_input(""), out=out)(make_proposal())
    shown = out.getvalue().lower()
    assert "enter" in shown
    assert "preview (not saved)" in shown


def test_publish_prompt_names_the_write_action():
    out = io.StringIO()
    Decider(input_fn=scripted_input("s"), out=out, apply=True)(make_proposal())
    shown = out.getvalue().lower()
    assert "enter" in shown
    assert "publish" in shown


def test_terminal_colour_does_not_restore_untrusted_controls(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    out = Terminal()
    proposal = make_proposal()
    proposal.title = "Title\x1b[2J"
    Decider(input_fn=scripted_input("s"), out=out)(proposal)
    assert "\x1b[36m" in out.getvalue()
    assert "\x1b[2J" not in out.getvalue()
