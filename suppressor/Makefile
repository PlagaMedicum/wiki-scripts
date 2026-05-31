MAKEFLAGS += --no-print-directory

CARGO ?= cargo
ZIGBUILD ?= cargo zigbuild
CONFIG ?= ./config.toml
ENV_FILE ?= ./.env
ARGS ?=
REVID ?=
SERVER_TARGET ?= aarch64-unknown-linux-musl
SERVER_BINARY ?= target/$(SERVER_TARGET)/release/suppressor
LOG_LEVEL ?= warn,suppressor=info,hyper=warn,hyper_util=warn,h2=warn,reqwest=warn
LOG_FORMAT ?= text
TEST_ARGS ?= -- --test-threads=1

RUN_ENV = RUST_LOG=$(LOG_LEVEL) BEWIKI_LOG_FORMAT=$(LOG_FORMAT) BEWIKI_ENV_FILE=$(ENV_FILE)

.PHONY: help env-check run dry-run tui check-auth reload-cache hide-revid smoke-test emergency-catchup coverage-report nightly-sweep-now print-effective-config build build-server release test fmt lint check

define REQUIRE_CONFIG
	@if [ -f "$(CONFIG)" ]; then :; else \
		printf '[error] config file not found: %s\n' "$(CONFIG)" >&2; \
		printf '        Pass CONFIG=/path/to/config.toml or run from suppressor/.\n' >&2; \
		printf '        The tracked example is ./config.toml.\n' >&2; \
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
		'Operator commands:' \
		'  make env-check' \
		'  make run [CONFIG=./config.toml] [ARGS="..."]' \
		'  make dry-run [CONFIG=./config.toml] [ARGS="..."]' \
		'  make tui [CONFIG=./config.toml] [ARGS="..."]' \
		'  make check-auth [CONFIG=./config.toml]' \
		'  make reload-cache [CONFIG=./config.toml]' \
		'  make hide-revid REVID=<revision_id> [CONFIG=./config.toml] [ARGS="..."]' \
		'  make smoke-test [CONFIG=./config.toml] [ARGS="--page User:Bot/Test"]' \
		'  make emergency-catchup [CONFIG=./config.toml] [ARGS="--dry-run"]' \
		'  make coverage-report [CONFIG=./config.toml] [ARGS="--start 2026-04-24T00:00:00Z --report-only"]' \
		'  make nightly-sweep-now [CONFIG=./config.toml]' \
		'  make print-effective-config [CONFIG=./config.toml]' \
		'' \
		'Developer commands:' \
		'  make build' \
		'  make build-server' \
		'  make release' \
		'  make test [ARGS="..."]' \
		'  make fmt' \
		'  make lint' \
		'  make check' \
		'' \
		'Variables:' \
		'  CONFIG=./config.toml' \
		'  ENV_FILE=./.env' \
		'  SERVER_TARGET=aarch64-unknown-linux-musl' \
		'  LOG_LEVEL=warn,suppressor=info,hyper=warn,hyper_util=warn,h2=warn,reqwest=warn' \
		'  LOG_FORMAT=text' \
		'  TEST_ARGS=-- --test-threads=1'

env-check:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	@printf 'config: %s\n' "$(CONFIG)"
	@printf 'env:    %s\n' "$(ENV_FILE)"

run:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" run $(ARGS)

dry-run:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" dry-run $(ARGS)

tui:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" tui $(ARGS)

check-auth:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" check-auth $(ARGS)

reload-cache:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" reload-cache $(ARGS)

hide-revid:
	@if [ -n "$(REVID)" ]; then :; else \
		printf '[error] missing revision id.\n' >&2; \
		printf '        Usage: make hide-revid REVID=<revision_id> [CONFIG=./config.toml] [ARGS="..."]\n' >&2; \
		exit 2; \
	fi
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" hide-revid "$(REVID)" $(ARGS)

smoke-test:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" smoke-test $(ARGS)

nightly-sweep-now:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" nightly-sweep-now $(ARGS)

emergency-catchup:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" emergency-catchup $(ARGS)

coverage-report:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" coverage-report $(ARGS)

print-effective-config:
	$(call REQUIRE_CONFIG)
	$(call REQUIRE_ENV)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" print-effective-config $(ARGS)

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
