MAKEFLAGS += --no-print-directory

ARGS ?=

# Root Makefile guardrails:
# - Keep this file as a thin repo orchestrator; project behavior lives in each project.
# - Delegate to project-local Makefiles instead of duplicating CLI options here.
# - Pass one-off command options with ARGS="..." or normal make variables.
# - Add root targets only for repeated repo-wide workflows.
# - Move multi-step scripts into scripts/ before wiring them here.

.PHONY: help test lint check FORCE

help:
	@printf '%s\n' \
		'Repo commands:' \
		'  make test' \
		'  make lint' \
		'  make check' \
		'' \
		'Project commands:' \
		'  make suppressor-<target> [ARGS="..."]' \
		'  make biblio-<target> [ARGS="..."]' \
		'  make agentic-bot-<target> [ARGS="..."]' \
		'  make svg-replacer-<target> [ARGS="..."]' \
		'' \
		'Common examples:' \
		'  make suppressor-build' \
		'  make suppressor-build-server' \
		'  make suppressor-run CONFIG=/path/to/wiki.toml [ARGS="..."]' \
		'  make suppressor-status CONFIG=/path/to/wiki.toml ARGS="--json"' \
		'  make biblio-run ARGS="list"' \
		'  make agentic-bot-test' \
		'  make biblio-test' \
		'  make svg-replacer-run'

test: suppressor-test biblio-test agentic-bot-test svg-replacer-test

lint: suppressor-lint biblio-lint agentic-bot-lint svg-replacer-lint

check: suppressor-check biblio-check agentic-bot-check svg-replacer-check

suppressor-%: FORCE
	$(MAKE) -C suppressor $* ARGS="$(ARGS)"

biblio-%: FORCE
	$(MAKE) -C biblio $* ARGS="$(ARGS)"

agentic-bot: FORCE
	$(MAKE) -C agentic-bot run ARGS="$(ARGS)"

agentic-bot-%: FORCE
	$(MAKE) -C agentic-bot $* ARGS="$(ARGS)"

svg-replacer-%: FORCE
	$(MAKE) -C svg-replacer $* ARGS="$(ARGS)"

FORCE:
