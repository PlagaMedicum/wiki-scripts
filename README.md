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

Active safety freeze: until the human owner releases it, repo work is restricted to
`specs/001-real-time-suppression/` and the `suppressor/` changes needed to reach a minimal stable
server-runnable MVP. That MVP means automatic live hiding, automatic recovery/reconciliation,
nightly fallback checks, truthful non-healthy status, bounded failure behavior, and verification
through the actual launch path. Unrelated `biblio`, broad docs, workflow polish, new features,
architecture experiments, and cosmetic work wait.

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
Changes that can delete work, invalidate previous setups, break schemas or operator surfaces, or
otherwise disrupt established workflows must be called out explicitly, planned through Spec Kit,
and approved by the human owner before the disruptive step runs.
Config changes are treated as product decisions: changing tracked config files, config schema,
defaults, environment variable names, loading semantics, or deployment-required sections requires a
specific motivation, explicit human review, compatibility or migration evidence, deployment-path
verification, and rollback/fallback notes before the change can support production trust.

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
