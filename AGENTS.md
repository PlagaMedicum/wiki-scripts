---
docmeta:
  status: maintained
  review: workflow-local
  purpose: Repo-local agent instructions and context-loading rules for work in this repository.
  source: document-local metadata
---

# Agent Instructions

## Token economy rules

- Try to spare as much tokens as you can, when working on the repo
- Do not read the whole repository.
- Start with `git status`, `git diff --stat`, `fd`, and `rg`.
- Read only files directly relevant to the task.
- Do not paste full logs into reasoning; use summarized failing cases.
- Prefer surgical patches over broad rewrites.
- After edits, run the narrowest relevant test first.
- Use `rtk` for token economy.

## Writing code
- Try to write as minimal amount of code as possible, according to KISS (keep it simple stupid).
- Document your code and ensure adding documentation and notes about experiences with hard issues, to not repeat mistakes.
- Always prefer easy, performant, reliable, fast, simple, not greedy on resources, optimizes, compact sollutions.
- Ensure reusability of your code, do not repeat yourself.
- Store all common commands and check common commands from Makefiles. If you repeat some commands often, add them into according makefiles.

<!-- SPECKIT START -->
For repo rules and current structure, read `.specify/memory/constitution.md`
and `specs/000-repo-governance/`.

For scoped implementation context, read `.specify/feature.json` only if it
exists, then open that feature's `plan.md`. If there is no active feature
pointer, use the relevant `specs/NNN-feature-name/` directory directly.

The current active plan is `specs/001-real-time-suppression/plan.md`
while `.specify/feature.json` points there.
For `001-real-time-suppression`, read `spec.md` and `plan.md` first. The
active goal is the minimal stable suppressor server only: fast live hide,
bounded catch-up after downtime, truthful degraded or blocked status, exact
deployment proof for the running binary, and an emergency live-only production
profile until automatic verification is re-approved after soak. Do not widen
scope from historical checklist, TUI, reporting, template, or inactive-feature
material unless the user explicitly asks. The authoritative reading order for
`001` is `spec.md` -> `plan.md` -> `tasks.md` -> operator docs.
<!-- SPECKIT END -->
