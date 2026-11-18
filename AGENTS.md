> **Protected file:** Automated agents and LLMs must never edit, replace, delete,
> rename, move, or regenerate `AGENTS.md` unless the user explicitly asks for an
> `AGENTS.md` change in the current task. Otherwise agents may read it and propose
> changes in chat.

## Authority and context

Use the smallest amount of repository context needed to do the task correctly.

Authority order:

1. `AGENTS.md`
2. Task-specific user instructions
3. Relevant project-local README and architecture/operations/testing documentation
4. Current source code and tests
5. Git history for superseded behavior, regressions, and operational context

For `suppressor` work, normally read only:

- `suppressor/README.md`
- the relevant file under `suppressor/docs/`
- the tests and production modules directly owned by the task

Do not read the whole repository by default.

If `~/.codex/RTK.md` is readable, follow it for token-efficient
shell use. Prefer `rtk` for supported commands when available. Never install it
implicitly. If compressed output is ambiguous, rerun only the smallest necessary
raw command.

## Task-fit preflight

Before editing, prove enough understanding to proceed.

For non-trivial work, use this compact record when useful:

```text
TASK-FIT
risk: routine | elevated | restricted
owner: <module/files>
invariants: <1-3 contracts that must remain true>
test: <first test/check>
red: <expected failure, or N/A for pure refactor/non-behavioral work>
scope: <expected files>
verdict: proceed | investigate-only | stop
```

`restricted` includes:

- architecture or policy changes;
- authentication, credentials, permissions, or security behavior;
- revision-deletion/suppression semantics;
- Toolforge deployment/runtime lifecycle;
- persistence/state format changes;
- dependency additions or major upgrades;
- concurrency/queue redesign;
- destructive migration or broad cleanup.

If ownership, invariants, runtime behavior, or required tools are unclear, investigate
or ask the user. Do not guess through consequential uncertainty.

## Repository workflow

Start normal work with:

```bash
git status --short
git diff --stat
```

Then localize narrowly with:

```bash
fd
rg
```

Prefer symbol-aware or project-local repository intelligence when available.
Read only the files needed to establish ownership and invariants.

Avoid:

- whole-tree dumps;
- dependency trees;
- giant lockfiles;
- generated artifacts;
- broad logs;
- unrelated docs;
- speculative exploration.

Preserve unrelated user work. Never reset, restore, discard, stash, amend,
rebase, force-push, rewrite history, or overwrite unrelated work without explicit
permission.

## Minimal-engineering rule

Minimize implementation, not understanding, correctness, validation, or safety.

Before adding code, ask in this order:

1. Can the requirement be satisfied with no production change?
2. Can code be deleted or simplified instead?
3. Does the repository already own the capability?
4. Can the existing owner be extended directly?
5. Can stdlib or existing dependencies solve it?
6. Can a small local implementation solve it?
7. Only then consider a new abstraction, dependency, service, framework, worker,
   cache, queue, configuration switch, or public API.

Apply KISS and YAGNI aggressively.

Prefer:

```text
deletion
> direct local fix
> reuse of existing owner
> small explicit helper
> new abstraction
> new dependency/subsystem
```

Small duplication is cheaper than the wrong abstraction.

Do not add speculative managers, registries, orchestration layers, generic
frameworks, background services, async/concurrency, caches, or configuration
surface without demonstrated present need.

## Architecture guardrails

Organize by service first, then by domain/layer inside that service.

A file split is not an architecture boundary unless dependencies point the right
way.

Dependencies should point inward:

```text
operator / CLI / Toolforge adapter
        ->
application / daemon coordination
        ->
domain rules / state contracts
        ->
small infrastructure adapters
```

Core/domain/application code must not depend on:

- CLI rendering;
- operator presentation;
- process launch wrappers;
- Toolforge command formatting;
- unrelated storage details;
- ad hoc global state;
- test-only helpers.

Controllers and CLI commands translate operator intent into typed backend calls
or compact state reads. They must not become alternate implementations of daemon
logic.

Keep runtime communication explicit:

- typed inputs;
- typed results;
- bounded queues;
- compact persisted snapshots;
- deliberate command/request surfaces.

Avoid hidden side channels.

### Suppressor-specific invariants

For `suppressor`, preserve these unless the user explicitly requests a behavior
change:

- live protection is based on authoritative RecentChanges polling;
- EventStreams is not part of the latency-critical live path;
- matched-edit suppression/revision deletion must happen before nonessential
  persistence, status rendering, telemetry, or bookkeeping;
- exactly one production daemon should own a given wiki/state directory;
- persistent state must remain bounded or have an explicit retention policy;
- Toolforge production runs in the foreground through the Jobs framework;
- credentials come from Toolforge environment variables, not committed files;
- control actions such as reconciliation/reload should use the deliberate shared
  command surface rather than cross-pod signals;
- recovery and reconciliation must favor correctness over cleverness.

Do not weaken protection semantics to improve benchmarks or make tests easier.

## File-size and complexity limits

Large files are a design smell, not an automatic refactor mandate.

For production source:

- around **350 lines**: reconsider ownership and whether the module is accumulating
  unrelated responsibilities;
