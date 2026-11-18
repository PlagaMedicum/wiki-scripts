# Biblio Verification

_AI-assisted documentation._

Run from `biblio/`:

```bash
make test ARGS="tests/test_page_save.py -q"
make lint
make check
```

The first command is an example focused test; select the module owning the change.
[`Makefile`](../Makefile) owns command details: `lint` runs Ruff and import
contracts; `check` synchronizes development dependencies, runs tests, lint, and
the dependency audit. Use an already prepared environment when installation or
network access is not authorized; do not describe a partial check as the full gate.

## Test Ownership

Tests live in `tests/test_<area>.py`, alongside shared fixtures in `tests/fixtures/`:

| Contract | Test modules |
| --- | --- |
| Source parsing and replacement | `test_specs.py`, `test_text.py`, `test_engine.py` |
| Runtime and persistence | `test_bootstrap.py`, `test_runtime.py`, `test_state.py` |
| Page processing and save decisions | `test_page_analysis.py`, `test_page_execution.py`, `test_page_save.py` |
| Run orchestration | `test_session.py`, `test_workflow.py`, `test_runner.py` |
| CLI and source management | `test_cli.py`, `test_startup.py`, `test_source_commands.py`, `test_manage_import.py`, `test_manage_tui.py` |

## Limits

Passing local tests does not prove live-wiki behavior, the full interactive TUI,
or performance on large source sets. Changes to prompts, approvals, cancellation,
or rendering need observation of the actual terminal interaction as well as
relevant deterministic tests.

Source/state contracts and edit-review rules live in the [README](../README.md);
dependency boundaries live in [architecture.md](architecture.md) and
[`.importlinter`](../.importlinter).
