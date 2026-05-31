---
docmeta:
  status: draft
  review: feature-local
  purpose: Human review and maintainer action queue for the active suppressor MVP gate.
  source:
  - speckit-plan human-review queue update on 2026-05-06
  - user approval on 2026-05-07
  - live-hide incident update with sensitive identifiers redacted
  - server-running launch-path mismatch update on 2026-05-07
  - rsynced crash evidence update on 2026-05-13
---

# Review Queue: Real-Time Suppression Recovery


Feature-local approvals and blockers live here so the operator does not need to hunt through chat,
quickstart notes, operations docs, and task rows during the safety freeze.

The current docs status tool surfaces `answer_needed`, `comment_requested`, and `update_needed`
feature rows. Until feature-local `approval_needed` rows are surfaced by the tool, approval
decisions that need a direct human answer are encoded as `answer_needed`.

This queue is not a second implementation plan. It tracks only unresolved human or maintainer
blockers for the active emergency daemon gate.

| ID | Status | Subject | Owner | Note |
|----|--------|---------|-------|------|
| RQ001 | resolved | [Q001 config pass path](./questions.md) | human | Approved path 1 on 2026-05-07: target-host config migration to the reviewed tracked baseline. |
| RQ002 | update_needed | [T040 launch evidence](./quickstart.md) | maintainer | Rsynced target-host evidence now shows reviewed `[realtime]` config plus `server-start` PID/runtime/log alignment. Record that concise non-secret partial evidence and finish the remaining T040 logout-survival check without credentials, raw logs, or sensitive incident identifiers. |
| RQ003 | resolved | [Docs workflow status parser](../../tools/doc_workflow.py) | maintainer | KISS decision: no parser repair needed before MVP; Q001 was visible through `answer_needed` and is now answered. |
| RQ004 | resolved | [Docs gate inactive-002 blocker](../002-fix-git-commit/checklists/requirements.md) | human | Explicitly out of the active `001` emergency scope. Do not block suppressor stabilization on inactive `002` docs work. |
| RQ005 | update_needed | [Active live-hide incident](./quickstart.md#active-live-hide-incident-with-sensitive-identifiers-redacted) | maintainer | Treat the operator-reported visible watched edit as failed T041 evidence without storing real page, actor, revision, diff, comment, screenshot, or log identifiers; fix the first live-path boundary, rebuild or redeploy the current binary, and rerun live or dry-run smoke after T040 logout evidence is handled. |
| RQ006 | resolved | [Crash-resilient runtime policy](./plan.md#phase-2b---crash-resilient-runtime-policy) | maintainer | Local source and tests now cover the two rsynced crash signatures. The remaining blocker is target-host proof that the running daemon is the rebuilt current binary. |
| RQ007 | update_needed | [Current-binary smoke gate](./quickstart.md#active-emergency-gate) | maintainer | T052 must now prove exact artifact identity, same-run current status shape, bounded lag or current head under live activity, and rejection of stale replay as realtime success. |
