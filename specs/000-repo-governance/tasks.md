---
docmeta:
  status: maintained
  review: reviewed
  purpose: Lean future-work backlog for repo workflow and tool-boundary follow-up.
  source: .specify/doc-registry.json
---

# Future Work


## Repo Workflow

- Complete `001-docs-governance-hardening` to add file-backed question queues, stricter docs status
  visibility, and `.specify` guardrails for LLM-assisted work.
- Keep repo-local Spec Kit template overrides conservative and close to upstream defaults unless the
  user explicitly asks for a reviewed deviation.
- Treat the repo-local docs extension and workflow hardening as a candidate reusable basis only after
  `001-docs-governance-hardening` proves stable.

## Suppressor

- Start `002-suppressor-journalling-policy` to decide whether journalling entries can be hidden
  automatically and, if not, define the safest bot-marking or filtering fallback that still avoids
  loops.
- Start `003-suppressor-operator-contract` to encode the operational targets, stop conditions, and
  any separate operator-visible status surface in implementation-facing docs and tests.
- Investigate the observed default-parallel suppressor suite failure around redirect-target
  fetching; isolated and single-threaded runs pass, so publication should not overclaim full-suite
  stability.

## Biblio

- Start `004-biblio-boundary-cut` to turn the current code-level import/population versus
  processing/edit boundary into a scoped implementation spec with explicit entrypoint and ownership
  lines.
- Start `005-biblio-proof-rule` to turn the proposed “100% match” proof rule and the approved
  manual-review rules into implementation-facing checks and tests.
