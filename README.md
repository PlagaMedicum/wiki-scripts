# Wiki Scripts

This repository is a hub for independent be.wiki operator tools. Each project keeps its own README, Makefile, config, docs, tests, and runtime files inside its own directory.

## Projects

- [`bewiki_biblio/README.md`](bewiki_biblio/README.md): Python bibliography cleanup CLI. Start here for install, usage, and project-local docs.
- [`bewiki_suppressor/README.md`](bewiki_suppressor/README.md): Rust public-RevDel daemon. Start here for operator setup and architecture docs.

## Fast Entry Points

- `make -C bewiki_biblio help`
- `make -C bewiki_suppressor help`
- `python3 -m pip install -e ./bewiki_biblio`

## Layout

- `bewiki_biblio/`: self-contained Python project with its own docs and sources
- `bewiki_suppressor/`: self-contained Rust project with its own docs and state
- `.gitignore`: repo-wide ignore rules for local runtime state and build artifacts
