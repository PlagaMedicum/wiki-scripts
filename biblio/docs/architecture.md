# Biblio Architecture

_AI-assisted documentation._

Biblio is one Python package and CLI, with source management separate from page
processing. It is not a split service architecture.

## Ownership Map

| Area | Modules |
| --- | --- |
| Source rules and models | `models.py`, `source_templates.py`, `specs.py`, `text.py`, `engine.py` |
| Page-processing workflow | `query.py`, `page_analysis.py`, `page_execution.py`, `page_save.py`, `session.py`, `workflow.py` |
| Source-management controllers | `manage.py`, `manage_*.py` |
| Entry points and run controllers | `cli.py`, `startup.py`, `runner.py` |
| Wiki, state, and presentation adapters | `bootstrap.py`, `runtime.py`, `runtime_json.py`, `state.py`, `transport.py`, `ui.py`, `observability.py` |

## Enforced Boundaries

The executable module lists live in [`.importlinter`](../.importlinter):

- backend modules cannot import UI or controllers;
- source-management controllers cannot import run workflow or page execution.

Run `make lint` from `biblio/` to check these contracts alongside Ruff.
This map describes ownership; the import contracts, not this table, define the
exact forbidden dependency edges.

## Related Owners

- [README](../README.md): usage, source/state contract, authentication, and scope.
- [Testing strategy](testing-strategy.md): checks and verification limits.
- [Repository plan](../../docs/plan.md): pending work, not current architecture.
