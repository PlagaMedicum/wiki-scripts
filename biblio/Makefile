PYTHON ?= python3
ARGS ?=

.PHONY: help list validate add-source run test lint format check

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make run [ARGS="..."]' \
		'  make list' \
		'  make validate' \
		'  make add-source' \
		'  make test [ARGS="..."]' \
		'  make lint' \
		'  make format' \
		'  make check'

run:
	$(PYTHON) -m biblio $(ARGS)

list:
	$(PYTHON) -m biblio list $(ARGS)

validate:
	$(PYTHON) -m biblio validate $(ARGS)

add-source:
	$(PYTHON) -m biblio add-source $(ARGS)

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
