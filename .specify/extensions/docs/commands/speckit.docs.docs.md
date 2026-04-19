---
description: "Run the repo's explicit docs workflow gate"
---

# Run Docs Workflow

Run the repo-local deterministic docs gate.

## Behavior

This command runs the same final gate as `make docs`:

1. sync managed doc metadata
2. lint managed doc metadata
3. run docs-tool tests
4. print deterministic doc status categories

## Execution

- **Bash**: `.specify/scripts/bash/run-doc-workflow.sh`

## Notes

- This command is explicit. It is not auto-executed as a mutating hook.
- Use it at the end of non-trivial work after `spec.md`, `plan.md`, `tasks.md`, and implementation.
