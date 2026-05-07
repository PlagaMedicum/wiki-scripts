---
docmeta:
  status: maintained
  review:
  - client-input-derived
  - approved
  purpose: Repo governance rules and non-negotiable workflow requirements.
  source: .specify/doc-registry.json
---

<!--
Sync Impact Report
Version change: 1.8.0 -> 1.9.0
Modified principles:
- Added IX. Public-Repo Privacy For Sensitive Edit Evidence
- IV. Deterministic Documentation, Safe Writes, And Honest Status (expanded tracked evidence privacy)
- Workflow And Quality Gates (added mandatory synthetic-fixture and redaction requirements)
Added sections:
- IX. Public-Repo Privacy For Sensitive Edit Evidence
Removed sections:
- None
Templates requiring updates:
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/tasks-template.md
- ✅ README.md
- ✅ specs/000-repo-governance/spec.md
- ✅ specs/000-repo-governance/quickstart.md
- ✅ .specify/extensions/docs/README.md
- ✅ .specify/extensions/docs/commands/speckit.docs.md
- ✅ specs/001-real-time-suppression/spec.md
- ✅ specs/001-real-time-suppression/plan.md
- ✅ specs/001-real-time-suppression/tasks.md
- ✅ specs/001-real-time-suppression/quickstart.md
- ✅ specs/001-real-time-suppression/contracts/runtime-status.md
- ✅ suppressor/src/catchup.rs
- ✅ suppressor/src/commands.rs
- ✅ suppressor/src/runtime.rs
- ✅ suppressor/src/state.rs
- ✅ suppressor/src/stream.rs
- ✅ suppressor/src/tui_status.rs
- ✅ suppressor/src/tui_view.rs
- ✅ suppressor/src/worker.rs
- ✅ suppressor/src/mw_api.rs
- ⚠ `.specify/templates/commands/*.md` is not present in this repo; repo-local command guidance was checked in `.specify/extensions/docs/commands/` instead
Follow-up TODOs:
- Docs gate is blocked by unrelated inactive feature metadata:
  `specs/002-fix-git-commit/checklists/requirements.md` lacks YAML frontmatter. Do not resolve
  this during the active suppressor MVP freeze unless the human owner explicitly allows touching
  inactive `002` artifacts.
-->

# Wiki Scripts Constitution


## Core Principles

### I. Separate Tools First

This repository MUST be treated as a collection of separate wiki tools. New work SHOULD start as a
separate tool unless an existing tool clearly owns the problem.

### II. Explicit Boundaries, Minimal Coupling

Projects MUST keep domain logic, orchestration, and adapters visibly separated. Significant layers,
frontends, and backends MUST communicate through explicit interfaces. Shared code is allowed, but
it SHOULD be isolated deliberately in modules, libraries, or separate tools when that boundary is
real. "We may reuse this later" is not enough reason to keep unrelated workflows in one runtime or
one tangled module graph.

### III. Narrow, Risk-Based Scope

Each tool MUST keep a clear mission. `biblio` is bibliography-first. `suppressor` is narrow,
speed-sensitive, and safety-sensitive. Broadening a tool beyond its current mission requires an
approved spec.

### IV. Deterministic Documentation, Safe Writes, And Honest Status

Managed human docs MUST get their metadata from `.specify/doc-registry.json` through deterministic
tooling. No doc may claim review or approval state unless that label is present in the registry.
Managed-doc review or approval changes become durable only when the registry is updated and synced;
Markdown-only metadata edits do not count as durable review evidence. Accepted repo direction
belongs in `specs/000-repo-governance/spec.md`. Unresolved repo-level governance questions or
standing-governance review follow-up belong in `specs/000-repo-governance/research.md`.
Feature-scoped unresolved human input belongs in feature-local `questions.md` or `review-queue.md`
while that feature is active. Resolved temporary-surface items SHOULD be folded into durable docs and
cleaned out of temporary files instead of kept as a second archive. Maintained standing-governance
docs MUST NOT retain inline TODO-style review comments once that feedback has been captured in an
authoritative temporary surface. Broad docs-maintenance rewrites MUST offer an inspectable or
narrowed execution path before mutation, and feature-generation steps MUST NOT overwrite filled
artifacts unless an explicit overwrite action is requested. Docs and operator surfaces MUST
distinguish current behavior from future direction, and they MUST NOT silently imply that an old
verification path or setup is still authoritative when it is not. Tracked docs, examples,
contracts, tests, code comments, and release evidence MUST NOT preserve real sensitive-edit
incident identifiers when synthetic or redacted evidence can prove the same lesson.

