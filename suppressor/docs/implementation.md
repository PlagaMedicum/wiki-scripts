---
docmeta:
  status: maintained
  review: code-reviewed
  purpose: Current suppressor implementation contract at the documented scope.
  source: .specify/doc-registry.json
---

# Suppressor Implementation


## Purpose

The daemon:

- consumes Wikimedia EventStreams recent-change data
- matches revisions against the watched-title set
- performs public RevDel for `user|comment`
- maintains reconciliation and backfill state

## Current Non-Goals

- full suppression workflows
- broader moderation-platform behavior
- remote control as a product surface

## Current Behavior

- one daemon worker path for live handling
- reconciliation and backfill support
- local cache and local state persistence
- strict right checks before live operation
- process same-account edits too

The remaining unresolved part is the exact handling of journalling or follow-on actions that could
create loops.

## Current Deployment Model

- Linux-first
- one system
- one local operator TUI
- current production baseline aimed at be.wiki

## Safety Rules

- fail closed on unrecoverable auth or permission loss
- never log secrets or sensitive payloads
- keep current scope narrow unless a later approved spec changes it
- keep the reaction path fast enough that public metadata is hidden as quickly as possible
