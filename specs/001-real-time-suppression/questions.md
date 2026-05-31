---
docmeta:
  status: draft
  review: feature-local
  purpose: Direct human answers required before suppressor MVP deployment trust.
  source:
  - speckit-plan human-review queue update on 2026-05-06
  - user approval on 2026-05-07
  - rsynced crash evidence update on 2026-05-13
---

# Questions: Real-Time Suppression Recovery


## Active Questions

There are no open feature questions at the moment. Q001 is answered. Any new scope expansion,
repo-wide Spec Kit workflow change, or inactive-feature cleanup needs explicit user approval and is
outside the active `001` emergency daemon gate unless recorded here first.

### Q001: Which reviewed config pass path is approved before T040?

- Status: answered
- Owner: human
- Needed before: T040 `server-start` launch-path evidence can be collected or trusted.
- Context: the target host reported `missing field realtime` for `./suppressor server-start`.
  T039 recorded this as a deployment-trust block, not as approval for a background config edit.
- Decision: approve path 1, target-host config migration to the reviewed tracked baseline.
- Answered at: 2026-05-07.

Approved path:

- Target-host config migration to the reviewed tracked baseline is approved.
- The server config was updated by the human operator.
- The daemon was started by the human operator.

2026-05-13 update: rsynced target-host evidence now provides equivalent safe fields for reviewed
`[realtime]` config plus `server-start` PID/runtime/log alignment. Remaining T040 evidence is the
terminal logout-survival check and concise recording of the non-secret safe fields. Do not include
credentials, `.env` values, cookies, tokens, raw logs with sensitive material, or sensitive page
content.
