PYTHON ?= python3
MODULE ?= bewiki_biblio
SOURCE ?=
ARGS ?=

.PHONY: help list validate add-source run test compile lint format check

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make list [ARGS="--no-color"]' \
		'  make validate [ARGS="--no-color"]' \
		'  make add-source' \
		'  make run SOURCE="<source_id> [more_source_ids] | --all" [ARGS="--limit 10 --no-color"]' \
		'  make lint' \
		'  make format' \
		'  make check' \
		'  make test [ARGS="-q"]' \
		'  make compile'

list:
	$(PYTHON) -m $(MODULE) list $(ARGS)

validate:
	$(PYTHON) -m $(MODULE) validate $(ARGS)

add-source:
	$(PYTHON) -m $(MODULE) add-source $(ARGS)

run:
	@if [ -z "$(SOURCE)" ]; then \
		printf 'Usage: make run SOURCE="<source_id> [more_source_ids] | --all" [ARGS="..."]\n' >&2; \
		exit 2; \
	fi
	$(PYTHON) -m $(MODULE) run $(SOURCE) $(ARGS)

test:
	$(PYTHON) -m pytest $(ARGS)

compile:
	$(PYTHON) -m py_compile bewiki_biblio/*.py tests/*.py

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

check:
	$(MAKE) compile
	$(MAKE) test
	$(MAKE) lint
