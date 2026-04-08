# Architecture Review

This document is intentionally critical. It is not a duplicate of the stable architecture guide in [architecture.md](architecture.md). It records where the project is coherent today, where it is starting to accumulate friction, and what should happen next.

## Summary

The core engine is reasonably coherent. The weak points are at the edges: operator entry points, docs navigation, and modules that are carrying more than one responsibility. This is still maintainable, but only because the project is small enough that the coupling has not yet turned into a real problem.

The current code is not spaghetti. It is, however, a little too close to being a transaction-script style application in the command layer. That is acceptable for now, but it should be treated as a limit, not a target.

## Findings

### High

- The operator surface is split across too many equivalent entry points. The CLI has subcommands, the Makefile has aliases, and the README previously repeated both. That makes the mental model harder than it needs to be.
- `runner.py` owns too much: wiki I/O, run-session state, progress reporting, interactive decisions, candidate learning, and save flow. That is a lot of policy, and it will get brittle as soon as a second substantial run mode appears.

### Medium

- `manage.py` mixes prompt orchestration, scaffold rendering, validation output, and filesystem writes. It is not broken, but it is several responsibilities in one file.
- The documentation previously had no real index. A reader had to discover the right file by guessing whether they needed the README, the architecture guide, or a source README.
- The Makefile was more of a CLI alias collection than a useful operator tool. Extra targets like `run-interactive` and `compile` did not earn their keep.

### Low

- Test discovery originally depended on mutating `sys.path` in `tests/conftest.py`. That is a pragmatic hack, but not a clean project boundary.
- Source README files are useful but were not linked back to the project docs, so they felt isolated instead of navigable.

## Proposals

### Keep the stable core stable

Do not rewrite the engine or the source model just to improve architecture. The current replacement and state logic is structured enough to keep. The right move is to reduce edge friction, not churn the core.

### Make command entry points obvious

Keep the Makefile small and boring:

- `make run` should be the default human entry point and open the wizard when no source is supplied.
- `make list`, `make validate`, and `make add-source` are the only source-management helpers that earn a place there.
- `make test`, `make lint`, `make format`, and `make check` cover the developer loop.

Anything beyond that should live in the CLI, not the Makefile.

### Split orchestration when the next feature arrives

`runner.py` and `manage.py` are both at the point where a new feature should trigger a split. Good future split lines are:

- `runner.py` into run-session orchestration, wiki I/O, and decision logic.
- `manage.py` into scaffold prompting, scaffold rendering, and source validation.
- `specs.py` into path discovery, TOML loading, and validation helpers if source loading grows further.

That is not a refactor to do pre-emptively. It is the next sensible boundary when the code starts growing again.

### Keep docs layered

Use three levels only:

1. [README.md](../README.md) for operator entry and quick commands.
2. [docs/architecture.md](architecture.md) for the stable design.
3. This file for criticism, risks, and proposals.

Per-source README files should stay local and practical, with links back to the project docs.

### Avoid path hacks

Use pytest configuration to keep the package importable during tests instead of manual `sys.path` injection. It is cleaner, less surprising, and easier to reason about when the project boundary moves again.

## Bottom Line

The project is coherent enough to keep growing, but only if the edges stay disciplined. The code is already carrying enough responsibility that new work should prefer extraction and documentation discipline over adding another convenience layer.
