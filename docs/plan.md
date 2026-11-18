# Repository Maintenance Plan

_AI-assisted review. This file owns the work record and pending work; project
documentation owns current behavior. Earlier implementation proposals are
superseded by this record._

## Review Findings

1. **Suppressor restructuring lacks a demonstrated need.** `suppressor/Cargo.toml`
   already defines a workspace containing the binary and `core`. The earlier
   six-crate target and daemon extraction tasks describe a possible design, not
   evidence of a protection defect or measured operational improvement. Do not
   continue that migration merely to finish the plan.
2. **Biblio's planned boundary partly duplicates an existing safeguard.**
   `biblio/.importlinter` already forbids source-management controllers from
   importing workflow, runner, or page execution. BBA-002's import-isolation
   acceptance condition therefore does not establish a missing capability.
   Additional interfaces or UI protocols need a concrete failing use case.
3. **Size is a maintenance signal, not deletion evidence.** Large source and test
   modules exist in both projects. Some Rust modules contain inline tests, so
   total file length is not production-code size. This setup review did not
   establish dead code, redundant behavioral coverage, or safe deletion candidates.
4. **Existing tools already own the checks.** Root `Makefile` delegates to each
   project; project gates own formatting, lint, tests, dependency audit, and
   Python import contracts. No replacement framework or additional gate is needed
   for these responsibilities.

## Current Scope

The deployed suppressor is reported working. This review makes no claim about
current server health or deployed artifact identity and authorizes no deployment.
Preserve its backend, protection semantics, configuration, state, launch paths,
and existing tests. A backend rebuild is not scheduled.

Keep the existing project documentation and quality gates. Do not reduce coverage
or remove dependencies from counts alone. Protected agent instructions and
untracked local files are outside this cleanup.

## Completed

### Agentic-bot Integration

Publication requires interactive terminal confirmation and a pending or approved
proposal; unresolved conflict markers and failed rebases block publication. Wiki
authentication is in-memory and isolated from repository credential files.
Regression tests cover the publication gate, merge failures, and synthetic
authentication. The sanitized snapshot was published to `main` under explicit
operator authorization.

## Pending Work

### Biblio: Multi-source Proposals

Goal: replace plain, book-template, and other bibliographic forms with their
publication-specific templates. Generate rule-based proposals for operator review;
do not save wiki edits or promote approvals during preparation.

1. Reuse the existing local source catalog, including per-volume rules and review
   variants. Inspect several real publication templates and source citations;
   identify editions, article titles, authors, pages, links, and anchors.
2. Add source-specific matching rules to the existing local `sources/` owner.
   Exercise positive examples and negative cases for missing or conflicting
   metadata, protected text, and references with links or custom anchors. Keep
   uncertain mappings review-required; do not hide lost information.
3. Run small anonymous read-only previews against live revisions, respecting rate
   limits. Record concrete matches and rejected forms; search hits are not edits.
4. Preserve existing state and per-volume boundaries. The merged BelEn source does
   not currently load legacy per-volume state, and historical approvals must not be
   silently promoted into new automated saves. Do not migrate or overwrite state.

Current source work: add `belarusian-language-1994`, `music-dictionary-1990`,
and `myths-1992-volume2` using the existing `source.toml` mechanism. Match
reviewed structured-article, plain-text, and book-template forms respectively;
preserve entry/page values, require manual review, and reject added metadata or
conflicting editions. Keep local sources Git-ignored and track isolated test
fixtures. Run representative source tests and bounded live previews before
claiming coverage. Existing merged/legacy state is not changed.

Completion: tested reusable rules for supported publications and observed
reviewable proposals; report coverage, untested cases, and local-only files.
Existing per-volume state, credentials, other projects, and wiki pages remain
untouched.

### Biblio Citation Safety

Duplicate-parameter safety: the existing parser collapses repeated names, so
`engine._preserves_book_citation` now declines candidates when parameter counts
are ambiguous or collapsed. Existing safety cases share one citation fixture;
their assertions remain. A duplicate-parameter case failed before the repair.
Afterward 205 Biblio tests, Ruff, and both import contracts passed.

Completed: `engine.replace_text()` now declines candidate units overlapping
protected comment or literal/code regions, including short-reference updates.
For `Кніга`/`book` inputs, it also declines conversions with unsupported nonempty
parameters, surrounding text, or a year conflicting with a configured short-ref
year. Custom anchors are retained unless matching active short references can be
retargeted for manual review.

Regression evidence: 203 Biblio tests passed, including the original failures,
normal concrete-template conversions, and save/review tests; Ruff and both import
contracts passed. No live wiki edits were made. Aggregate `make check` and the
dependency audit were not run: the former synchronizes dependencies and the latter
may need network access.

Limit: these guards do not establish equivalence of all publication fields, nor do
they establish that arbitrary free-text citations or other citation templates are
lossless. Source definitions and edit diffs still require review. Further
generalization needs its own evidence and plan.

Deferred: search broadening, catalog migration, TemplateData integration, fuzzy
matching, and parser/framework replacement.

### Previously Parked Work

| ID | Disposition | Evidence needed before implementation |
| --- | --- | --- |
| SBA-002 | Parked; initial workspace slices exist | A concrete dependency problem that the current binary/core boundary cannot address locally. |
| SBA-003 | Parked | A specific daemon maintenance failure or defect, with the smallest extraction justified against a direct fix. |
| SBA-004 | Parked | Proven duplicate runtime behavior and contract coverage before replacing either path. |
| BBA-002 | Parked; import isolation already enforced | A source-management use case that existing models and boundaries cannot support directly. |
| BBA-003 | Parked | A demonstrated UI/backend coupling problem; preserve prompts, approvals, cancellation, and output if changing the interface. |
| DEP-001 | Conditional release work, not a rollout request | Separately authorized daemon-critical changes and target-host verification under the existing operations/testing documentation. |
| DEP-002 | Conditional compatibility work | An actual configuration schema/default change, with compatibility tests and migration/rollback evidence. |
| MSA-001 | Not scheduled | A demonstrated process-isolation requirement that cannot be met inside the current application. |

For an established problem, replace the relevant parked entry with a bounded plan:
name the owning files/functions, smallest change, preserved contracts, focused
verification, and completion condition. Do not add abstractions or tests solely
to satisfy a former architecture target.

## Completed Record

Historical task IDs remain reserved; the table below is the summary record.

| IDs | Completed scope |
| --- | --- |
| RCP-001–004 | Central planning and documentation consolidation. |
| RCP-005 | Documentation contracts deduplicated; required config shown in README and root help; existing checks and runtime behavior preserved. |
| QAG-001–003 | Existing quality gates and dependency review. |
| SBA-001 | Earlier workspace design recorded; it is not authorization for further migration. |
| BBA-001 | Python import contracts installed. |

## Review Evidence

Reviewed the root entry points and plan, project READMEs, Makefiles, dependency
manifests, Biblio import contracts and architecture/testing documentation, and
Suppressor runtime-boundary/testing documentation. No production code, test,
dependency, quality gate, or deployment change is part of this review.

RCP-005 verification: local documentation links and test-module references checked;
root/project help and root-to-suppressor config forwarding observed (dry-run only).
Installed Biblio checks passed: 190 tests, Ruff lint/format, and both import
contracts. No dependency synchronization, audit, aggregate `make check`, Suppressor
test suite, or deployment verification was run for this documentation/help cleanup.

This is a setup/documentation review, not a behavioral code audit. Runtime
correctness, test redundancy, dependency necessity, and live deployment health
remain unproven by it.
