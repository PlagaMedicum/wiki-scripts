# `gvb14`

This source targets Т. 9: Гродзенская вобласць, кн. 2 bibliography references on be.wikipedia.org.

## Navigation

- [Project README](../../README.md)
- [Documentation index](../../docs/README.md)
- [Architecture overview](../../docs/architecture.md)
- [Architecture review](../../docs/architecture-review.md)

## Search Terms

- Insource terms: Гродзенская вобласць
- ISBNs: 978-985-11-0908-7
- Keywords: none

## Replacement Forms

- Without pages: `{{Крыніцы/ГВБ|9-2|{entry}}}`
- With pages: `{{Крыніцы/ГВБ|9-2|{entry}|{pages}}}`

## Candidate Detection

- Must contain all: Гродзенская вобласць
- Must contain any: Т. 9: Гродзенская вобласць, кн. 2, 978-985-11-0908-7

## Default Edit Summary

- `Замена бібліяграфічнай спасылкі шаблонам {{Крыніцы/ГВБ}}`

## Notes

- Add bibliography-specific macros in `source.toml` under `[macros]`.
- Add broad regex rules in `[[regex_rules]]`.
- `rules.json`, `review_variants.json`, and `ignored_variants.json` are managed by the workflow.
