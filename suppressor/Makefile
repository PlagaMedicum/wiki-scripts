MAKEFLAGS += --no-print-directory

CARGO ?= cargo
ZIGBUILD ?= cargo zigbuild
CONFIG ?=
ENV_FILE ?= ./.env
ARGS ?=
REVID ?=
SERVER_TARGET ?= aarch64-unknown-linux-musl
SERVER_BINARY ?= target/$(SERVER_TARGET)/release/suppressor
TOOLFORGE_TARGET ?= x86_64-unknown-linux-musl
TOOLFORGE_BINARY ?= target/$(TOOLFORGE_TARGET)/release/suppressor
LOG_LEVEL ?= warn,suppressor=info,hyper=warn,hyper_util=warn,h2=warn,reqwest=warn
LOG_FORMAT ?= text
TEST_ARGS ?= -- --test-threads=1

RUN_ENV = RUST_LOG=$(LOG_LEVEL) WIKI_LOG_FORMAT=$(LOG_FORMAT) WIKI_ENV_FILE=$(ENV_FILE)

.PHONY: help env-check run dry-run status health last-edits perf check-auth reload-cache catch-up-now hide-revid smoke-test emergency-catchup coverage-report nightly-sweep-now print-effective-config build build-server build-toolforge release test fmt lint audit check

define REQUIRE_CONFIG
	@if [ -f "$(CONFIG)" ]; then :; else \
		printf '[error] config file not found: %s\n' "$(CONFIG)" >&2; \
		printf '        Pass CONFIG=/path/to/a-wiki.toml.\n' >&2; \
		printf '        Start from ./config.example.toml or use CONFIG=/path/to/a-wiki.toml.\n' >&2; \
		exit 1; \
	fi
endef

help:
	@printf '%s\n' \
		'Operator commands:' \
		'  make env-check' \
		'  make run CONFIG=/path/to/a-wiki.toml [ARGS="..."]' \
		'  make dry-run CONFIG=/path/to/a-wiki.toml [ARGS="..."]' \
		'  make status CONFIG=/path/to/a-wiki.toml [ARGS="--json"]' \
		'  make health CONFIG=/path/to/a-wiki.toml [ARGS="--json"]' \
		'  make last-edits CONFIG=/path/to/a-wiki.toml [ARGS="--limit 20"]' \
		'  make perf CONFIG=/path/to/a-wiki.toml [ARGS="--json"]' \
		'  make check-auth CONFIG=/path/to/a-wiki.toml' \
		'  make reload-cache CONFIG=/path/to/a-wiki.toml' \
		'  make catch-up-now CONFIG=/path/to/a-wiki.toml' \
		'  make hide-revid REVID=<revision_id> CONFIG=/path/to/a-wiki.toml [ARGS="..."]' \
		'  make smoke-test CONFIG=/path/to/a-wiki.toml [ARGS="--page User:Bot/Test"]' \
		'  make emergency-catchup CONFIG=/path/to/a-wiki.toml [ARGS="--dry-run"]' \
		'  make coverage-report CONFIG=/path/to/a-wiki.toml [ARGS="--start 2026-04-24T00:00:00Z --report-only"]' \
		'  make nightly-sweep-now CONFIG=/path/to/a-wiki.toml' \
		'  make print-effective-config CONFIG=/path/to/a-wiki.toml' \
		'' \
		'Developer commands:' \
		'  make build' \
		'  make build-server' \
		'  make build-toolforge' \
		'  make release' \
		'  make test [ARGS="..."]' \
		'  make fmt' \
		'  make lint' \
		'  make audit' \
		'  make check' \
		'' \
		'Variables:' \
		'  CONFIG=/path/to/a-wiki.toml (required)' \
		'  ENV_FILE=./.env' \
		'  SERVER_TARGET=aarch64-unknown-linux-musl' \
		'  TOOLFORGE_TARGET=x86_64-unknown-linux-musl' \
		'  LOG_LEVEL=warn,suppressor=info,hyper=warn,hyper_util=warn,h2=warn,reqwest=warn' \
		'  LOG_FORMAT=text' \
		'  TEST_ARGS=-- --test-threads=1'

env-check:
	$(call REQUIRE_CONFIG)
	@printf 'config: %s\n' "$(CONFIG)"
	@printf 'env:    %s (optional)\n' "$(ENV_FILE)"

run:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" run $(ARGS)

dry-run:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" dry-run $(ARGS)

status:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" status $(ARGS)

health:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" health $(ARGS)

last-edits:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" last-edits $(ARGS)

perf:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" perf $(ARGS)

check-auth:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" check-auth $(ARGS)

reload-cache:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" reload-cache $(ARGS)

catch-up-now:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" catch-up-now $(ARGS)

hide-revid:
	@if [ -n "$(REVID)" ]; then :; else \
		printf '[error] missing revision id.\n' >&2; \
		printf '        Usage: make hide-revid REVID=<revision_id> CONFIG=/path/to/a-wiki.toml [ARGS="..."]\n' >&2; \
		exit 2; \
	fi
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" hide-revid "$(REVID)" $(ARGS)

smoke-test:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" smoke-test $(ARGS)

nightly-sweep-now:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" nightly-sweep-now $(ARGS)

emergency-catchup:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" emergency-catchup $(ARGS)

coverage-report:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" coverage-report $(ARGS)

print-effective-config:
	$(call REQUIRE_CONFIG)
	$(RUN_ENV) $(CARGO) run -- --config "$(CONFIG)" print-effective-config $(ARGS)

build:
	$(CARGO) build --workspace $(ARGS)

build-server:
	$(ZIGBUILD) --release --target "$(SERVER_TARGET)" $(ARGS)
	@printf 'server binary: %s\n' "$(SERVER_BINARY)"

build-toolforge:
	$(ZIGBUILD) --release --target "$(TOOLFORGE_TARGET)" $(ARGS)
	@printf 'Toolforge binary: %s\n' "$(TOOLFORGE_BINARY)"

release:
	$(CARGO) build --workspace --release $(ARGS)

test:
	$(CARGO) test --workspace $(ARGS) $(TEST_ARGS)

fmt:
	$(CARGO) fmt $(ARGS)

lint:
	$(CARGO) clippy --workspace --all-targets --all-features -- -D warnings $(ARGS)

audit:
	$(CARGO) deny check $(ARGS)

check:
	$(CARGO) fmt --check
	$(CARGO) clippy --workspace --all-targets --all-features -- -D warnings
	$(CARGO) deny check
	$(CARGO) test --workspace $(TEST_ARGS)
