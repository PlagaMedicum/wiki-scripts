---
docmeta:
  status: maintained
  review: reviewed
  purpose: Human-oriented repo overview and navigation only.
  source: .specify/doc-registry.json
---

# Wiki Scripts


This repository is a workspace for separate wiki tools, mainly around Belarusian Wikipedia. It is
not one application and not a generic wiki platform.

Most of the repo has been developed with heavy LLM assistance, currently centered on Codex plus a
repo-local Spec Kit workflow. That speeds iteration, but it also means mistakes, overclaims, and
workflow drift are still possible. The repo therefore relies on reviewed docs, explicit governance,
and deterministic checks so important assumptions do not stay buried in generated prose or chat.

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

- treat this repo as a multi-project workspace, not one shared application
- start non-trivial changes in `specs/NNN-feature-name/` and keep the active feature pointer honest
- use file-backed review state (`questions.md`, `review-queue.md`, registry-backed frontmatter) instead of relying on chat memory
- keep durable policy in `.specify/memory/constitution.md` and `specs/000-repo-governance/`
- expect LLM output to need verification; reviewed docs, tests, and the explicit docs gate are the control surface

## Where To Look Next

- project usage and scope:
  [`biblio/README.md`](biblio/README.md) and [`suppressor/README.md`](suppressor/README.md)
- repo rules and current accepted direction:
  [`specs/000-repo-governance/spec.md`](specs/000-repo-governance/spec.md) and
  [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- practical repo workflow:
  [`specs/000-repo-governance/quickstart.md`](specs/000-repo-governance/quickstart.md)
- current active review surface:
  [`.specify/feature.json`](.specify/feature.json), then the referenced feature's `review-queue.md`
  and `questions.md` if an active feature exists
- change-specific planning and implementation artifacts:
  [`specs/`](specs/README.md)
