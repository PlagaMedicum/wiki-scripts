# Spec Kit Workflow Quickstart

<!-- DOCMETA:START -->
> Status: maintained
> Review: client-input-derived
> Purpose: Practical Spec Kit workflow for this repo, including the explicit docs gate.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

## One-Time Setup

Install and verify the global CLI:

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.7.3
specify version
specify check
```

## Normal Flow For Non-Trivial Changes

1. Read `README.md`, `.specify/memory/constitution.md`, and this governance stack.
2. Create or update a feature directory under `specs/NNN-feature-name/`.
3. Write `spec.md`, then `plan.md`, then `tasks.md`.
4. Implement the change.
5. Close the work with the explicit docs gate:

```bash
make docs
```

Equivalent direct commands:

```bash
python3 tools/doc_workflow.py all
# or, inside the Spec Kit command layer:
/speckit.docs.docs
```

6. Once the durable lessons are fixed elsewhere, close the feature by removing
   `.specify/feature.json` and deleting or archiving the finished
   `specs/NNN-feature-name/` directory.

## Brownfield Notes

- The repo may contain unrelated uncommitted work. Do not reset or drop it unless explicitly
  intended.
- Some upstream helper scripts expect a feature branch like `001-feature-name`. If you stay on
  `main`, those helpers can refuse to run even when the `specs/` directory exists.
- The feature directory remains the durable source of truth for scoped work even when a helper
  script is skipped.
- When no non-trivial feature is active, `.specify/feature.json` may be absent.
- Do not hand-edit DOCMETA review labels in Markdown. Change `.specify/doc-registry.json` and run
  the docs gate instead.

## Repo-Local Refresh

Refresh the local Spec Kit scaffolding only when you intentionally want to update repo-local Spec
Kit files:

```bash
specify init --here --force --integration codex --script sh
```

Review that diff carefully before keeping it.
