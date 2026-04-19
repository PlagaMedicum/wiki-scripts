---
docmeta:
  status: maintained
  review: client-input-derived
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

## Stable Documentation Model

- `README.md` is the human overview of the repository.
- `.specify/memory/constitution.md` holds the stable governance rules.
- `specs/000-repo-governance/` holds the long-lived repo state.
- `specs/NNN-feature-name/` holds change-specific Spec Kit artifacts.
- Project-local docs should exist only when they help operators or maintainers directly.
- Managed doc metadata comes from `.specify/doc-registry.json`, not from free-form claims in
  Markdown files.
- Review labels in the registry are additive: provenance labels may coexist with terminal review or
  approval labels, and queue state must be derived from the combination.

## Accepted Repo Decisions

### Architecture And Reuse

- Prefer separate packaging and separate runtime control when that improves failure isolation,
  safety, or operator control.
- Python is the default choice for smaller or faster-turnaround wiki automation.
- Rust is preferred for performance-sensitive, reliability-sensitive, or safety-sensitive services.
- Cross-language reuse should default to shared contracts, schemas, process rules, or clear process
  boundaries before embedded shared libraries.

### Workflow

- Non-trivial changes use Spec Kit.
- The required sequence is `spec.md`, then `plan.md`, then `tasks.md`, then implementation, then
  the explicit docs gate.
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
  follow-on actions.
- Current operational targets are:
  - hide latency target under one second when possible
  - recovery target within a few minutes after disconnect or restart, with priority on newer edits
  - stop conditions for missing rights, broken auth, persistent API failure, or malformed
    suppression-list input
- The service should log stop reasons with enough detail for troubleshooting without leaking secrets
  or sensitive payloads.

### Environment Contract

- The preferred BotPasswords login shape is `username@label` in one variable.
- `biblio` and `suppressor` both use that full login form.

## Documentation Rules

- Keep durable repo guidance lean.
- Delete overlapping summaries instead of keeping multiple partial versions of the same story.
- Generated docs are convenience output only and must not invent scope, guarantees, review state,
  or product direction.
- Docs must distinguish current behavior from future direction explicitly.
- Open matters that still need a decision belong in [`research.md`](research.md), not mixed into
  accepted decisions.
- Feature-local unresolved questions and requested comments belong in the active feature directory,
  not only in chat history.
- Feature-local workflow docs should use an explicit local schema instead of pretending they are
  registry-managed docs.
- Git history is the default archive. Finished feature specs should not be kept only for archival
  completeness once their durable lessons have been captured elsewhere.
- If a feature revealed important pitfalls or costly mistakes, preserve that experience in code
  comments, tests, governance docs, or other maintained docs instead of leaving it buried only in
  an old feature spec.
- `.specify/feature.json` is optional. If it exists, it should stop pointing at a finished feature
  before the next non-trivial feature becomes active.