### V. Stable Config, Compatibility, Non-Destructive Change, And Explicit Approval

Repository work MUST default to additive, non-destructive, backward-compatible changes when it
touches user work surfaces, configs, state files, schemas, CLIs, operator reports, launch paths,
or other established workflows. Destructive edits, mass rewrites, major refactors that invalidate
current setups, incompatible schema/config/state/report changes, and any change that can disrupt
previous setups MUST NOT be applied silently or on assumption; they require explicit human approval
before execution. When such a change is approved, the active spec, plan, tasks, and affected docs
MUST name the impacted surface, compatibility strategy, migration steps, fallback or rollback
path, and the operator-visible prompt or diagnostic that prevents false healthy, false compatible,
or false complete readings. Reliability-sensitive automation MUST prefer preview, dry-run,
compatibility fixtures, and guarded migration paths over blind mutation.

Config surfaces are stability-critical operator contracts, not casual implementation details. Any
change to tracked config files, config schema, default values, environment variable names, config
loading semantics, or deployment-required config sections MUST be motivated by a specific runtime,
safety, compatibility, or operator-control need and MUST receive explicit human review before it is
used for production trust. Agents MUST NOT churn config shape, rename config keys, add required
sections, change defaults, or tell operators to edit server config as an unreviewed workaround.
Config evolution MUST be additive and backward-compatible whenever practical. If a config change
cannot stay backward-compatible, the feature MUST include a compatibility fixture for the previous
config, an operator-visible migration-needed diagnostic, exact migration steps, rollback/fallback
steps to the last trusted config, and evidence that the server launch path fails safely instead of
claiming healthy status.

### VI. Spec Kit First For Non-Trivial Work

New tools, major refactors, service splits, workflow changes, doc-governance changes, and
high-risk operational changes MUST use Spec Kit. Destructive or setup-invalidating changes MUST
also use Spec Kit. The required path is `spec.md`, then `plan.md`, then `tasks.md`, then
implementation, then the explicit docs gate.

### VII. Resource Economy, Robustness, And Durable Lessons

Operational tools MUST be designed for low-spec local machines by default. Plans for performance-,
reliability-, or safety-sensitive work MUST state concrete resource goals for CPU, memory, disk,
network, concurrency, queues, polling, and log volume when those resources can constrain operation.
Implementations MUST prefer bounded work queues, bounded concurrency, compact durable state,
coalesced or rate-limited warnings, and idle waits over busy loops or unbounded accumulation.
Economy MUST NOT justify weaker correctness, degraded performance, delayed safety actions, lossy
recovery, missing observability, or reduced documentation quality; any tradeoff between cost,
latency, throughput, safety, robustness, and documentation completeness MUST be explicit in the spec
or plan. Documentation economy means concise durable evidence, not undocumented decisions.
Microservice architecture in this repo means explicit ownership boundaries first. Additional OS
processes, public services, or dependencies require evidence that they improve isolation,
robustness, or operator control more than they increase overhead. Incident lessons MUST be preserved
in tests, operator docs, code comments, or governance docs before the feature closes.

### VIII. Active Human-Safety Freeze For Suppressor MVP

