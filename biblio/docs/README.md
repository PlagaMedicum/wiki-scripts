# Documentation Index

This directory is for maintainer-facing guidance. If you are running the tool, start with the
project [README](../README.md).

## Read This Next

- [Architecture overview](architecture.md): stable design, source lifecycle, and data flow.
- [Architecture review](architecture-review.md): critical assessment, risks, and future splits.
- [Page save boundary](page-save-boundary.md): the current save-policy/I/O seam and the next
  extraction target.

## When To Use It

- Use the project README for operator setup and day-to-day commands.
- Use the architecture overview when you need to understand how source data, runtime state, and
  CLI flows fit together.
- Use the review when you want the blunt version of what is still fragile or too coupled.

For source-specific notes, open any `sources/<source_id>/README.md`.