- around **450 lines**: treat as a split signal and inspect for a natural boundary;
- above **600 lines**: do not add substantial new behavior without either splitting
  along a real ownership boundary or documenting why the file must remain unified.

For tests:

- prefer focused test modules grouped by contract;
- above roughly **600 lines**, split when there is a clear behavioral boundary;
- do not fragment tests merely to satisfy a number.

For functions:

- prefer functions that fit on one screen;
- above roughly **60 lines**, inspect for multiple responsibilities;
- above roughly **100 lines**, require a clear reason not to split.

These are guardrails, not mechanical quotas. Never create meaningless files,
helpers, or abstractions merely to reduce line counts.

## Tests first, not afterward

For executable behavior changes and bug fixes use:

```text
RED -> GREEN -> REFACTOR
```

1. Write or adjust the smallest meaningful regression/behavior test first.
2. Run it before changing production code.
3. Confirm it fails for the expected behavioral reason.
4. Make the smallest complete production change.
5. Rerun the focused test and confirm GREEN.
6. Refactor only while the relevant tests remain green.
7. Run broader regression/quality gates appropriate to the touched risk.

A bug fix requires a reproducing regression test before the fix.

Do not implement behavior first and retrofit tests afterward merely to bless the
implementation.

Tests should verify observable contracts, boundaries, failures, persistence
semantics, and invariants. Avoid tests that merely restate:

- constants;
- accessors;
- wiring;
- private helper shape;
- implementation details with no externally meaningful contract.

For a pure behavior-preserving refactor:

1. establish a relevant GREEN baseline first;
2. refactor;
3. preserve that behavior with the same tests.

Do not manufacture a fake RED test for a refactor.

Documentation-only, comment-only, formatting-only, and purely mechanical config
changes are exempt where no meaningful executable test applies.

If behavior cannot be meaningfully automated, state that explicitly and perform
the nearest runtime/operational verification instead of inventing a low-value test.

## Test-suite quality and cleanup

Treat tests as production-quality code.

When touching an area, inspect nearby tests for:

- duplicate coverage;
- tests coupled to private implementation shape;
- obsolete behavior;
- over-mocking;
- broad fixtures that hide ownership;
- assertions that cannot catch regressions;
- flaky timing dependence;
- network/environment dependence that should be deterministic;
- dead helpers;
- tests that pass for the wrong reason.

Prefer a smaller suite of high-value contract tests over a large pile of brittle
checks.

Do not delete or weaken a test merely because it blocks a change. If a test is
wrong, first prove the contract it encodes is obsolete or invalid.

Cleanup should reduce surface area:

```text
remove obsolete test
> merge duplicate tests
> simplify fixture
> narrow helper
> add new test
```

Never turn cleanup into broad normalization unrelated to the task.

## Writing code

Prefer compact, explicit code with narrow ownership.

- Keep ordinary code self-explanatory.
- Document only interfaces, invariants, failure modes, compatibility constraints,
  and hard-won operational lessons.
- Avoid comments that narrate obvious control flow.
- Remove dead code and accidental abstraction before adding structure.
- Prefer deterministic logic over model-assisted or heuristic behavior.
- Prefer bounded data structures and explicit retention limits in long-lived
  daemons.
- Do not silently swallow errors.
- Do not add fake fallback/success paths.
- Do not convert a hard failure into silent degradation unless that degradation is
  explicitly part of the contract.

### Dependencies

Prefer stdlib and existing dependencies.

Add a dependency only when it clearly reduces maintenance or risk and is:

- mature;
- actively maintained;
- widely used;
- auditable;
- appropriately small for the problem.

Do not add a dependency merely to avoid thinking through ownership.

Any dependency change is elevated-risk and requires explicit justification.

## Performance and latency discipline

Optimize only measured or clearly structural costs.

For latency-sensitive `suppressor` work:

- preserve the shortest path from observed RecentChanges edit to RevDel submission;
- do not put status persistence, telemetry collection, filesystem reads, cache
  maintenance, reconciliation, or optional logging before the protection action;
- do not add concurrency merely because work can be parallelized;
- do not lower polling intervals, alter queue capacities, or change worker counts
  without evidence;
- distinguish throughput, poll freshness, and end-to-end observed-to-hidden latency.

Prefer a simple serial critical path over clever concurrency when the existing
load does not justify complexity.

## Persistence and state discipline

Long-lived services must make retention obvious.

Every persistent or in-memory collection should be one of:

```text
bounded
replace-on-update
time/window limited
operator-controlled
explicitly justified as unbounded
```

State schema changes require:

- ownership identified;
- backward/forward compatibility considered;
- deterministic serialization tests;
- migration behavior documented when applicable.

Do not preserve recursive status history. Prefer one compact current snapshot and,
where operationally justified, one bounded previous-generation summary.

Persist only what is required for correctness, recovery, or diagnosis.

## Toolforge and operational safety

Treat Toolforge as production infrastructure.

Ask before:

- changing production resources;
- changing job type or lifecycle behavior;
- adding services or health-check restart logic;
- changing credentials/envvars;
- changing deployment images;
- changing wiki targets;
- running destructive or write-heavy operational commands;
- altering suppression behavior.

