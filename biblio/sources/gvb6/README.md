# `gvb6`

This source targets Т. 6, кн. 2. Магілёўская вобласць bibliography references on be.wikipedia.org.

## Navigation

- [Project README](../../README.md)
- [Documentation index](../../docs/README.md)
- [Architecture overview](../../docs/architecture.md)
- [Architecture review](../../docs/architecture-review.md)

## Search Terms

- Insource terms: Магілёўская вобласць
- ISBNs: 978-985-11-0440-2
- Keywords: none

## Replacement Forms

- Without pages: `{{Крыніцы/ГВБ|6-2|{entry}}}`
- With pages: `{{Крыніцы/ГВБ|6-2|{entry}|{pages}}}`

## Candidate Detection

- Must contain all: Магілёўская вобласць
- Must contain any: Т. 6, кн. 2. Магілёўская вобласць, 978-985-11-0440-2

## Default Edit Summary

- `Замена бібліяграфічнай спасылкі шаблонам {{Крыніцы/ГВБ}}`

## Notes

- Add bibliography-specific macros in `source.toml` under `[macros]`.
- Add broad regex rules in `[[regex_rules]]`.
- `rules.json`, `review_variants.json`, and `ignored_variants.json` are managed by the workflow.
