from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from biblio.models import RunOptions, SourceSpec


class PagePromptUI(Protocol):
    def prompt_page_action(self, current_summary: str, *, review_required: bool = False) -> str: ...

    def prompt_summary(self, current_summary: str) -> str: ...


@dataclass(frozen=True)
class PageDecision:
    choice: str
    summary_override: str | None = None

    @property
    def is_accept_all(self) -> bool:
        return self.choice == "a"

    @property
    def is_quit(self) -> bool:
        return self.choice == "q"

    @property
    def is_skip(self) -> bool:
        return self.choice == "n"


@dataclass
class RunPolicy:
    options: RunOptions
    accept_all: bool = False
    bulk_mode_active: bool = False
    summary_override: str | None = None
    stopped: bool = False

    def current_summary(self, spec: SourceSpec) -> str:
        return self.summary_override or self.options.summary or spec.render_default_summary()

    def should_skip_review_required(self, *, review_required: bool) -> bool:
        return review_required and self.options.skip_review_required

    def should_prompt_page(self, *, review_required: bool) -> bool:
        return (not self.accept_all) or review_required

    def is_bulk_mode(self) -> bool:
        return self.options.apply and self.bulk_mode_active

    def apply_page_decision(self, decision: PageDecision) -> None:
        if decision.summary_override is not None:
            self.summary_override = decision.summary_override
        if decision.is_accept_all:
            self.accept_all = True
            self.bulk_mode_active = True
        if decision.is_quit:
            self.stopped = True

    def apply_decision(self, decision: PageDecision) -> None:
        self.apply_page_decision(decision)


def needs_interactive_input(
    options: RunOptions,
    *,
    accept_all: bool,
    has_review_required_rules: bool,
) -> bool:
    return options.learn_variants or (
        options.apply
        and (not accept_all or (has_review_required_rules and not options.skip_review_required))
    )


def prompt_page_decision(
    ui: PagePromptUI,
    current_summary: str,
    *,
    review_required: bool,
) -> PageDecision:
    summary_override: str | None = None
    while True:
        choice = ui.prompt_page_action(current_summary, review_required=review_required)
        if choice != "e":
            return PageDecision(choice=choice, summary_override=summary_override)
        current_summary = ui.prompt_summary(current_summary)
        summary_override = current_summary
