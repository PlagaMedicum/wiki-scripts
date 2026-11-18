# wiki-scripts Agent Instructions

> **Protected file:** Automated agents and LLMs must never edit, replace, delete,
> rename, move, or regenerate `AGENTS.md` unless the user explicitly asks for an
> `AGENTS.md` change in the current task. Otherwise agents may read it and propose
> changes in chat.

## Authority and context

- This monorepo contains independent services/tools. Use root `README.md` for routing, then the
  affected subsystem's README/architecture/operations/testing owners; task instructions define
  authorized scope. Current source/tests precede historical inference.
- Suppressor tasks normally load only `suppressor/README.md`, relevant `suppressor/docs/` owners,
  and affected modules/tests—not unrelated subsystems.
- Before nontrivial work report risk, owner/files, invariants, first test/expected RED (N/A for
  docs/refactors), available/missing tools, scope, and proceed/investigate-only/stop verdict. Use
  evidence, not confidence scores.
- Restricted work needs established ownership, operational understanding, and required runtime/tools
  before implementation: architecture/policy; auth/permissions; suppression/RevDel semantics;
  Toolforge lifecycle; persistent schemas; dependencies/major upgrades; concurrency/queue redesign;
  destructive migrations/broad cleanup. Otherwise investigate or stop and ask; do not guess.

## Minimal-engineering rule

- Minimize implementation and operator effort—not investigation, correctness, validation, or safety.
  Apply KISS/YAGNI to current requirements, not hypothetical features.
- Try no change/deletion → repository/adopted tool → extend its owner → platform/stdlib/existing
  dependencies → small local implementation. New machinery needs a demonstrated gap.
- Keep owners cohesive, interfaces narrow, dependencies acyclic. Abstractions must hide real
  complexity, enforce a boundary, or remove proven duplication; small duplication is cheaper than a
  wrong abstraction.
- No speculative managers, registries, services, factories, buses, plugins, frameworks, caches,
  switches, concurrency, or public APIs; no unrelated cleanup or metric-driven fragmentation.
- New dependencies need approval, maturity, maintainability, auditability, and lower lifetime cost
  than a clear local solution.

## Architecture and invariants

- Organize first by service/domain, then layer. Keep CLI/operator/HTTP/daemon adapters thin:
  explicit typed inputs/results feed application/domain services, storage adapters, and platform
  edges; core must not import presentation, Toolforge formatting, launch wrappers, unrelated
  storage, or test helpers.
- No test-only exports/runtime switches, private-helper chains, mocks/fallbacks altering production
  semantics, or compatibility shims for removed internal APIs. Do not put integration glue in core
  merely to simplify tests.
- Suppressor protection uses authoritative RecentChanges polling; EventStreams is outside the
  latency-critical path. Exactly one production daemon owns each wiki/state directory;
  recovery/reconciliation favors correctness.
- Submit matched-edit suppression/RevDel before nonessential persistence, status, telemetry,
  filesystem/cache work, reconciliation, optional logging, or bookkeeping. Preserve observed-edit →
  RevDel latency; distinguish poll freshness, throughput, and observed-to-hidden time.
- Keep hot-path work bounded, not growing with uptime. Cache/local state needs demonstrated
  measurement; poll interval/worker/queue changes need observed behavior. Prefer simple serial flow
  over speculative concurrency and batches only where APIs/measurements justify them.
- Toolforge production runs foreground through Jobs; detached-host deployment is separate, never
  permission to detach Toolforge jobs. Credentials come from environment variables, not committed
  files.
- Reload/reconciliation uses the deliberate shared command surface, not cross-pod signals. No
  alternate CLI implementation, global hidden side channel, generic framework, plugin layer, bus, or
  registry around existing daemon behavior.
- Collections require bounds, replacement semantics, time windows, operator control, or an explicit
  unbounded justification. Do not retain recursive status history; keep a compact current snapshot
  and justified bounded previous summary.
- Persistent schema changes identify owner, compatibility expectations, deterministic serialization
  tests, and applicable migration behavior. Preserve protection semantics; benchmark/test
  convenience never authorizes weakening them.
