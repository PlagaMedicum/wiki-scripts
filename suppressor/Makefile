MAKEFLAGS += --no-print-directory

CARGO ?= cargo
ZIGBUILD ?= cargo zigbuild
CONFIG ?= ./config.toml
ENV_FILE ?= ./.env
ARGS ?=
SERVER_TARGET ?= aarch64-unknown-linux-musl
SERVER_BINARY ?= target/$(SERVER_TARGET)/release/suppressor
LOG_LEVEL ?= warn,suppressor=info,hyper=warn,hyper_util=warn,h2=warn,reqwest=warn
LOG_FORMAT ?= text
TEST_ARGS ?= -- --test-threads=1

RUN_ENV = RUST_LOG=$(LOG_LEVEL) BEWIKI_LOG_FORMAT=$(LOG_FORMAT) BEWIKI_ENV_FILE=$(ENV_FILE)

# Make is a small command router, not a second CLI schema.
# Pass suppressor flags and positionals through ARGS, for example:
#   make status ARGS="--json"
#   make hide-revid ARGS="12345"
# Repeated multi-step shell workflows belong in scripts/ and may be called from Make.

ENV_COMMANDS := run dry-run last-edits check-auth hide-revid smoke-test emergency-catchup coverage-report coverage-last-24h print-effective-config server-start
NO_ENV_COMMANDS := status health perf reload-cache catch-up-now nightly-sweep-now

.PHONY: help env-check $(ENV_COMMANDS) $(NO_ENV_COMMANDS) build build-server release test fmt lint check

define REQUIRE_CONFIG
	@if [ -f "$(CONFIG)" ]; then :; else \
		printf '[error] config file not found: %s\n' "$(CONFIG)" >&2; \
		printf '        Pass CONFIG=/path/to/config.toml or run from suppressor/.\n' >&2; \
		exit 1; \
	fi
endef

define REQUIRE_ENV
	@if [ -f "$(ENV_FILE)" ]; then :; else \
		printf '[error] env file not found: %s\n' "$(ENV_FILE)" >&2; \
		printf '        Create it from ./.env.example or pass ENV_FILE=/path/to/.env.\n' >&2; \
		exit 1; \
	fi
endef

help:
	@printf '%s\n' \
		'Usage:' \
		'  make <command> [CONFIG=./config.toml] [ARGS="..."]' \
		'' \
		'Operator commands:' \
		'  env-check' \
		'  run dry-run server-start' \
		'  status health last-edits perf' \
		'  check-auth reload-cache catch-up-now nightly-sweep-now' \
		'  hide-revid smoke-test emergency-catchup coverage-report coverage-last-24h' \
		'  print-effective-config' \
		'' \
		'Developer commands:' \
		'  build build-server release test fmt lint check' \
		'' \
		'Examples:' \
		'  make status ARGS="--json"' \
		'  make hide-revid ARGS="12345"' \
		'  make coverage-report ARGS="--start 2026-04-24T00:00:00Z --report-only"'

env-check:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	@printf 'config: %s\n' "$(CONFIG)"
	@printf 'env:    %s\n' "$(ENV_FILE)"

$(ENV_COMMANDS):
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" $@ $(ARGS)

$(NO_ENV_COMMANDS):
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" $@ $(ARGS)

build:
	$(CARGO) build $(ARGS)

build-server:
	$(ZIGBUILD) --release --target "$(SERVER_TARGET)" $(ARGS)
	@printf 'server binary: %s\n' "$(SERVER_BINARY)"

release:
	$(CARGO) build --release $(ARGS)

test:
	$(CARGO) test $(ARGS) $(TEST_ARGS)

fmt:
	$(CARGO) fmt $(ARGS)

lint:
	$(CARGO) clippy --all-targets --all-features -- -D warnings $(ARGS)

check:
	$(CARGO) fmt --check
	$(CARGO) clippy --all-targets --all-features -- -D warnings
	$(CARGO) test $(TEST_ARGS)
