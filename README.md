# Wiki Scripts

This repository is a workspace for separate wiki tools, mainly around Belarusian Wikipedia. It is
not one application and not a generic wiki platform.

Keep the repo small and direct. Prefer project-local docs, Makefiles, tests, and clear code over
generated planning artifacts. Human intent comes first; for non-trivial work, restate the concrete
goal and clarify risky ambiguity before design choices harden.

## Current Projects

- [`biblio/`](biblio/README.md)
  Python tooling for bibliography and citation cleanup, with source-driven matching and controlled
  edit workflows.
  Main libraries: `pywikibot`, `rich`, `prompt-toolkit`, `python-dotenv`.
- [`suppressor/`](suppressor/README.md)
  Rust tooling for fast public RevDel on watched revisions, kept intentionally narrow and
  safety-sensitive, with low-spec local operation treated as a design constraint.
  Main libraries: `tokio`, `reqwest`, `reqwest-eventsource`, `ratatui`,
  `metrics-exporter-prometheus`, `serde`.

## Workflow In Brief

Keep suppressor production behavior stable unless a task explicitly asks for runtime changes.
Cleanup work should first remove unused docs, generated artifacts, and duplicate code around the
current behavior.

Safety-, reliability-, or performance-sensitive changes must keep queues and concurrency bounded,
avoid unnecessary services or dependencies, and verify that simplicity does not come at the cost of
correctness, recovery, or operator-visible status.

Changes that delete work, break schemas, alter config, or disrupt operator surfaces must be called
out explicitly and approved by the human owner before the disruptive step runs.

Because this is a public repo, sensitive-edit incident evidence must stay redacted. Do not commit
real editor names, page titles, revision IDs, diff URLs, comments, screenshots, or log excerpts that
identify how a real person edited a sensitive page; use synthetic fixtures and aggregate outcomes.

## Where To Look Next

- project usage and scope:
  [`biblio/README.md`](biblio/README.md) and [`suppressor/README.md`](suppressor/README.md)
- project commands:
  `biblio/Makefile` and `suppressor/Makefile`
- local agent rules:
  [`AGENTS.md`](AGENTS.md)
