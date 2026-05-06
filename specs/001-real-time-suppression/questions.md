---
docmeta:
  status: draft
  review: feature-local
  purpose: Direct human answers required before suppressor MVP deployment trust.
  source:
  - speckit-plan human-review queue update on 2026-05-06
  - user approval on 2026-05-07
---

# Questions: Real-Time Suppression Recovery


## Active Questions

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

Remaining evidence for T040: record non-secret `server-start` receipt, PID/runtime/log paths,
daemon-owned status freshness, and terminal logout survival. Do not include credentials, `.env`
values, cookies, tokens, or sensitive page content.
