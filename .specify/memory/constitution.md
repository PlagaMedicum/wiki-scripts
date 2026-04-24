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
Version change: 1.3.0 -> 1.4.0
Modified principles:
- IV. Deterministic Documentation And Honest Status -> IV. Deterministic Documentation, Safe Writes, And Honest Status
- Workflow And Quality Gates (expanded guidance only)
Added sections:
- None
Removed sections:
- None
Templates requiring updates:
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/tasks-template.md
- ✅ README.md
- ✅ specs/000-repo-governance/spec.md
- ✅ specs/000-repo-governance/plan.md
- ✅ specs/000-repo-governance/quickstart.md
- ✅ .specify/extensions/docs/README.md
- ✅ .specify/extensions/docs/commands/speckit.docs.md
- ⚠ `.specify/templates/commands/*.md` is not present in this repo; repo-local command guidance was checked in `.specify/extensions/docs/commands/` instead
Follow-up TODOs:
- None
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
artifacts unless an explicit overwrite action is requested. Docs MUST distinguish current behavior
from future direction.

### V. Spec Kit First For Non-Trivial Work

New tools, major refactors, service splits, workflow changes, doc-governance changes, and
high-risk operational changes MUST use Spec Kit. The required path is `spec.md`, then `plan.md`,
then `tasks.md`, then implementation, then the explicit docs gate.

## Language And Deployment Policy

- Python is the default language for smaller and faster-turnaround wiki automation.
- Rust is preferred for performance-sensitive, reliability-sensitive, or safety-sensitive services.
- Cross-language reuse SHOULD default to shared contracts, schemas, or process boundaries before
  shared embedded libraries.
- Public network services are not the default goal for this repo.
- Projects SHOULD remain separately packageable and separately runnable where that improves failure
  isolation or operator control.

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
- When standing-governance review produces unresolved follow-up, move it into
  `specs/000-repo-governance/research.md` or a new scoped feature instead of leaving inline TODO
  markers in maintained governance docs.
- Repo policy changes MUST update `README.md`, this constitution, and the standing governance spec
  where relevant.
- When vision, acceptance criteria, or review requirements are unclear enough to risk wrong work,
  the human owner MUST be asked directly instead of letting the docs drift on assumption.
- Generated text is proposal text until human-reviewed. Stable decisions MUST be fixed in code,
  tests, governance docs, or explicit comments that preserve lessons learned.
- When durable lessons are lifted from a feature or review, maintainers SHOULD preserve a light
  trace to the originating feature or decision when that materially helps later audit or git
  history lookup.
- Production-readiness claims MUST be backed by strong automated coverage plus manual verification.
- Tooling, logging, and metrics MUST avoid secrets and sensitive payloads.
- Operator surfaces, CLIs, and Makefiles SHOULD stay small, well-described, and layered. Prefer a
  few clear entrypoints over long flat command lists that only make sense after rereading docs.

## Governance

This constitution supersedes conflicting repo process guidance.

Amendment rules:

- update the constitution
- update `specs/000-repo-governance/` as needed
- update affected README or project docs
- run the explicit docs gate

Versioning policy:

- MAJOR: incompatible governance change or principle removal/redefinition
- MINOR: new principle or materially expanded requirement
- PATCH: clarifications and wording-only improvements

Compliance review expectations:

- significant reviews SHOULD check constitution compliance
- if work intentionally violates a principle, the spec and plan MUST justify it explicitly

**Version**: 1.4.0 | **Ratified**: 2026-04-18 | **Last Amended**: 2026-04-20
