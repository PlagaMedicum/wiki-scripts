# Repo Cleanup And Architecture Plan

This is the only durable planning document for the repository. Project docs should describe current
interfaces, operations, and testing rules; future work belongs here.

## Operating Rules

- Commit each completed cleanup slice after the relevant gate passes.
- Preserve current suppressor protection behavior unless a slice explicitly says otherwise.
- Use established open-source tools when they prevent duplicated maintenance.
- Keep repo checks strict: root `make check` is the normal pre-commit gate.
- Organize by service first, then by domain/layer inside that service.
- Prefer enforceable boundaries: Python import contracts and Rust workspace crates.
- Keep docs short and current. Remove stale incident plans after the durable lesson is captured.

## Slice 1: Centralize Planning

Start when project docs contain future-direction, task-ID, or refactor-plan content.

Work:

- Create this repo-level plan.
- Delete project-local plan files that duplicate this plan.
- Replace project-local future-work sections with a short pointer here.
- Keep operational lessons in operations/testing docs only when they protect current behavior.

End when:

- Project-local docs no longer contain stale task IDs, old refactor plans, or future-work sections.
- Root `make check` passes or any environment-only limitation is recorded.

## Slice 2: Rust Workspace Boundaries

Start when suppressor still relies on one large crate for enforced architecture.

Work:

- Convert `suppressor` to a small Cargo workspace.
- Keep one operator binary named `suppressor`.
- Move inward code into crates that do not depend on controllers or transport adapters.
- Put MediaWiki, filesystem state, signals, metrics, and launch adapters outside the domain crates.
- Keep CLI/status/server-start controllers thin and dependent on application ports only.

End when:

- Cargo crate dependencies enforce inward direction without custom scripts.
- `cargo deny check`, clippy, and suppressor tests pass from `make -C suppressor check`.
- No runtime behavior, config schema, or state file name changes are introduced by the split.

## Slice 3: Suppressor Runtime Shrink

Start after workspace boundaries exist or when a single runtime module blocks safe edits.

Work:

- Split daemon status/event handling, live polling, source-refresh scheduling, and hide outcome
  recording into small service modules.
- Keep live hiding higher priority than background work.
- Keep background work bounded and resumable after live work completes.
- Remove duplicate command/recovery runtime code only after its replacement path is covered.

End when:

- No suppressor source file is large enough that changing one behavior requires loading unrelated
  domains.
- Source-list edits still refresh the cache and schedule history sweeps.
- Live hide, catch-up, signal, status, and server-start tests pass.

## Slice 4: Biblio Service Boundaries

Start when `biblio` backend modules still share types or imports with UI/controller code more than
needed.

Work:

- Keep `import-linter` contracts strict and extend them only after real boundaries exist.
- Separate source onboarding/import flow from page-processing/edit flow behind typed interfaces.
- Move UI-facing rendering data toward compact snapshots instead of rich backend objects.
- Keep source definitions in `sources/<source_id>/source.toml`; do not recreate generated docs.

End when:

- Backend modules cannot import UI, CLI, startup, or management controllers.
- Management controllers cannot import run workflow or page execution.
- UI can render from snapshots or protocols without reaching into backend internals.
- `make -C biblio check` passes.

## Slice 5: Dependency And Tool Hygiene

Start when checks warn about vulnerable, duplicated, unused, or oversized dependencies.

Work:

- Keep `cargo-deny`, Ruff, Import Linter, pytest, pip-audit, clippy, and formatter gates required.
- Patch lockfile advisories instead of ignoring them.
- Treat duplicate Rust crates as warnings until a safe dependency trim removes them.
- Evaluate `cargo-machete` or similar tools as advisory only before making them required.
- Remove dependencies that no longer pay for their maintenance/context cost.

End when:

- Root `make check` passes.
- New dependency additions include a reason, boundary owner, and license/audit fit.
- No custom local quality script duplicates a mature tool.

## Slice 6: Documentation Economy

Start when docs contain stale incident evidence, generated planning artifacts, or repeated
architecture rules.

Work:

- Keep one root README, one repo plan, and project-local README/architecture/operations/testing docs.
- Move durable lessons near the code or into the relevant current doc.
- Delete old task evidence once the current rule and test coverage exist.
- Keep sensitive incident identifiers out of tracked docs.

End when:

- Project docs describe current truth, not backlog.
- Future work appears only in this file.
- README navigation points to the central plan.

## Slice 7: Deployment And Operations Proof

Start before trusting a suppressor server rollout after daemon-critical edits.

Work:

- Build the reviewed server artifact.
- Record safe artifact identity for the deployed binary.
- Start through the intended launch path and verify PID, status, log path, and config agreement.
- Reconnect after logout and confirm fresh daemon-owned status.
- Run a controlled live or dry-run watched-edit smoke check while background work is idle or queued.
- Record a short CPU/RSS/resource sample for low-spec operation.

End when:

- Runtime status is fresh and healthy or truthfully degraded with an actionable issue.
- Live protection evidence is current and tied to the deployed binary.
- No secrets, raw sensitive titles, actors, comments, revision IDs, or hidden content are recorded.

## Slice 8: Optional Future Service Split

Start only if one process is no longer enough for failure isolation, operation, or context economy.

Work:

- Split by microservice first, not by technical layer first.
- Define communication through CLI, signals, local files, HTTP, queues, or another standard
  interface before moving code.
- Keep TUI/controller processes unable to import backend internals.
- Preserve local-first operation unless the operator explicitly approves a broader deployment model.

End when:

- Each process has one responsibility, one operator contract, and one documented interface.
- Cross-service communication is typed, bounded, observable, and testable.
- The split reduces maintenance risk instead of adding orchestration overhead.
