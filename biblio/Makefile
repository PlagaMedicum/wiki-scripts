UV ?= uv
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
PIP_AUDIT_CACHE_DIR ?= $(CURDIR)/.pip-audit-cache
ARGS ?=

.PHONY: help sync lock list validate add-source run test lint format audit check

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make sync' \
		'  make lock' \
		'  make run [ARGS="..."]' \
		'  make list' \
		'  make validate' \
		'  make add-source' \
		'  make test [ARGS="..."]' \
		'  make lint' \
		'  make format' \
		'  make audit' \
		'  make check'

sync:
	$(UV) sync --dev --cache-dir $(UV_CACHE_DIR)

lock:
	$(UV) lock --cache-dir $(UV_CACHE_DIR)

run:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) biblio $(ARGS)

list:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) biblio list $(ARGS)

validate:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) biblio validate $(ARGS)

add-source:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) biblio add-source $(ARGS)

test:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) pytest $(ARGS)

lint:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) ruff check .
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) ruff format --check .

format:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) ruff check --fix .
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) ruff format .

audit:
	$(UV) run --locked --cache-dir $(UV_CACHE_DIR) \
		pip-audit --cache-dir $(PIP_AUDIT_CACHE_DIR) --skip-editable

check:
	$(MAKE) sync
	$(MAKE) test
	$(MAKE) lint
	$(MAKE) audit
