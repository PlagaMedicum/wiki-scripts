# Repo Cleanup And Architecture Plan

This is the only durable planning document for the repository. Project docs describe current
interfaces, operations, and testing rules; future work belongs here.

## Plan Rules

- Task IDs are stable. Do not reuse an ID after deleting or finishing a task.
- Commit each completed task or tightly related task group after the relevant gate passes.
- Preserve suppressor protection behavior unless a task explicitly changes it.
- Use established open-source tools when they prevent duplicated maintenance.
- Keep root `make check` as the normal pre-commit gate.
- Organize by service first, then by domain/layer inside that service.
- Prefer enforceable boundaries: Python import contracts and Rust workspace crates.
- Keep sensitive incident identifiers out of tracked docs.

## Status Legend

- `done`: completed in the repo and committed.
- `ready`: can start now.
- `blocked`: needs another task, operator evidence, or a decision first.
- `later`: valid direction, but not worth doing until earlier boundaries exist.

## RCP: Repo Planning And Documentation

### RCP-001 Central Plan Surface

Status: `done`

Start when project docs contain future-direction, task-ID, or refactor-plan content.

Work:

- Create this repo-level plan.
- Link it from the root README.
- Delete project-local plan files that duplicate this plan.
- Replace project-local future-work sections with a short pointer here.

End when:

- Future work appears only in this file.
- Project docs describe current truth, not backlog.
- Root `make check` passes.

### RCP-002 Plan ID Structure

Status: `done`

Start when the central plan has slices but no stable task IDs.

Work:

- Replace loose slices with ID-based workstreams.
- Give every task start criteria, concrete work, end criteria, and verification.
- Mark completed setup work as `done` so future agents do not repeat it.
- Keep the plan compact enough to read in one pass.

End when:

- Every planned work item has a stable ID.
- Tasks can be referenced from commits and user requests.
- Root `make check` passes.

### RCP-003 Documentation Economy Pass

Status: `ready`

Start when docs contain stale incident evidence, generated planning artifacts, or repeated
architecture rules.

Work:

- Keep one root README, one repo plan, and project-local README/architecture/operations/testing docs.
- Move durable lessons near the code or into the relevant current doc.
- Delete old task evidence once the current rule and test coverage exist.
- Remove repeated architecture rules from project docs when `AGENTS.md` or this plan already owns
  them.

End when:

- `rg` over authored docs finds no stale task IDs or old refactor-plan files.
- Project docs remain useful for current operation and development.
- Root `make check` passes.

## QAG: Quality And Dependency Guardrails

### QAG-001 Strict Quality Gate

Status: `done`

Start when linting, audits, tests, and architecture checks are not all in the required project gates.

Work:

- Treat `make check` as the normal pre-commit gate.
- Keep Rust formatting, clippy with warnings as errors, tests, and `cargo-deny` required.
- Keep Python Ruff, formatting check, pytest, `pip-audit`, and Import Linter required.
- Patch lockfile advisories instead of ignoring them.

End when:

- Root `make check` passes.
- New dependency additions are covered by audit/license/source policy.
- No custom quality script duplicates a mature tool.

### QAG-002 Rust Duplicate Dependency Review

Status: `ready`

Start when `cargo-deny` reports duplicate-version warnings.

Work:

- Review duplicate crates reported by `cargo-deny`.
- Use `cargo tree -d` to identify direct causes.
- Upgrade or remove direct dependencies only when behavior risk is low.
- Keep warnings allowed until dependency owners make safe convergence possible.

End when:

- Duplicates are reduced where safe, or documented as transitive and currently accepted.
- `make -C suppressor check` passes.

### QAG-003 Unused Dependency Review

Status: `ready`

Start after QAG-001 is stable and before adding more custom tooling.

Work:

- Evaluate `cargo-machete` for suppressor and a mature Python equivalent only as advisory tools.
- Remove dependencies that are unused or no longer worth their maintenance/context cost.
- Do not make a new tool required until it proves low-noise on this repo.

End when:

- Removed dependencies are reflected in lockfiles.
- Remaining dependencies have clear ownership.
- Root `make check` passes.

## SBA: Suppressor Architecture

### SBA-001 Rust Workspace Boundary Plan

Status: `ready`

Start when suppressor still relies on one large crate for enforceable architecture.

Work:

- Define the target Cargo workspace members and dependency direction.
- Keep one operator binary named `suppressor`.
- Identify inward crates for domain/application logic.
- Identify outward crates or modules for MediaWiki, filesystem state, signals, metrics, launch, and
  controllers.
