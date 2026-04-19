# Deterministic Docs Workflow Extension

This local extension exposes one explicit command:

- `speckit.docs.docs`

It runs the same repo-local final gate as `make docs` and `python3 tools/doc_workflow.py all`.

The command is intentionally explicit. It is not configured as an automatic mutating hook.
