---
docmeta:
  status: draft
  review: feature-local
  purpose: Human review and maintainer action queue for the active suppressor MVP gate.
  source:
  - speckit-plan human-review queue update on 2026-05-06
  - user approval on 2026-05-07
  - live-hide incident update on 2026-05-07
---

# Review Queue: Real-Time Suppression Recovery


Feature-local approvals and questions live here so the operator does not need to hunt through chat,
quickstart notes, operations docs, and task rows during the safety freeze.

The current docs status tool surfaces `answer_needed`, `comment_requested`, and `update_needed`
feature rows. Until feature-local `approval_needed` rows are surfaced by the tool, approval
decisions that need a direct human answer are encoded as `answer_needed`.

| ID | Status | Subject | Owner | Note |
|----|--------|---------|-------|------|
| RQ001 | resolved | [Q001 config pass path](./questions.md) | human | Approved path 1 on 2026-05-07: target-host config migration to the reviewed tracked baseline. |
| RQ002 | update_needed | [T040 launch evidence](./quickstart.md) | maintainer | Record the T040 evidence contract from quickstart: non-secret `server-start` receipt or equivalent safe fields for an already-started daemon, PID/runtime/log paths, daemon-owned status freshness, terminal logout survival, and no credentials or sensitive content. |
| RQ003 | resolved | [Docs workflow status parser](../../tools/doc_workflow.py) | maintainer | KISS decision: no parser repair needed before MVP; Q001 was visible through `answer_needed` and is now answered. |
| RQ004 | comment_requested | [Docs gate inactive-002 blocker](../002-fix-git-commit/checklists/requirements.md) | human | `speckit.docs` remains blocked by inactive `002`; touching it still needs explicit approval or a scoped active-feature gate. |
| RQ005 | update_needed | [May 7 live-hide incident](./quickstart.md#active-live-hide-incident-recorded-on-2026-05-07) | maintainer | Treat the visible `Пратэсты ў Беларусі (2020—2021)` edit as failed T041 evidence; collect minimal non-secret server facts, fix the first live-path boundary, rebuild/redeploy, and rerun live or dry-run smoke. |
