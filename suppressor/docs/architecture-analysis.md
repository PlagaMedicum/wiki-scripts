# Architecture Analysis and Proposals

This is a blunt review of the current `suppressor` structure. It now mixes historical critique with the remaining architecture debt that still matters as the crate grows.

## Findings

1. `src/app.rs` was a god module. That specific problem has already been fixed, so this doc should be read as historical context plus remaining pressure, not as a live file-level indictment.
2. The configuration model is clearer than before: non-secret wiki defaults live in `config.toml`, auth env names are configurable, and env overrides still exist for deployment-specific overrides. It is workable, but the rules are still more complicated than they should be.
3. The TUI is now correctly framed as a supervisory client, but the docs still need to keep that relationship obvious because `run`, `tui`, and the signal targets are easy to confuse.
4. The Makefile is better than before, but it should stay a boring front door, not a cargo wrapper zoo.
5. The cache boundary is better than before: policy lives in `cache/store.rs`, fetch execution lives in `cache/source.rs`, and reconciliation passes use the narrower `ReconcilePassContext`. The remaining risk is regression if new code starts bypassing those seams.
6. The current design is still biased toward one daemon, one source page, one cache, and one operational workflow. That is acceptable for v1, but future expansion would become messy if the boundaries are not tightened now.

## Risks

- New functionality can still blur back into wide shared runtime structs unless new behavior is forced through the narrower runtime-specific seams.
- The custom config and `.env` handling will drift if another runtime input source gets added without a single documented policy for secrets versus non-secrets.
- Operator behavior is too dependent on undocumented conventions like "config lives next to the binary" and "state is local mutable machine state."
- The repository can easily drift into a pile of command aliases if the Makefile is allowed to keep growing instead of staying a small front door.

## Proposals

1. Split the application into clear layers:
   - command parsing and entrypoint
   - daemon bootstrap and runtime assembly
   - stream ingestion
   - reconciliation scheduler
   - revisiondelete worker
   - TUI control client

2. Treat state explicitly by category:
   - durable operational state
   - derived cache state
   - ephemeral locks and coordination
   - operator inputs

3. Keep the project docs navigable from one landing page:
   - README for orientation
   - docs index for doc discovery
   - implementation spec for behavior
   - operations spec for deployment and runtime

4. Keep the Makefile boring:
   - one target for common operator actions
   - one target for config checks
   - one target for each normal cargo workflow
   - no alias clutter, no fake abstractions, no cargo wrapper zoo

5. If the crate grows again, extract a dedicated `runtime` or `daemon` module before adding new feature branches to `app.rs`.
6. Keep cache policy and cache shaping separate. That split is already in place and should not regress.
7. Keep reconciliation on the narrower per-pass context and do not let behavior drift back into the broad runtime bag.
8. Keep `cache/store.rs` as policy and orchestration, and keep `cache/source.rs` as the remote fetch execution layer.

## Conclusion

Nothing here is broken enough to justify a rewrite. The problem is structural debt: the project is coherent today, but only just. The current cleanup should make the project easier to extend without turning it into a monolith of hand-wired behavior.

Next document: [Runtime boundaries](runtime-boundaries.md)