- Files/functions are design signals, not quotas: reconsider ownership around 350 source lines;
  inspect splitting near 450; above 600 no substantial addition without real split/documented
  reason. Review test modules above ~600, functions above ~60 lines; above ~100 needs an explicit
  reason not to split. Extract real boundaries, not fragments or synthetic generic modules.

## Tests first

- Behavior changes/bugs: write the smallest meaningful regression/contract test before production
  code; observe the expected behavioral RED, implement the smallest complete fix, rerun to GREEN,
  then refactor only while green. No retrofitted tests that merely bless implementation.
- Test observable success/failure, boundaries, invariants, and relevant transitions—not constants,
  accessors, private wiring, or implementation shape. Tests stay deterministic/isolated; remove
  coverage only after proving its contract obsolete or still covered.
- Refactors preserve a relevant GREEN baseline. Docs/mechanical edits need appropriate checks, not
  invented RED. If automation is impractical, explain why and perform real runtime/manual
  verification.
- Never weaken tests, lint/types, architecture, coverage/budgets, mutation scope, security, CI, or
  evidence to pass. No unevidenced suppressions/exceptions, dead code, swallowed failures, fake
  fallbacks/success; report conflicts instead.
- State/protection changes cover relevant errors and persistence/recovery boundaries. Test difficult
  code by inspecting ownership/interfaces first, not by exporting internals or loosening production
  contracts.

## Verification and evidence

- Start focused, broaden by risk; Rust normally needs `cargo fmt --check`, `cargo check`, `cargo
  test`. Use existing Make/script commands; required aggregate gates are additional requirements,
  not substitutes for regression tests.
- Root `make check` delegates to both `suppressor` and `biblio`; subsystem-only success does not
  prove the required root gate. Keep root Makefile a thin orchestrator: delegate existing targets,
  use `ARGS`/Make variables for one-offs, add root targets only for recurring cross-project
  workflows.
- Before commits, stage intended hunks, inspect the staged diff, run required checks against the
  exact artifact where practical, then make an atomic coherent commit. No temporary scaffolds or
  weakened gates left behind.
- Report source/artifact identity, actual commands/results, and unavailable checks; source/config
  edits alone are not runtime/deployment evidence. Remote/CI/deployment claims require the exact
  matching artifact.
- Incidents: preserve evidence before changing resources. Capture binary/source identity, separate
  facts/hypotheses, and do not blame OOM/eviction/MediaWiki/Toolforge/rate limits without
  observation.

## Safety and delivery

- Start with `git status --short` and `git diff --stat`; use targeted searches/bounded reads, not
  broad generated/vendor/cache/lockfile/log dumps. Optional agent tools are not prerequisites; never
  install implicitly.
- Preserve unrelated work. No reset/restore/discard/stash, amend/rebase/force-push/history rewrite,
  or overwrite without explicit permission.
- Ask before destructive edits, broad refactors/moves, dependencies/installations, services,
  network/API/auth changes, or expanded scope. Authorization is task/session-specific; do not ask
  again within approved scope.
- Never expose credentials, cookies, tokens, private data, or suppressed content in
  output/fixtures/docs/commits. No telemetry or unsolicited network.
- Update existing topic owners with behavior/interface changes; no duplicate policy/command
  documents or dated status in always-loaded rules.
- Production resources, job lifecycle, services/restart logic, environment variables, container
  images, wiki targets, destructive/write-heavy commands, and suppression/permission changes require
  explicit approval after explaining affected resources, failure modes, alternatives, verification,
  and rollback.
- Never print/store bot passwords, Toolforge envvar values, API tokens, cookies, or private
  operational data; fixtures are sanitized. Reconcile any exposure of suppressed metadata/private
  state with security and operations owners before editing.
- Broad cleanup starts by mapping service/domain ownership, entry points/commands, tests,
  persistence, runtime configuration, operator interfaces, dead paths, and already-duplicated
  doctrine. Propose its boundary before deletion/moves; remove dead weight without losing test
  strength or operator behavior.

<!-- AI-assisted maintenance. -->
