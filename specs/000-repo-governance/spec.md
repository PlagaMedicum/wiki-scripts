---
docmeta:
  status: maintained
  review:
  - client-input-derived
  - approved
  purpose: Accepted repo model, scope boundaries, and documentation rules.
  source: .specify/doc-registry.json
---

# Repo Governance


## Purpose

This standing spec records the current accepted repo model, scope boundaries, and documentation
rules. It is the durable human-maintained reference for how this repository is organized today.

Use this file for settled direction. Use [`research.md`](research.md) for unresolved questions and
tradeoffs.

## Repo Model

- This repository is a workspace for separate wiki tools, not one merged application.
- New unrelated work should usually start as a new tool instead of stretching an existing one.
- Shared code is allowed, but shared runtime coupling is not a default goal.
- The repo is not trying to become a generic wiki automation framework today.
- Most of the repo has been built with heavy LLM assistance, so durable lessons need to be fixed in
  code, tests, governance docs, or explicit comments after review.
- Low-spec local operation is a default constraint for operational tools. Resource economy must
  support robustness, performance, and documentation quality, not replace them.

## Stable Documentation Model

- `README.md` is the human overview of the repository.
- `.specify/memory/constitution.md` holds the stable governance rules.
- `specs/000-repo-governance/` holds the long-lived repo state.
- `specs/NNN-feature-name/` holds change-specific Spec Kit artifacts.
- Project-local docs should exist only when they help operators or maintainers directly.
- Managed doc metadata comes from `.specify/doc-registry.json`, not from free-form claims in
  Markdown files.
- Managed review or approval changes become durable only through `.specify/doc-registry.json` plus
  deterministic sync, not through hand-edited Markdown review labels.
- Review labels in the registry are additive: provenance labels may coexist with terminal review or
  approval labels, and queue state must be derived from the combination.
- Repo-level unresolved governance or review follow-up belongs in `research.md`; feature-scoped
  unresolved human input belongs in feature-local `questions.md` or `review-queue.md`.
- Resolved temporary-surface items should be folded into durable docs and cleaned out rather than
  kept as duplicate archives.

## Accepted Repo Decisions

### Architecture And Reuse

- Prefer separate packaging and separate runtime control when that improves failure isolation,
  safety, or operator control.
- Python is the default choice for smaller or faster-turnaround wiki automation.
- Rust is preferred for performance-sensitive, reliability-sensitive, or safety-sensitive services.
- Cross-language reuse should default to shared contracts, schemas, process rules, or clear process
  boundaries before embedded shared libraries.
- Resource-sensitive tools should prefer explicit internal ownership boundaries before adding
  separate long-running processes, public services, or dependencies.
- Queues, concurrency, durable state, polling, and log volume should be bounded when unbounded growth
  could affect correctness, latency, recovery, or operator trust.

### Workflow

- Non-trivial changes use Spec Kit.
- The required sequence is `spec.md`, then `plan.md`, then `tasks.md`, then implementation, then
  the explicit docs gate.
- Changes should default to additive, non-destructive, backward-compatible behavior across configs,
  state files, schemas, operator surfaces, and launch paths.
- Destructive edits, broad rewrites, major refactors that invalidate current setups, incompatible
  schema/config/state/report changes, and any change that can disrupt previous setups require
  explicit human approval before execution.
- When incompatibility is necessary, the active spec, plan, tasks, and affected docs must name the
  impacted surface, compatibility strategy, migration steps, fallback/rollback path, and any
  operator-visible prompt or diagnostic before implementation begins.
- The explicit docs gate is `make docs`, `python3 tools/doc_workflow.py all`, or the repo-local
  Spec Kit command `/speckit.docs`.
- When a feature needs direct human approval, comment, or answer, record that need in feature-local
  docs such as `questions.md` or `review-queue.md` instead of relying only on chat state.
- Spec Kit provides the structure. Codex or other LLM tools may draft and implement inside that
  structure, but they do not define the client vision by themselves.
- Repo policy belongs in the constitution and this governance stack, not spread across many
  overlapping docs.
- For long-running work, keep commits reasonably small and descriptive so the feature history stays
  usable as evidence later.
