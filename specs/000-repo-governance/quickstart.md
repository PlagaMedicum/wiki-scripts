---
docmeta:
  status: maintained
  review: client-input-derived,reviewed and commented
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
2. Create or update a feature directory under `specs/NNN-feature-name/`.
3. Write `spec.md`, then `plan.md`, then `tasks.md`. If direct human answers or comments are still
   needed, keep them in feature-local files such as `questions.md` or `review-queue.md`.
   <!-- todo: to not duplicate document logic and use only the research docs.  -->
   If the unresolved point is repo-level governance rather than feature-scoped work, move it into
   `specs/000-repo-governance/research.md`.
4. Implement the change.
5. Check the current docs queue when you need to see pending approval, manual review, answer, or
   update work:

```bash
python3 tools/doc_workflow.py status
```

   Read the active feature's `questions.md` and `review-queue.md` alongside that output when the
   feature is still in flight.

6. Close the work with the explicit docs gate:

```bash
make docs
```

Equivalent direct commands:

```bash
python3 tools/doc_workflow.py all
# or, inside the Spec Kit command layer:
/speckit.docs
```

7. Once the durable lessons are fixed elsewhere, close the feature by removing
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

## Repo-Local Refresh

Refresh the local Spec Kit scaffolding only when you intentionally want to update repo-local Spec
Kit files:

```bash
specify init --here --force --integration codex --script sh
```

Review that diff carefully before keeping it.
