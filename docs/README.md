# Silo Documentation

- [Commands Reference](commands.md) - all commands and options

## Quick Start

```bash
silo init .
silo commit "first snapshot"
silo log --oneline
silo diff
silo tag v1.0 --branch main
```

Your project is now versioned. Every `silo commit` snapshots all files.

## Architecture

Silo is built in three layers:

| Layer | Modules | Role |
|-------|---------|------|
| CLI | `cli/core.py`, `cli/vcs.py`, `cli/tag.py`, `cli/note.py`, `cli/config.py`, `cli/ops.py`, `cli/bridge.py`, `cli/import_.py` | Click commands, user I/O, formatting |
| Persistence | `database.py`, `engine.py` | SQLite index, JSON commit storage, SHA256 + zlib blob store |
| Foundation | `models.py`, `utils.py`, `theme.py` | Typed dataclasses (`Commit`, `Tag`, `Note`, `Config`), file walking, ignore patterns, color styling |

### CLI internals

- **`ColorGroup`** (`cli/_common.py`) - custom Click group with colored help output
- **`require_silo()`** - guard that finds `.silo/` or prints an error
- **`weld_entity()` / `unweld_entity()`** (`cli/_entity.py`) - shared logic for attaching/detaching tags and notes to commits or branches

## How It Works

Silo is a local-first version manager. No servers, no accounts.

1. **Hashing** - every file is SHA256-hashed, stored as a zlib-compressed blob in `objects/XX/YY`
2. **Commits** - lightweight JSON `Commit` dataclass with tree hash map, parent, author, message, co-authors, timestamp, branch
3. **Index** - SQLite `index.db` with `file_index` (path → hash + mtime) and `commits_index` (hash → message + timestamp + author + branch) for fast queries
4. **Branches** - plain files in `branches/` containing a commit hash
5. **Tags & Notes** - JSON-serialized `Tag` / `Note` dataclasses, weldable to individual commits or entire branches
6. **Audit** - every action logged to `logs/history.log`

```
.silo/
  config.json      # name, email, frozen, theme, use_gitignore
  HEAD             # ref: refs/heads/main or detached hash
  index.db         # SQLite (file_index + commits_index)
  objects/XX/     # zlib-compressed blobs (sha256[0:2]/sha256[2:])
  commits/<hash>.json  # Commit dataclass
  branches/<name>      # file containing commit hash
  tags/<name>.json     # Tag dataclass
  notes/<hash>.json    # Note dataclass
  logs/history.log     # audit trail
```

## Tags & Notes

Tags and notes use a shared `weld`/`unweld` system. Attach any tag or note to individual commits or to every commit on a branch at once:

```bash
silo tag weld v1.0 --branch main     # tag every commit on main
silo note weld <hash> --branch main  # attach note to every commit on main
silo tag unweld v1.0 abc1234         # detach from a single commit
```

## Environment

- **`NO_COLOR`** - set `NO_COLOR=1` to disable colored output
- **`--version`** - `silo --version` prints the installed version

## Interactive Behaviors

- `silo commit` without a message opens an interactive prompt
- `silo amend` without a message opens a prompt pre-filled with the current message
- `silo switch` without a name shows a branch picker
- `silo reset` without a ref shows a commit picker

## Co-authors

```bash
silo commit "pair programming" --co "Bob <bob@x.com>" --co "Carol <carol@x.com>"
```

The `--co` / `-c` flag is repeatable and stores co-authors on the commit.

## Ref Syntax

- `HEAD` - current commit
- `HEAD~N` - Nth parent (e.g., `HEAD~1`, `HEAD~3`)
- Partial hash prefix (e.g., `abc1234`) - auto-resolved via SQLite prefix match

## Directory Structure

Every silo repository has a `.silo/` directory at its root. This is the entire repository — copy it, back it up, move it. Nothing lives outside `.silo/`.
