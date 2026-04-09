# Architecture Review

This document is intentionally critical. It is not a duplicate of the stable architecture guide in
[architecture.md](architecture.md). It records where the project is coherent today, where it is
starting to accumulate friction, and what should happen next.

## Summary

The core engine is reasonably coherent. The weak points are still at the edges, especially the run
orchestration layer around `workflow.py`, the adjacent `page_analysis.py` helper, the
`page_execution.py` plus `page_save.py` run boundary, and the `session.py` policy layer. The
source-management boundary is much better now that prompting, rendering, writing, and validation
live in separate helpers, and the run boundary is clearer now that `page_analysis.py`,
`page_execution.py`, `page_save.py`, and `session.py` hold the explicit run objects while
`runtime.py` holds the wiki-client pool, `PageEdit` transport, and dependency wrappers.
The project still depends on a lot of implicit conventions.

The current code is not spaghetti. It is, however, still close to a transaction-script style
application in the command layer. That is acceptable for now, but it should remain a limit, not a
target.

## Findings

### High

- The orchestration shell still owns too much policy. `runner.py` is now a thin facade, but
  `workflow.py` still carries source/page coordination, `page_analysis.py` carries candidate and
  review-reason derivation, `page_execution.py` still owns dry-run review learning, `page_save.py`
  now carries apply policy and post-save state mutation, and `session.py` carries prompt handling,
  accept-all state, summary override persistence, and quit/skip decisions. `runtime.py` still owns
  the direct save transport through `PageEdit` and `WikiClient.save_page()`. That is much cleaner
  than before, but it is still the next likely hotspot if a second substantial run mode appears.

### Medium

- The operator workflow still has several equivalent entry points, even though `make run` is now the
  clearly documented default. Keep the Makefile small and resist adding more aliases that compete
  with the CLI.
- The docs are now better layered, but source READMEs still repeat a small amount of navigation and
  project context. That is useful duplication, not a bug, but it should stay minimal.

### Low

- Pytest still uses `pythonpath = ["."]` in `pyproject.toml` to make the package importable during
  tests. That is pragmatic, but it keeps the test environment looser than an installed-package
  boundary.

## Proposals

### Keep the stable core stable

Do not rewrite the engine or the source model just to improve architecture. The current replacement
and state logic is structured enough to keep. The right move is to reduce edge friction, not churn
the core.

### Keep command entry points boring

The documentation should continue to treat `make run` as the human entry point, with the CLI as the
authoritative implementation. `make list`, `make validate`, `make add-source`, `make test`, `make
lint`, `make format`, and `make check` are enough for the normal workflow.

Anything beyond that should live in the CLI, not the Makefile.

### Split orchestration when the next feature arrives

The workflow layer is still the next boundary that should split if new behavior lands there. Good
future split lines are:

- `workflow.py` into run-session orchestration, page analysis, and save-policy helpers
- `page_execution.py` into display and dry-run review helpers if the review-learning path grows
- `page_save.py` into save-plan and post-save state helpers if the save path grows again
- `page_analysis.py` into separate analysis and learning helpers if the candidate logic grows
  further
- `session.py` into prompt handling and post-decision state mutation if the session state machine
  grows again
- `specs.py` into path discovery, TOML loading, and validation helpers if source loading grows
  further
- `startup.py` only if the wizard starts accumulating more run-mode policy

That is not a refactor to do pre-emptively. It is the next sensible boundary when the code starts
growing again.

### Keep docs layered

Use three levels only:

1. [README.md](../README.md) for operator entry and quick commands
2. [docs/architecture.md](architecture.md) for the stable design
3. This file for criticism, risks, and proposals

Per-source README files should stay local and practical, with links back to the project docs.

### Avoid path hacks

Use pytest configuration to keep the package importable during tests instead of manual `sys.path`
injection. It is cleaner, less surprising, and easier to reason about when the project boundary
moves again.

## Bottom Line

The project is coherent enough to keep growing, but only if the edges stay disciplined. The code is
already carrying enough responsibility that new work should prefer extraction and documentation
discipline over adding another convenience layer.
