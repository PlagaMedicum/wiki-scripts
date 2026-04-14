# Page Save Boundary

This note documents the current edge where page save policy and wiki I/O meet. It is meant to
stay small and practical so the next extraction is easy to review.

## Current Shape

- `page_execution.py` decides whether a changed page should be skipped, prompted, or saved.
- `session.py` keeps the cross-page policy state such as `accept_all` and summary overrides.
- `runtime.py` carries the page-save transport through `PageEdit` and `WikiClient.save_page()`.
- `workflow.py` stays focused on source iteration and page loading.

## Next Extraction

The next helper module should own the actual save path, so `page_execution.py` can stop mixing
policy with transport. A likely name is `page_save.py`, but the exact filename matters less than
the boundary:

- build a page-edit request from policy and analysis
- apply the edit through one explicit wiki I/O helper
- keep the summary/minor/bot flags in one transport shape, with `bot=True` enforced for every save
- leave review and accept-all state in `session.py`

## Why This Matters

The split keeps the save contract easy to test and prevents the page-execution layer from turning
back into a transaction script. The goal is not to add more layers. The goal is to make the save
boundary explicit before another feature depends on it.
