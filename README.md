# Wiki Scripts

This repository contains small tools used around Belarusian Wikipedia. It is a workspace for
separate projects, not one application. You can adapt this repo for other wikis as well.

## Projects

- [`biblio/`](biblio/README.md)
  Python tooling for bibliography and citation cleanup.
- [`suppressor/`](suppressor/README.md)
  Rust tooling for fast public RevDel on matched revisions. It is currently running 24/7 on
  `be.wikipedia.org` to support suppressor workflow with quicker reaction time.

## Basic Repo Usage

Run commands from the repository root. Use `make help` for more info.

Project-local commands are forwarded through the root Makefile:

```bash
make suppressor-help
make suppressor-run
make biblio-help
make biblio-run
```

## Where To Look

- root command wrapper: `Makefile`
- suppressor usage: [`suppressor/README.md`](suppressor/README.md)
- biblio usage: [`biblio/README.md`](biblio/README.md)
- local agent rules for this repo: [`AGENTS.md`](AGENTS.md)

## Disclaimer

LLMs are used heavily in this repository for drafting, refactoring, and routine code/documentation
work. That improves speed, but it also means some code or docs may not yet be fully verified by
careful manual review. Use thins code with caution.
