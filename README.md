# Wiki Scripts

This repository is a hub for independent wiki operator tools. Those projects were first developed
for be.wiki, but the user-facing commands are kept generic and the docs explain how to retarget
them to another local wiki.

## Projects

- [`biblio/README.md`](biblio/README.md): Biblio, the Python bibliography cleanup CLI. Start here for install, usage, and project-local docs.
- [`suppressor/README.md`](suppressor/README.md): Suppressor, the Rust public-RevDel daemon. Start here for operator setup and architecture docs.

## Fast Entry Points

- `make -C biblio help`
- `make -C suppressor help`
- `biblio --help`
- `suppressor --help`
- `python3 -m pip install -e ./biblio`

## Which Tool

- choose `biblio/` if you want to replace or normalize bibliography templates on wiki pages
- choose `suppressor/` if you want a daemon that watches recent changes and hides revision metadata on matched pages

## Quick Local Setup

1. Pick the project directory you need: `biblio/` or `suppressor/`.
2. Install the local runtime for that project:
   `python3 -m pip install -e ./biblio` for Biblio, or Rust stable plus `cargo` for Suppressor.
3. Open `Special:BotPasswords` on the target wiki and create a dedicated bot password for the account you will run locally.
4. Put the generated credentials into the project-local `.env` file:
   `biblio/.env` for Biblio, `suppressor/.env` for Suppressor.
   Biblio stores the base username and bot-password label separately, while Suppressor stores the full `username@label` login.
5. Run the project-local auth check or first-run command:
   `make -C biblio run` for Biblio, `make -C suppressor check-auth` and `make -C suppressor dry-run` for Suppressor.
6. Only then switch to live runs or local service management.

## Layout

- `biblio/`: self-contained Python project with its own docs and sources
- `suppressor/`: self-contained Rust project with its own docs and state
- `.gitignore`: repo-wide ignore rules for local runtime state and build artifacts

## Observability Standard

Across projects in this repository:

- normal operator output should stay concise and task-focused
- verbose or debug diagnostics should be opt-in
- daemon-style projects should prefer metrics plus safe structured logs over ad hoc terminal journals
- journal-facing logs must not contain secrets, tokens, raw private payloads, or other sensitive text
- detailed diagnostics should live in project-local runtime files or explicitly requested verbose modes
- every operator action and failure boundary should have direct tests rather than relying on incidental coverage

## Portable Use

If you want to adapt either tool to another local wiki, keep the project structure and change the
wiki-specific inputs instead:

- for Biblio, add or edit source folders under `biblio/sources/`, set `site_lang` and
  `family`, and adjust the source search terms, template names, edit summaries, candidate rules,
  and normalization rules for the target wiki
- for Suppressor, edit `suppressor/config.toml` and `suppressor/.env` so the API URL,
  EventStreams URL, wiki code, server name, suppression-list page, revdel reason text, and
  bot-password credentials point at the target wiki
- confirm the required rights and bot-password grants on the target wiki before assuming the
  be.wiki defaults apply there
- in both projects, keep the docs and source-local README files close to the code that they
  describe

Public names versus internal names:

- prefer the public commands `biblio` and `suppressor`
- keep using the existing internal directories `biblio/` and `suppressor/`
- Biblio still keeps the internal Python module path `biblio`
- Suppressor still keeps the internal crate name `suppressor` and the existing `BEWIKI_*` env vars
