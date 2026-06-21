# Contributing

## Setup

```bash
git clone <url> silo
cd silo
uv sync
uv run silo --help
```

## Code style

Readable over perfect. No docstrings unless the logic is genuinely
unexpected. Short variable names are fine. Standard libs preferred
over framework dependencies. PEP8 is a guideline, not a rule.

Run `uv run python -m pytest tests/` before opening a PR.

## Commit messages

Use conventional types: `feat`, `fix`, `chore`, `docs`, `refactor`,
`style`, `test`, `db`, `cli`, `storage`. Keep them descriptive.

Good:
```
cli: add branch creation, listing, and workspace switching
db: add sqlite index database
```

Avoid:
```
fix: bug
update stuff
```

## Pull requests

Keep PRs focused on one thing. Include test coverage for new
features. Link to any related issues.

## Architecture

```
src/silo/
  cli/
    __init__.py  # command registry
    _common.py   # ColorGroup, require_silo()
    bridge.py    # git hook bridge
    config.py    # config commands (local + global)
    core.py      # init, commit, status, log, diff, show, amend
    import_.py   # import git/gh
    note.py      # note commands
    ops.py       # snapshot, purge, cleanup, gc, verify, info
    stash.py     # stash commands
    tag.py       # tag commands
    vcs.py       # branch, switch, reset
  engine.py    # snapshot, blob storage, tree diff
  database.py  # sqlite index, commit/branch/tag/note/config persistence
  models.py    # Commit, Tag, Note, Config dataclasses (with schema validation)
  utils.py     # file walking, hashing, path helpers, .siloignore
  theme.py     # color/style helpers
```
