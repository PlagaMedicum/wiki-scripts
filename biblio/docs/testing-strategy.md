# Biblio Testing Strategy

<!-- DOCMETA:START -->
> Status: maintained
> Review: code-reviewed
> Purpose: Current biblio testing strategy and coverage shape.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

## Test Layers

### Core Logic

- text normalization and extraction
- source loading and validation
- replacement logic
- state serialization

### Boundary Tests

- bootstrap and auth setup
- runtime wiki client behavior
- page analysis and page save flow
- workflow orchestration
- source-management flow

### Operator-Facing Tests

- CLI output
- startup flow
- source-management UX

## Strongest Coverage

`biblio` is strongest where the logic is deterministic:

- source parsing
- normalization and extraction
- replacement behavior
- save-path policy
- operator workflow flow control

## Known Gaps

- no regular live-wiki CI coverage
- no full real-TUI automation
- no strong performance guarantees across large source sets

## Testing Rule

Add or update tests whenever a change affects:

- source loading
- matching logic
- save policy
- operator prompts or destructive-action flow
- state-persistence behavior