- Safety-, reliability-, or performance-sensitive specs and plans should include resource goals,
  recovery/status behavior, low-spec verification, and durable lessons captured in tests or docs.
- Resource constraints must not be used to lower performance goals or skip documentation of evidence,
  operational checks, and lessons learned.
- Compatibility and migration checks should be treated as correctness work when machine-readable
  surfaces, stored state, or operator workflows can break across versions.

### Biblio

- `biblio` remains bibliography-first.
- Separation between source-population/import work and source-processing/edit work should start now
  with minimal-cost isolation of logic and entrypoints.
- Broader heuristics belong in dry-run or review-required paths.
- Always require manual review for broad regex rules and uncertain source mapping/import matches.
- Page-wide rewrites may auto-apply only when the match is exact and deterministic.
- Learned replacements should require manual approval on the first proven occurrence before they
  can be promoted to automatic handling.
- `source.toml` is the tracked source definition. Runtime JSON files remain local state.

### Suppressor

- `suppressor` remains intentionally narrow and safety-sensitive.
- Keep one daemon and one local supervisor TUI for now.
- The daemon should process edits made by the same account and hide them too.
- Avoid feedback loops aggressively, especially around any journalling or follow-on actions.
- The preferred next step is to test whether journalling entries can be hidden automatically; if
  that is not possible, evaluate whether they can be safely marked or filtered as bot-originated
  follow-on actions. The next suppressor policy spec should decide whether any hide-and-edit
  fallback must be marked as a bot-originated edit.
- Current operational targets are:
  - hide latency target under one second when possible
  - recovery target within a few minutes after disconnect or restart, with priority on newer edits
  - stop conditions for missing rights, broken auth, persistent API failure, or malformed
    suppression-list input
- The service should log stop reasons with enough detail for troubleshooting without leaking secrets
  or sensitive payloads.
- The service should use internal service boundaries for stream ingestion, source-page refresh,
  reconciliation, suppression execution, status, and persistence while staying a local low-overhead
  daemon unless a process split is justified.
- Suppressor work should treat log storms, unbounded queues, needless polling, and oversized durable
  state as correctness risks because they can delay hiding or hide real operational failures.

### Environment Contract

- The preferred BotPasswords login shape is `username@label` in one variable.
- `biblio` and `suppressor` both use that full login form.

## Documentation Rules

- Keep durable repo guidance lean.
- Delete overlapping summaries instead of keeping multiple partial versions of the same story.
- Generated docs are convenience output only and must not invent scope, guarantees, review state,
  or product direction.
- Docs must distinguish current behavior from future direction explicitly.
- Broad metadata rewrites or feature-generation writes should offer preview or narrowed scope before
  mutation, and must not silently replace filled artifacts or imply that an old setup remains valid
  when it does not.
- Open matters that still need a decision belong in [`research.md`](research.md), not mixed into
  accepted decisions.
- Accepted decisions should be moved out of temporary research or question files once the durable docs
  are updated.
- Maintained standing-governance docs must not keep unresolved inline TODO-style review comments
  once that follow-up has been captured in `research.md` or a scoped feature surface.
- Feature-local unresolved questions and requested comments belong in the active feature directory,
  not only in chat history.
- Feature-local workflow docs should use an explicit local schema instead of pretending they are
  registry-managed docs.
- Git history is the default archive. Finished feature specs should not be kept only for archival
  completeness once their durable lessons have been captured elsewhere.
- If a feature revealed important pitfalls or costly mistakes, preserve that experience in code
  comments, tests, governance docs, or other maintained docs instead of leaving it buried only in
  an old feature spec.
- If a feature changes resource, recovery, or operator-status behavior, update the project-local
  docs and quickstart checks so later maintainers can repeat the evidence.
- Concise docs are preferred, but undocumented operational decisions are not acceptable for
  safety-sensitive tools.
- When a feature or review produces a durable governance lesson, preserve traceability back to the
  originating feature or decision source when that materially helps later audit or git-history
  lookup.
- `.specify/feature.json` is optional. If it exists, it should stop pointing at a finished feature
  before the next non-trivial feature becomes active.
