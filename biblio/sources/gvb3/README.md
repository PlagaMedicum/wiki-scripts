# `gvb3`

This source targets Т. 3, кн. 1. Брэсцкая вобласць bibliography references on be.wikipedia.org.

## Navigation

- [Project README](../../README.md)
- [Documentation index](../../docs/README.md)
- [Architecture overview](../../docs/architecture.md)
- [Architecture review](../../docs/architecture-review.md)

## Search Terms

- Insource terms: Брэсцкая вобласць
- ISBNs: 985-11-0373-X
- Keywords: none

## Replacement Forms

- Without pages: `{{Крыніцы/ГВБ|3-1|{entry}}}`
- With pages: `{{Крыніцы/ГВБ|3-1|{entry}|{pages}}}`

## Candidate Detection

- Must contain all: Брэсцкая вобласць
- Must contain any: Т. 3, кн. 1. Брэсцкая вобласць, 985-11-0373-X

## Default Edit Summary

- `Замена бібліяграфічнай спасылкі шаблонам {{Крыніцы/ГВБ}}`

## Notes

- Add bibliography-specific macros in `source.toml` under `[macros]`.
- Add broad regex rules in `[[regex_rules]]`.
- `rules.json`, `review_variants.json`, and `ignored_variants.json` are managed by the workflow.
