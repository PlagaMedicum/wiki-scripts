# Repo Governance Research

<!-- DOCMETA:START -->
> Status: maintained
> Review: unreviewed
> Purpose: Remaining repo-level open questions, rationale, and missing proof rules.
> Source: .specify/doc-registry.json
<!-- DOCMETA:END -->

## Purpose

This file keeps only the unresolved repo-level questions that still need a specific answer. Each
item states what is already decided, what is still open, and what kind of evidence would close it.

## 1. What Is The Smallest Useful First Split In `biblio`?

### Already Decided

- The separation work should start now.
- The intended split line is between source-population/import work and source-processing/edit work.
- The first step should keep costs low and avoid a cosmetic reshuffle with no real boundary.

### Still Open

The exact first cut is not yet written down:

- which CLI entrypoints should move first
- which modules become the initial shared core
- which tests should move with that split instead of staying temporary

### Why It Matters

Without a concrete first cut, the decision stays abstract and the code can keep drifting as one
large Python application while the docs claim separation has started.

### What Would Close It

A narrow implementation spec that names the first entrypoints, module ownership, and the minimal
shared surface.

### Draft Default

Short draft implementation spec:

- keep one Python package and one operator Makefile for now
- make the first real split at the command and orchestration layer, not by extracting random helper
  modules first
- treat import/population work as the side owned by `manage_import.py`, source onboarding, source
  questions, and related source-management tests
- treat processing/edit work as the side owned by page analysis, execution, save policy, and the
  operator run flow
- keep the first shared core limited to source definitions, deterministic matching/rendering rules,
  and narrow runtime/auth helpers that both sides actually use
- first success signal: a routine import-flow change should not require touching page
  execution/save modules, and a routine page-processing change should not require touching import
  orchestration modules

This is a proposed default, not yet an approved implementation spec.

## 2. What Counts As A Proven “100% Match” In `biblio`?

### Already Decided

- Page-wide rewrites may auto-apply only when the match is exact and deterministic.
- Learned replacements need an initial manual approval before automatic promotion.

### Still Open

The docs still do not define the exact proof rule for an auto-eligible rewrite. The missing part is
the threshold:

- exact text equality only
- exact structured parse match
- exact match plus per-source guard conditions

### Why It Matters

Without a concrete proof rule, “100% match” can turn into a vague phrase that different parts of
the project interpret differently.

### What Would Close It

A narrow biblio spec that defines the proof conditions in code-facing terms and ties them to tests.

### Draft Default

Proposed proof rule for a “100% match” auto-eligible rewrite:

- every targeted citation or template instance on the page must resolve to exactly one source rule
  without fallback or manual tie-breaking
- the extracted structured fields must match the expected source shape exactly enough to reproduce
  the rendered citation deterministically
- no unmatched target fragments, ambiguous multi-matches, or review-required flags may remain on
  the page
- rerunning the same rewrite on the same input must produce the same normalized output and the same
  diff
- page-wide auto-apply should require per-source guard conditions, not only raw text equality

This is a proposed default, not yet an approved implementation spec.