When an active feature is declared human-safety-critical by the human owner, repo work MUST route
only to that feature and the minimum direct enablers needed to make it safe. During the active
`specs/001-real-time-suppression/` freeze, agents MUST NOT start or continue unrelated `biblio`,
workflow-polish, broad docs, refactor, or new-feature work unless the human owner explicitly releases
the freeze or the work is required to make the suppressor daemon run safely. The MVP target is a
minimal, stable, server-runnable suppressor daemon that automatically hides eligible watched edits,
keeps the live path independent from slower work, performs automatic recovery/reconciliation and
nightly fallback checks, reports non-healthy status truthfully, and can be verified through the
actual launch path. Architecture experiments, large rewrites, new services, cosmetic TUI work, and
non-essential optimization MUST wait until that MVP is stable. Token and time economy are mandatory:
agents MUST use narrow context, small patches, and the shortest meaningful tests, but MUST NOT skip
critical daemon, recovery, reconciliation, or safety verification.

### IX. Public-Repo Privacy For Sensitive Edit Evidence

This repository is public. Work that involves hiding, suppressing, reverting, moderating, or
otherwise protecting sensitive wiki edits MUST NOT commit real personal or incident-identifying
details about those edits to tracked repository artifacts. Prohibited tracked evidence includes real
editor account names, IPs, page titles, revision IDs, diff URLs, comments, timestamps, screenshots,
log excerpts, or text snippets when those details identify how a real person edited a sensitive page
or article. Tests, contracts, fixtures, docs, code comments, and examples MUST use synthetic titles,
synthetic actor names, synthetic revision IDs, synthetic URLs, aggregate counts, outcome classes, or
redacted placeholders instead. Operator-only diagnostics may use the minimum real identifiers needed
to protect an exposed edit during live operation, but those identifiers MUST stay out of Git history
and public issue/task/doc/code surfaces unless the human owner explicitly approves a specific
public-safe exception before it is written. If an agent discovers real sensitive-edit identifiers in
tracked files, it MUST stop expanding that evidence, replace it with synthetic or redacted material,
and treat the cleanup as safety work before release trust.

## Language And Deployment Policy

- Python is the default language for smaller and faster-turnaround wiki automation.
- Rust is preferred for performance-sensitive, reliability-sensitive, or safety-sensitive services.
- Cross-language reuse SHOULD default to shared contracts, schemas, or process boundaries before
  shared embedded libraries.
- Public network services are not the default goal for this repo.
- Projects SHOULD remain separately packageable and separately runnable where that improves failure
  isolation or operator control.
- Resource-sensitive local tools SHOULD stay single-process unless a separate process gives a clear
  failure-isolation or operator-control benefit that is worth its runtime cost.
- New dependencies, services, or long-running processes MUST justify their resource cost, new
  failure modes, and operator burden in the feature plan.

## Workflow And Quality Gates

- Use the global `specify` CLI for installation and upgrades, and use `.specify/` plus `specs/`
  for repo-local workflow state.
- Spec Kit provides the structure; Codex or other LLM tools may draft, analyze, or implement
  within that structure, but they do not establish product intent on their own.
- Close non-trivial work with `make docs`, `python3 tools/doc_workflow.py all`, or
  `/speckit.docs`.
- Managed docs MUST be covered by `.specify/doc-registry.json`.
- Managed-doc frontmatter is machine-controlled. If review state or purpose changes, update the
  registry instead of hand-editing the Markdown metadata.
- Docs-maintenance runs and feature-generation runs are separate write surfaces. Use preview/scope
  controls for broad metadata sync, and require an explicit overwrite action before replacing a
  filled artifact such as `plan.md`.
- Feature generation, docs maintenance, schema/state/config migrations, CLI/report-surface
  rewrites, and broad refactors MUST use an inspectable scope, preview, or dry-run whenever
  practical before mutation.
- When standing-governance review produces unresolved follow-up, move it into
  `specs/000-repo-governance/research.md` or a new scoped feature instead of leaving inline TODO
  markers in maintained governance docs.
- Repo policy changes MUST update `README.md`, this constitution, and the standing governance spec
  where relevant.