- Document the migration order before moving code.

End when:

- The workspace-crate map is decision-complete.
- No runtime behavior, config schema, or state file names change.
- `make -C suppressor check` passes.

### SBA-002 Convert Suppressor To Workspace

Status: `blocked`

Blocked by: SBA-001

Start when the workspace boundary plan is complete.

Work:

- Convert `suppressor` into a small Cargo workspace.
- Move inward domain/application code into crates that do not depend on controllers or transport
  adapters.
- Keep CLI/status/server-start controllers thin and dependent on application ports only.
- Keep the existing binary name and operator commands.

End when:

- Cargo dependencies enforce inward direction.
- Existing suppressor CLI behavior still works.
- `make -C suppressor check` passes.

### SBA-003 Split Daemon Runtime Modules

Status: `ready`

Start when `daemon.rs` still mixes live polling, status/event handling, source refresh scheduling,
and hide outcome recording.

Work:

- Extract status/event handling into a small daemon service module.
- Extract live polling and watched-change classification behind a narrow interface.
- Keep background scheduling in `daemon/background.rs` or split it only when ownership becomes
  clearer.
- Preserve live priority over background work.

End when:

- Changing one daemon behavior no longer requires loading unrelated domains.
- Source-list edits still refresh the cache and schedule history sweeps.
- Daemon-focused tests and `make -C suppressor check` pass.

### SBA-004 Shrink Command/Recovery Runtime

Status: `blocked`

Blocked by: SBA-003 or SBA-002

Start when replacement daemon boundaries are stable enough to compare against the command/recovery
runtime.

Work:

- Identify command/recovery runtime code that duplicates daemon-owned behavior.
- Keep one-shot coverage and emergency catch-up behavior stable.
- Remove duplicate runtime code only after its replacement path is covered by tests.

End when:

- No duplicate runtime path owns the same behavior without a clear reason.
- Command-report isolation still works.
- `make -C suppressor check` passes.

## BBA: Biblio Architecture

### BBA-001 Import Contracts

Status: `done`

Start when Python backend modules can import UI or controller code.

Work:

- Add Import Linter.
- Forbid backend imports of UI, CLI, startup, and management controllers.
- Forbid source-management controllers from importing run workflow and page execution.

End when:

- `make -C biblio lint` proves contracts are kept.
- `make -C biblio check` passes.

### BBA-002 Source Management Boundary

Status: `ready`

Start when source onboarding/import flow and page-processing/edit flow share more implementation
detail than necessary.

Work:

- Define typed interfaces between source management and run workflow.
- Keep shared source models below both flows.
- Avoid broad UI rewrites; move only the data needed to enforce the boundary.

End when:

- Source-management controllers cannot import run workflow or page execution.
- New tests cover source creation/import behavior.
- `make -C biblio check` passes.

### BBA-003 UI Snapshot Boundary

Status: `blocked`

Blocked by: BBA-002

Start when backend flows expose stable typed snapshots.

Work:

- Move UI rendering toward compact snapshots or protocols.
- Reduce direct UI dependence on rich backend objects.
- Keep terminal behavior and operator text stable unless explicitly reviewed.

End when:

- UI can render key flows without reaching into backend internals.
- Import contracts are tightened without breaking workflow tests.
- `make -C biblio check` passes.

## DEP: Deployment And Operations Proof

### DEP-001 Suppressor Deployment Evidence Gate

Status: `ready`

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

### DEP-002 Server Config Compatibility Review

Status: `later`

Start when config schema/defaults must change.

Work:

- Treat config changes as operator-contract changes.
- Provide migration or compatibility diagnostics.
- Verify target-host config before deployment trust.

End when:

- Config changes have tests, rollback notes, and deployment evidence.
- `make -C suppressor check` passes.

## MSA: Optional Microservice Split

### MSA-001 Process Boundary Decision

Status: `later`

Start only if one process is no longer enough for failure isolation, operation, or context economy.

Work:

- Identify the microservice first, not the technical layer first.
- Define communication through CLI, signals, local files, HTTP, queues, or another standard
  interface before moving code.
- Keep TUI/controller processes unable to import backend internals.
- Preserve local-first operation unless the operator explicitly approves a broader deployment model.

End when:

- The split reduces maintenance risk instead of adding orchestration overhead.
- Each process has one responsibility, one operator contract, and one documented interface.
- Cross-service communication is typed, bounded, observable, and testable.
