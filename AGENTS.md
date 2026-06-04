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

- Prefer compact, explicit code with narrow ownership. Remove duplication, generated artifacts, and
  accidental abstractions before adding new structure.
- Prefer established open-source tools and libraries over local reimplementation when they clearly
  reduce maintenance or risk. Before adding one, check that it is community-supported,
  time-tested, actively maintained, and small enough for the problem it solves.
- Do not add a dependency just to avoid thinking through ownership. If the tool is obscure,
  unmaintained, oversized, hard to audit, or only saves a few lines of clear local code, keep the
  local implementation.
- Document only facts that protect future work: interfaces, invariants, failure modes, and hard-won
  operational lessons. Keep ordinary code self-explanatory.
- Use existing Makefiles for common commands. Add a command only when repeated manual invocations
  show that it belongs in the project workflow.
- Treat `make check` as the required pre-commit gate. Formatting, linting, dependency audits,
  architecture checks, and tests must pass unless the failure is explicitly recorded as an
  environment limitation or approved temporary exception.
- Keep normal lint targets strict: warnings are errors, and broad `allow(...)` escapes need a local
  reason or must be replaced with narrower code ownership.

## Architecture guardrails

- Organize by service first, then by domain/layer inside that service. A directory split is not an
  architecture boundary unless imports also point the right way.
- Dependencies point inward: domain and application code must not import controllers, TUI/UI,
  process launchers, storage details, transport clients, or framework adapters.
- Controllers and UIs translate operator intent and render state. They communicate with backend
  services through typed inputs, ports, CLI/API/signal/status surfaces, or compact snapshots; they
  do not reach into runtime internals for implementation details.
- For Rust, prefer workspace crates when a boundary must be enforced. Crate visibility and Cargo
  dependencies are stronger guardrails than a large single crate split into files.

## Reasoning rules

- Treat user examples as evidence for an underlying principle, not text to copy into permanent
  rules. First identify the failure mode, then choose the smallest durable guidance or code change
  that addresses that class of failure.
- Distinguish session instructions from repository policy. Operational comments about the current
  task do not become durable project rules unless the user asks for that explicitly.
- If a durable rule would mostly mirror one prompt phrase, ask before writing it down.
- Prefer positive principles and scoped ownership boundaries over long lists of one-off bans.
- When uncertain, ask the operator instead of making a broad, confident policy decision.

## Current cleanup direction

- Spec Kit is no longer part of this repository.
- Keep suppressor protection behavior stable unless the user explicitly asks to change it.
- Prefer shrinking docs, generated artifacts, optional UI, dependencies, and duplicate code before
  adding new structure.
- Treat modules as small internal services. Each service owns one domain, exposes a narrow
  interface, and avoids reaching across boundaries for implementation details.
- Keep controllers thin. CLI commands may translate operator intent into backend calls or read
  state, but backend/runtime modules must not depend on command rendering or operator presentation.
- Keep communication explicit: pass typed inputs, return typed results or compact state snapshots,
  and avoid global side channels unless they are deliberate runtime state surfaces.
- Keep docs short: README for entry points, one architecture overview, one operations note, one
  testing note. Put durable tricky implementation facts near the code they protect.
- For suppressor work, read `suppressor/README.md`, the relevant `suppressor/docs/` file, and only
  the code touched by the task.
