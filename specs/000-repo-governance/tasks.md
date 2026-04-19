# Future Work

<!-- DOCMETA:START -->
> Status: maintained
> Review: unreviewed
> Purpose: Lean future-work backlog for repo workflow and tool-boundary follow-up.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

## Repo Workflow

- Add commit-granularity guidance for long-running features so Spec Kit work does not sit in one
  giant uncommitted batch.
- Review whether the local Spec Kit template overrides should be reset during a later controlled
  `specify init` refresh.
- Decide whether the repo-local docs extension should stay local-only or become a reusable preset.

## Biblio

- Turn the proposed first split for import/population versus processing/edit boundaries into a
  scoped implementation spec.
- Turn the proposed “100% match” proof rule into implementation-facing checks and tests.
- Encode the approved manual-review rules directly in code and tests where they are still only
  documented policy.

## Suppressor

- Test whether journalling entries can be hidden automatically; if not, evaluate the safest
  bot-marking or filtering fallback that still avoids loops.
- Encode the operational targets in implementation-facing docs and tests.
- Review whether the current stop conditions need a separate operator-visible status surface.
- Investigate the observed default-parallel suppressor suite failure around redirect-target
  fetching; isolated and single-threaded runs pass, so publication should not overclaim full-suite
  stability.
