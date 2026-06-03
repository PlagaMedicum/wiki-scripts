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
		'' \
		'Common examples:' \
		'  make suppressor-build' \
		'  make suppressor-build-server' \
		'  make suppressor-run ARGS="..."' \
		'  make suppressor-status ARGS="--json"' \
		'  make biblio-run ARGS="list"' \
		'  make biblio-test'

test: suppressor-test biblio-test

lint: suppressor-lint biblio-lint

check: suppressor-check biblio-check

suppressor-%: FORCE
	$(MAKE) -C suppressor $* ARGS="$(ARGS)"

biblio-%: FORCE
	$(MAKE) -C biblio $* ARGS="$(ARGS)"

FORCE:
