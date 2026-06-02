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

## Current cleanup direction

- Spec Kit is no longer part of this repository.
- Keep suppressor protection behavior stable unless the user explicitly asks to change it.
- Prefer shrinking docs, generated artifacts, optional UI, dependencies, and duplicate code before
  adding new structure.
- Keep backend/runtime code separate from operator presentation. Commands may read backend state;
  backend modules must not depend on command rendering.
- Keep docs short: README for entry points, one architecture overview, one operations note, one
  testing note. Put durable tricky implementation facts near the code they protect.
- For suppressor work, read `suppressor/README.md`, the relevant `suppressor/docs/` file, and only
  the code touched by the task.
