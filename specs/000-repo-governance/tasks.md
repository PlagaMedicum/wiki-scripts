---
docmeta:
  status: maintained
  review: reviewed
  purpose: Lean future-work backlog for repo workflow and tool-boundary follow-up.
  source: .specify/doc-registry.json
---

# Future Work


## Repo Workflow

- Keep the docs gate, registry-backed frontmatter sync, scoped metadata preview, and no-silent-plan
  overwrite guardrails stable as the baseline workflow.
- Keep the intent-first and KISS gates active in templates and reviews so future features do not
  drift into broad systems, speculative abstractions, or secondary polish before the accepted user
  goal works.
- When a feature closes, lift durable lessons into maintained docs, code comments, tests, or explicit
  future-work entries, then remove the finished feature directory and rely on git history for the
  detailed archive.
- Keep repo-local Spec Kit template overrides conservative and close to upstream defaults unless the
  user explicitly asks for a reviewed deviation.
- Treat the repo-local docs extension and workflow hardening as a candidate reusable basis only after
  it stays stable through the next feature cycle.
- Keep resource-economy gates current in the Spec Kit templates so new performance-, reliability-,
  or safety-sensitive features cannot skip bounded design and low-spec verification.

## Suppressor

- Start `002-suppressor-journalling-policy` to decide whether journalling entries can be hidden
  automatically and, if not, define the safest bot-marking or filtering fallback that still avoids
  loops.
- Start `003-suppressor-operator-contract` to encode the operational targets, stop conditions, and
  any separate operator-visible status surface in implementation-facing docs and tests.
- Fold the real-time suppression incident lessons into tests, docs, and quickstart benchmarks:
  immediate source-list refresh, bounded warning output, robust API error classification, and
  low-spec queue/backlog behavior.
- Investigate the observed default-parallel suppressor suite failure around redirect-target
  fetching; isolated and single-threaded runs pass, so publication should not overclaim full-suite
  stability.

## Biblio

- Start `004-biblio-boundary-cut` to turn the current code-level import/population versus
  processing/edit boundary into a scoped implementation spec with explicit entrypoint and ownership
  lines.
- Start `005-biblio-proof-rule` to turn the proposed “100% match” proof rule and the approved
  manual-review rules into implementation-facing checks and tests.