Read-only inspection is preferred before intervention.

For incidents:

1. preserve evidence first;
2. classify proven facts vs hypotheses;
3. capture exact binary/source identity;
4. avoid “fixing” resource limits before understanding the failure;
5. prefer instrumentation over speculative redesign when evidence is missing.

Do not claim OOM, eviction, rate limiting, MediaWiki failure, or Toolforge fault
without evidence.

## Security and privacy

Never print, commit, persist in repo files, or include in test fixtures:

- bot passwords;
- Toolforge envvar values;
- private tokens;
- session cookies;
- private API credentials.

Use redacted fixtures.

Do not add telemetry or unsolicited external network access.

Security/privacy behavior is restricted scope. If a requested change could expose
suppressed metadata, credentials, or private operational state, stop and reconcile
the design before editing.

## Documentation discipline

Keep documentation small and current.

Prefer:

- root/project README for entry points;
- project-local architecture/operations/testing docs for current truth;
- code-adjacent comments for tricky invariants;
- short incident notes only when they protect future operation.

Do not duplicate the same contract across many files.

When an operator-facing interface changes, update the documentation that defines
that interface.

Delete stale docs rather than layering new instructions over obsolete ones.

## Quality gates

During implementation, run the narrowest relevant check first.

For Rust work, normally:

```bash
cargo fmt --check
cargo check
cargo test
```

Use existing Makefile targets where they define the project workflow.

Treat the repository's aggregate check target (for example `make check`, if
present) as the required pre-commit gate.

Warnings should remain errors where the project enforces that policy.

Do not weaken lint, test, architecture, security, or CI gates to make a change
pass.

If a gate cannot run because of the environment, record that exact limitation.
Do not claim success.

## Exact Git-state discipline

Before commit:

1. stage only intended files/hunks;
2. inspect the staged diff;
3. run required checks against the exact artifact being committed when practical;
4. ensure unrelated work is not included.

A successful source-changing chunk should end with:

```text
implementation complete
-> focused test GREEN
-> relevant regression tests GREEN
-> required QA GREEN
-> staged diff reviewed
-> atomic commit
```

Do not bundle unrelated cleanup with a behavior fix.

Do not amend, rebase, force-push, or rewrite history without explicit permission.

Never claim a test, runtime result, deployment, commit, push, or CI result that
was not actually observed.

## Cleanup discipline

The repository should become smaller and clearer over time.

When doing cleanup, prefer:

```text
delete dead code
-> delete stale docs
-> remove duplicate tests/helpers
-> simplify ownership
-> reduce dependencies
-> reduce configuration surface
-> split only at real boundaries
```

Do not perform cleanup simply because nearby code is imperfect.

A cleanup task should have an explicit scope and a before/after invariant.

For broad cleanup, first map:

- executable entry points;
- active tests;
- persistence/state owners;
- Toolforge/runtime owners;
- operator commands;
- dead or legacy paths.

Then propose the cleanup boundary before deleting or moving broad areas.

## Hard quality rules

Automated agents must not:

- weaken tests or lint to make changes pass;
- change protection semantics without explicit user intent;
- introduce speculative architecture;
- add broad abstraction for a local problem;
- silently install dependencies or tools;
- start or modify services without authorization;
- perform unrelated cleanup;
- hide errors behind permissive fallbacks;
- treat generated/model output as evidence when deterministic evidence exists;
- claim certainty when evidence is incomplete.

If a guardrail conflicts with the task, report the conflict instead of changing
the guardrail autonomously.

## Reasoning discipline

Treat user examples as evidence for an underlying principle, not text to copy
mechanically into permanent policy.

Before changing code, identify:

- the actual failure mode;
- the owner;
- the invariant;
- the smallest test that proves the contract;
- the smallest implementation that restores it.

Distinguish:

```text
proven bug
observability gap
performance issue
cleanup opportunity
incident hypothesis
future hardening
```

Do not merge those categories merely because they appear in the same investigation.

When evidence conflicts, stop and reconcile it before implementation.

When uncertain about a consequential design choice, ask the user.

## Communication discipline

Communicate like a compact engineering protocol.

Do not:

- restate the whole task;
- narrate routine tool calls;
- dump large logs;
- repeat unchanged context;
- provide speculative progress commentary.

Surface meaningful findings early.

Final reports should normally contain only:

- changed behavior/files;
- tests and gates actually run;
- remaining limitations/risks;
- commit/push/deployment evidence when applicable.

## Strategic direction

`wiki-scripts` should stay small.

Prefer:

```text
simple services
+ explicit state
+ narrow interfaces
+ deterministic behavior
+ high-value regression tests
+ minimal Toolforge integration
```

over building a general framework.

For `suppressor`, prioritize:

```text
correct protection semantics
+ minimal RecentChanges -> RevDel latency
+ bounded state
+ deterministic recovery
+ observable failures
+ simple unattended Toolforge operation
```

Every new abstraction, dependency, worker, queue, compatibility layer, or runtime
feature should have to justify its continued existence.
