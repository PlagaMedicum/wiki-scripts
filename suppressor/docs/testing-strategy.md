---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current suppressor testing strategy and maintained test story.
  source: .specify/doc-registry.json
---

# Suppressor Testing Strategy


## Test Layers

### Unit And Subsystem Tests

- config loading
- auth and right checks
- cache shaping and persistence
- runtime assembly helpers
- queue and worker behavior
- TUI support helpers

### Boundary Tests

- mocked MediaWiki API requests
- config and state persistence

## Strongest Coverage

`suppressor` is strongest at:

- deterministic config handling
- right verification
- API contract checks
- cache/state persistence
- local runtime helper behavior

## Known Gaps

- no full live EventStreams-to-RevDel CI path
- no full real-TUI integration automation
- no broad live-wiki production simulation in CI
- the default full suite currently shows `cache::source::tests::fetch_redirect_target_uses_api_redirect_targets`
  failing while the isolated test and `--test-threads=1` pass, so the current suite should be
  treated as useful coverage, not proof that all parallel or state-sensitive behavior is settled

## Testing Rule

Add or update tests whenever a change affects:

- config or env parsing
- auth or rights expectations
- queueing or retry behavior
- reconciliation logic
- operator control flow
