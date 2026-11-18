UV ?= uv
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
ARGS ?=

.PHONY: help sync lock run test lint format check

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make sync' \
		'  make lock' \
		'  make run [ARGS="..."]' \
		'  make test [ARGS="..."]' \
		'  make lint' \
		'  make format' \
		'  make check'

sync:
	$(UV) sync --dev --cache-dir $(UV_CACHE_DIR)

lock:
	$(UV) lock --cache-dir $(UV_CACHE_DIR)

run:
	$(UV) run --cache-dir $(UV_CACHE_DIR) agentic-bot $(ARGS)

test:
	$(UV) run --cache-dir $(UV_CACHE_DIR) pytest $(ARGS)

lint:
	$(UV) run --cache-dir $(UV_CACHE_DIR) ruff check .
	$(UV) run --cache-dir $(UV_CACHE_DIR) ruff format --check .

format:
	$(UV) run --cache-dir $(UV_CACHE_DIR) ruff check --fix .
	$(UV) run --cache-dir $(UV_CACHE_DIR) ruff format .

check:
	$(MAKE) sync
	$(MAKE) test
	$(MAKE) lint
