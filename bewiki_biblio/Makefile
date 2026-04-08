PYTHON ?= python3
MODULE ?= bewiki_biblio
SOURCE ?=
ARGS ?=

.PHONY: help list validate add-source run test lint format check

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make run [SOURCE="<source_id> [more_source_ids] | --all"] [ARGS="..."]' \
		'  make list [ARGS="--no-color"]' \
		'  make validate [ARGS="--no-color"]' \
		'  make add-source' \
		'  make test [ARGS="-q"]' \
		'  make lint' \
		'  make format' \
		'  make check'

run:
	@if [ -n "$(SOURCE)" ]; then \
		$(PYTHON) -m $(MODULE) run $(SOURCE) $(ARGS); \
	else \
		$(PYTHON) -m $(MODULE) $(ARGS); \
	fi

list:
	$(PYTHON) -m $(MODULE) list $(ARGS)

validate:
	$(PYTHON) -m $(MODULE) validate $(ARGS)

add-source:
	$(PYTHON) -m $(MODULE) add-source $(ARGS)

test:
	$(PYTHON) -m pytest $(ARGS)

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

check:
	$(MAKE) test
	$(MAKE) lint
