---
docmeta:
  status: maintained
  review:
  - client-input-derived
  - approved
  purpose: Practical Spec Kit workflow for this repo, including the explicit docs gate.
  source: .specify/doc-registry.json
---

# Spec Kit Workflow Quickstart


## One-Time Setup

Install and verify the global CLI:

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.7.3
specify version
specify check
```

## Normal Flow For Non-Trivial Changes

1. Read `README.md`, `.specify/memory/constitution.md`, and this governance stack.
2. If an active human-safety freeze exists, confirm `.specify/feature.json` points at that feature
   and do not start unrelated work. The current freeze points at
   `specs/001-real-time-suppression/` and restricts work to suppressor MVP stabilization until the
   human owner releases it.
3. Create or update a feature directory under `specs/NNN-feature-name/`.
4. Write `spec.md`, then `plan.md`, then `tasks.md`. If direct human answers or comments are still
   needed, keep them in feature-local files such as `questions.md` or `review-queue.md`.
   If the unresolved point is repo-level governance rather than feature-scoped work, move it into
   `specs/000-repo-governance/research.md`.
   If the change can invalidate previous setups, schemas, configs, state files, machine-readable
   surfaces, or authoritative launch paths, document the compatibility strategy, migration steps,
   fallback/rollback, and the required human approval point before implementation.
   If the change touches tracked config files, config schema, defaults, environment variable names,
   loading semantics, or deployment-required config sections, document the concrete motivation,
   explicit human review evidence, compatibility or migration behavior, rollback/fallback, and
   deployment-path verification before trusting it on a server.
   For safety-, reliability-, or performance-sensitive work, state resource goals, bounded
   concurrency/state/logging, recovery/status behavior, low-spec verification, and how incident
   lessons will be preserved.
5. Implement the change.
6. Check the current docs queue when you need to see pending approval, manual review, answer, or
   update work:

```bash
python3 tools/doc_workflow.py status
```

   Read the active feature's `questions.md` and `review-queue.md` alongside that output when the
   feature is still in flight.

7. Close the work with the explicit docs gate:

```bash
make docs
```

Equivalent direct commands:

```bash
python3 tools/doc_workflow.py all
# or, inside the Spec Kit command layer:
/speckit.docs
```

8. Once the durable lessons are fixed elsewhere, close the feature by removing
   `.specify/feature.json` and deleting the finished `specs/NNN-feature-name/` directory unless the
   directory still carries active context. Git history remains the archive.

## Brownfield Notes

- The repo may contain unrelated uncommitted work. Do not reset or drop it unless explicitly
  intended.
- Some upstream helper scripts expect a feature branch like `001-feature-name`. If you stay on
  `main`, those helpers can refuse to run even when the `specs/` directory exists.
- The feature directory remains the durable source of truth for scoped work even when a helper
  script is skipped.
- When no non-trivial feature is active, `.specify/feature.json` may be absent.
- If a question needs a direct human answer, keep it in the feature directory instead of leaving it
  only in chat history.
- Do not hand-edit managed review labels in Markdown frontmatter. Change
  `.specify/doc-registry.json` and run the docs gate instead.
- Do not leave unresolved inline TODO-style review comments inside maintained governance docs once
  that follow-up has been captured in `research.md` or a scoped feature surface.
- Feature-local workflow docs are not registry-managed; keep their local metadata/status schema
  consistent instead of inventing a second header system for them.
- When durable lessons from a feature or review are folded into maintained docs, keep a light trace
  to the originating feature or decision when it will materially help later audit or git history.
- Do not trade away correctness, recovery, or operator-visible status for resource economy. Make any
  cost, latency, throughput, safety, robustness, or documentation tradeoff explicit in the active
  spec or plan.
- Do not execute destructive edits, broad rewrites, setup-breaking refactors, or incompatible
  schema/state/surface changes on assumption. Get explicit human approval and record the migration
  path first.
- Do not make config churn in the background. Config edits, schema/default changes, environment
  variable changes, and new required server config sections need a documented reason, explicit
  human review, compatibility or migration evidence, and rollback/fallback notes before production
  trust.

## Repo-Local Refresh

Refresh the local Spec Kit scaffolding only when you intentionally want to update repo-local Spec
Kit files:

```bash
specify init --here --force --integration codex --script sh
```

Review that diff carefully before keeping it.
