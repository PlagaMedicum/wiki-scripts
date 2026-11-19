# Wiki Scripts

This repository contains small tools used around Belarusian Wikipedia. It is a workspace for
separate projects, not one application. You can adapt this repo for other wikis as well.

## Projects

- [`biblio/`](biblio/README.md)
  Python tooling for bibliography and citation cleanup.
- [`agentic-bot/`](agentic-bot/README.md)
  Terminal workflow for reviewing and publishing wiki edit proposals.
- [`svg-replacer/`](svg-replacer/README.md)
  Interactive terminal tool for replacing raster images with their existing SVG
  equivalents on Wikimedia projects, one reviewed and approved edit at a time.
- [`suppressor/`](suppressor/README.md)
  Rust tooling for fast public RevDel on matched revisions. It is currently running 24/7 on
  `be.wikipedia.org` to support suppressor workflow with quicker reaction time.

## Basic Repo Usage

Run commands from the repository root. Use `make help` for more info.

Project-local commands are forwarded through the root Makefile:

```bash
make suppressor-help
make suppressor-run CONFIG=/path/to/wiki.toml
make biblio-help
make agentic-bot-help
make biblio-run
```

For maintenance, run the affected project's focused tests first, then `make check`
for the aggregate pre-commit gate. Project-specific `*-check` targets delegate to
the existing project gates. These checks do not establish deployment
health; suppressor release verification is documented in its project docs.

## Where To Look

- root command wrapper: `Makefile`
- suppressor usage: [`suppressor/README.md`](suppressor/README.md)
- biblio usage: [`biblio/README.md`](biblio/README.md)
- agentic-bot usage: [`agentic-bot/README.md`](agentic-bot/README.md)
- svg-replacer usage: [`svg-replacer/README.md`](svg-replacer/README.md)
- local agent rules for this repo: [`AGENTS.md`](AGENTS.md)
- active work and stable task IDs: [`docs/plan.md`](docs/plan.md)

## AI Assistance

This repository contains AI-assisted code and documentation. Review changes and
their verification evidence before use; generated material is not proof of
correctness.
