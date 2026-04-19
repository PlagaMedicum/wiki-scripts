# Wiki Scripts

<!-- DOCMETA:START -->
> Status: maintained
> Review: unreviewed
> Purpose: Human-oriented repo overview and navigation only.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

This repository is a workspace for separate wiki tools, mainly around Belarusian Wikipedia. It is
not one application and not a generic wiki platform.

Most of the repo has been developed with heavy LLM assistance, currently centered on Codex plus a
repo-local Spec Kit workflow. Because of that, the authoritative state is the code, the reviewed
project docs, and the standing governance spec rather than stray generated prose.

## Current Projects

- [`biblio/`](biblio/README.md)
  Python tooling for bibliography and citation cleanup, with source-driven matching and controlled
  edit workflows.
  Main libraries: `pywikibot`, `rich`, `prompt-toolkit`, `python-dotenv`.
- [`suppressor/`](suppressor/README.md)
  Rust tooling for fast public RevDel on watched revisions, kept intentionally narrow and
  safety-sensitive.
  Main libraries: `tokio`, `reqwest`, `reqwest-eventsource`, `ratatui`,
  `metrics-exporter-prometheus`, `serde`.

## Working Style

- keep tools separate instead of letting the repo collapse into one mixed codebase
- keep each tool narrow enough to stay reviewable and operable
- use Spec Kit for non-trivial changes so specs, plans, tasks, and implementation stay connected
- prefer deterministic scripts and explicit human review over free-form doc rewriting
- keep durable repo docs lean, with one owned place for each stable topic

## Where To Look Next

- project usage and scope:
  [`biblio/README.md`](biblio/README.md) and [`suppressor/README.md`](suppressor/README.md)
- repo rules and current accepted direction:
  [`specs/000-repo-governance/spec.md`](specs/000-repo-governance/spec.md) and
  [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- practical repo workflow:
  [`specs/000-repo-governance/quickstart.md`](specs/000-repo-governance/quickstart.md)
- change-specific planning and implementation artifacts:
  [`specs/`](specs/README.md)
