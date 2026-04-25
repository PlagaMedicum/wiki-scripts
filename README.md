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
  safety-sensitive, with low-spec local operation treated as a design constraint.
  Main libraries: `tokio`, `reqwest`, `reqwest-eventsource`, `ratatui`,
  `metrics-exporter-prometheus`, `serde`.

## Workflow In Brief

Non-trivial changes use Spec Kit under `specs/NNN-feature-name/`, with
`.specify/feature.json` used only while a feature is active. Managed human docs get review state from
`.specify/doc-registry.json` plus deterministic sync; feature-local questions and review queues are
temporary work surfaces, not durable policy.

When a feature closes, keep the durable lessons in maintained docs, code comments, tests, or explicit
future-work entries. Finished feature artifacts do not need to stay in the working tree once their
useful lessons are captured; git history is the archive.

Safety-, reliability-, or performance-sensitive changes must state resource goals, keep queues and
concurrency bounded, avoid unnecessary services or dependencies, and verify that economy does not
come at the cost of correctness, performance, recovery, operator-visible status, or durable
documentation.

## Where To Look Next

- project usage and scope:
  [`biblio/README.md`](biblio/README.md) and [`suppressor/README.md`](suppressor/README.md)
- repo rules and current accepted direction:
  [`specs/000-repo-governance/spec.md`](specs/000-repo-governance/spec.md) and
  [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- practical repo workflow:
  [`specs/000-repo-governance/quickstart.md`](specs/000-repo-governance/quickstart.md)
- active review surface, if one exists:
  `.specify/feature.json`, then the referenced feature's `review-queue.md` and `questions.md`
- change-specific planning and implementation artifacts:
  [`specs/`](specs/README.md)