- When vision, acceptance criteria, or review requirements are unclear enough to risk wrong work,
  the human owner MUST be asked directly instead of letting the docs drift on assumption.
- When a change can invalidate previous setups, stored state, schemas, configs, operator surfaces,
  authoritative launch paths, or other established workflows, the spec and plan MUST state the
  compatibility strategy, migration steps, fallback or rollback path, required human approval
  point, and any operator-visible prompt or diagnostic before implementation begins.
- Config changes are human-reviewed product decisions. Any change to tracked config files, config
  schema, defaults, environment variable names, config loading semantics, or deployment-required
  config sections MUST state its motivation, compatibility effect, review evidence, migration
  requirements, rollback/fallback path, and deployment verification before production readiness is
  claimed.
- Generated text is proposal text until human-reviewed. Stable decisions MUST be fixed in code,
  tests, governance docs, or explicit comments that preserve lessons learned.
- Incident lessons involving sensitive edits MUST be preserved only with synthetic fixtures,
  redacted placeholders, aggregate counts, and non-identifying outcome classes. Real editor names,
  page titles, revision IDs, diff URLs, comments, screenshots, or log excerpts that identify a real
  sensitive edit MUST NOT be committed.
- When durable lessons are lifted from a feature or review, maintainers SHOULD preserve a light
  trace to the originating feature or decision when that materially helps later audit or git
  history lookup.
- Production-readiness claims MUST be backed by strong automated coverage plus manual verification.
- Safety-, reliability-, or performance-sensitive specs and plans MUST include resource goals,
  bounded concurrency/state/logging decisions, recovery/status behavior, and test or benchmark
  evidence scaled to the risk.
- Task lists SHOULD include compatibility fixtures, migration verification, rollback/fallback
  checks, and setup-preservation checks whenever prior setups or machine-readable surfaces are at
  risk.
- Implementation task lists SHOULD include low-spec verification whenever CPU, memory, disk,
  network, or queue growth could affect correctness, latency, or operator trust.
- Incident fixes MUST capture the lesson in tests, docs, or narrowly useful comments so the repo
  does not rely on chat history to remember why the fix exists.
- Documentation work MAY be terse, but it MUST preserve enough context, evidence, and lessons for a
  future maintainer or operator to repeat the decision without depending on chat history.
- Tooling, logging, metrics, tests, docs, examples, and release evidence MUST avoid secrets,
  sensitive payloads, hidden text, and real sensitive-edit incident identifiers.
- Operator surfaces, CLIs, and Makefiles SHOULD stay small, well-described, and layered. Prefer a
  few clear entrypoints over long flat command lists that only make sense after rereading docs.
- If a human-safety freeze is active, `.specify/feature.json` MUST point at the active safety feature
  or be ignored in favor of the explicit human instruction. Any conflicting active feature pointer
  MUST be corrected before planning or implementation continues.
- During the active suppressor MVP freeze, production-readiness claims MUST mean the daemon has been
  verified on the actual launch path for automatic live hiding, recovery/reconciliation, nightly
  fallback, truthful non-healthy status, bounded failure behavior, and the minimum test evidence
  required by `specs/001-real-time-suppression/quickstart.md`.

## Governance

This constitution supersedes conflicting repo process guidance.

Amendment rules:

- update the constitution
- update `specs/000-repo-governance/` as needed
- update affected templates or workflow guidance when the principle changes how work is planned,
  specified, or task-tracked
- update affected README or project docs
- run the explicit docs gate

Versioning policy:

- MAJOR: incompatible governance change or principle removal/redefinition
- MINOR: new principle or materially expanded requirement
- PATCH: clarifications and wording-only improvements

Compliance review expectations:

- significant reviews SHOULD check constitution compliance
- if work intentionally violates a principle, the spec and plan MUST justify it explicitly

**Version**: 1.9.0 | **Ratified**: 2026-04-18 | **Last Amended**: 2026-05-07
