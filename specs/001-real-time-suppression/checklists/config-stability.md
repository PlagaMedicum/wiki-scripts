---
docmeta:
  status: draft
  review: feature-local
  purpose: Requirements-quality checklist for human-reviewed suppressor config stability.
  source: speckit-checklist on 2026-05-06
---

# Config Stability Checklist: Real-Time Suppression Recovery


## Requirement Completeness

- [x] CHK001 Are all config-affecting surfaces named as requirements inputs: tracked config files, schema, defaults, environment variable names, loading semantics, and deployment-required sections? [Completeness, Plan §Config Change Review, Contract §Config Stability Contract]
- [x] CHK002 Are requirements defined for treating config as a human-reviewed operator contract rather than an implementation detail? [Completeness, Constitution §V, Research §Config Contract]
- [x] CHK003 Are requirements defined for the target-host `missing field realtime` failure as a release-blocking config-compatibility gate? [Completeness, Plan §Config Change Review, Quickstart §Config Stability And Human Review Gate]
- [x] CHK004 Are requirements defined for recording reviewed config baseline or documented deployment divergence before launch evidence is accepted? [Completeness, Tasks §T039, Data Model §ConfigReviewEvidence]
- [x] CHK005 Are requirements defined for preserving the current config layout additively where practical instead of forcing section renames or ad-hoc migrations? [Completeness, Plan §Compatibility/Migration, Research §Preserve current config surfaces]

## Requirement Clarity

- [x] CHK006 Is "human review evidence" specific enough to require an explicit review reference or approval note before production trust? [Clarity, Data Model §ConfigReviewEvidence, Tasks §T039]
- [x] CHK007 Is "no background config edit" clearly stated for both tracked config and target-host config surfaces? [Clarity, Plan §Config Change Review, Tasks §Guardrails]
- [x] CHK008 Is the acceptable `print-effective-config` evidence defined as non-secret output or an exact config/migration-needed diagnostic? [Clarity, Quickstart §Config Stability And Human Review Gate, Contract §Print config]
- [x] CHK009 Is the difference between backward-compatible loading and migration-needed diagnostic explicitly defined for missing or incompatible config? [Clarity, Contract §Config Stability Contract, Data Model §ConfigReviewEvidence]
- [x] CHK010 Are rollback and fallback expectations specific enough to identify the last trusted config or launch workflow? [Clarity, Quickstart §Deployment Go/No-Go And Rollback Gate, Data Model §ConfigReviewEvidence]

## Requirement Consistency

- [x] CHK011 Are config-stability requirements consistent across constitution, plan, research, command contract, quickstart, data model, and tasks? [Consistency, Constitution §V, Plan §Config Change Review, Tasks §T039]
- [x] CHK012 Are `server-start` requirements consistent with config-stability requirements so launch trust cannot bypass T039? [Consistency, Quickstart §Detached Server Start Check, Tasks §T039-T040]
- [x] CHK013 Are print-config requirements consistent with the no-secrets rule and the no-unreviewed-normalization rule? [Consistency, Contract §Print config, Plan §Constraints]
- [x] CHK014 Are config-migration requirements consistent with existing compatibility requirements for status/report surfaces and launch paths? [Consistency, Spec §FR-027..FR-029, Plan §Compatibility/Migration]
- [x] CHK015 Are docs and task references consistent after renumbering config stability to T039, launch to T040, smoke to T041, and resource evidence to T042? [Consistency, Tasks §Phase 6, Quickstart §Current MVP Go/No-Go]

## Acceptance Criteria Quality

- [x] CHK016 Can config-stability acceptance be objectively determined from documented baseline or divergence, non-secret effective-config output, human review evidence, compatibility verdict, and rollback/fallback path? [Measurability, Quickstart §Config Stability And Human Review Gate]
- [x] CHK017 Are release-blocking conditions measurable for unreviewed required config sections, config migration failure, or missing config diagnostics? [Acceptance Criteria, Quickstart §Deployment Go/No-Go And Rollback Gate]
- [x] CHK018 Are config-review evidence fields measurable enough to distinguish `unchanged`, `backward-compatible`, `migration-needed`, and `blocked` outcomes? [Measurability, Data Model §ConfigReviewEvidence]
- [x] CHK019 Are criteria clear that `server-start` success evidence is invalid when config was edited in the background or lacks documented rollback/fallback? [Acceptance Criteria, Plan §Phase 4, Quickstart §Detached Server Start Check]

## Scenario Coverage

- [x] CHK020 Are primary, alternate, exception, and recovery scenarios covered for matching reviewed config, documented deployment divergence, missing required config, and incompatible target-host config? [Coverage, Quickstart §Config Stability And Human Review Gate]
- [x] CHK021 Are scenarios covered for both reviewed migration and reviewed safe failure without migration, instead of assuming one universal fix? [Coverage, Research §Config Contract, Contract §Config Stability Contract]
- [x] CHK022 Are requirements defined for older config shapes without allowing false healthy daemon status? [Coverage, Plan §Config Change Review, Spec §SC-016]
- [x] CHK023 Are requirements defined for config-affecting docs changes as release-contract changes even when no Rust code changes occur? [Coverage, Quickstart §Evidence Freshness And Expiry]

## Dependencies & Assumptions

- [x] CHK024 Are dependencies on operator-controlled secrets separated from config-review evidence so `.env` values are never captured in requirements evidence? [Dependency, Spec §Assumptions, Quickstart §Config Stability And Human Review Gate]
- [x] CHK025 Are target-host assumptions documented for config path, deployment directory, writable state paths, and authoritative launch path without assuming systemd or shell backgrounding? [Dependency, Quickstart §Target Server Environment Assumptions]
- [x] CHK026 Are governance dependencies explicit so future config changes route through constitution v1.8.0 and not only through feature-local prose? [Dependency, Constitution §V, Plan §Constitution Check]

## Ambiguities & Conflicts

- [x] CHK027 Is the rejected shortcut of patching server `config.toml` clearly documented as outside requirements unless human-reviewed migration evidence exists? [Ambiguity, Research §Config Contract, Quickstart §Config Stability And Human Review Gate]
- [x] CHK028 Are config-stability requirements free of a conflict between "stability" and necessary safety-driven config evolution by allowing reviewed, motivated, compatible or migrated changes? [Conflict, Research §Config Contract, Constitution §V]

## Notes

- These checklist items validate requirement quality, not implementation behavior.
- Focus areas: config-change motivation, human review, compatibility or migration diagnostics,
  target-host `missing field realtime`, no background config edits, and deployment trust gates.
- Depth: standard release-gate requirements review for the active suppressor MVP freeze.
- Actor/timing: author and reviewer before implementation proceeds from T039 to T040.
