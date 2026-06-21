# silo

Local-first version manager. No staging, no merge, no complexity.

## Install

```bash
pip install silo
# or
uv tool install silo
```

Or from source:

```bash
uv sync
uv run silo --help
```

## Quick start

```bash
cd my-project
silo init
silo commit "initial snapshot"
# ... work ...
silo commit "added feature X"
silo log --oneline
```

## Commands

| Command    | Arguments                              | What it does                           |
| ---------- | -------------------------------------- | -------------------------------------- |
| `init`     | `[dir]`                                    | Create a new silo repository                  |
| `commit`   | `"<msg>" [--co <name>]`                    | Snapshot all files                           |
| `status`   | `[--ignored]`                              | Show working tree changes                    |
| `log`      | `[--oneline] [--graph] [--author] [--since] [--grep] [-n]` | Show commit history with filters |
| `diff`     | `[<c1> [<c2>]] [--stat]`                   | Compare commits or working tree (with content diff) |
| `show`     | `[<ref>]`                                  | Show commit details and file changes         |
| `branch`   | `<name>` / `list` / `-d` / `-m`            | Create, list, delete, or rename branches     |
| `switch`   | `<name>`                                   | Switch branches                              |
| `reset`    | `<ref>`                                    | Move HEAD and delete descendant commits      |
| `amend`    | `"<msg>" [<ref>]`                          | Edit a commit message                        |
| `stash`    | `this\|put\|revert\|drop\|list <name>`     | Save/restore working changes                 |
| `tag`      | `add\|list / -d / -m`                      | Tag commits (delete/rename with flags)       |
| `note`     | `add\|list / -d / -m`                      | Annotate commits (delete/rename with flags)  |
| `config`   | `set\|list <key> <val>`                    | View/edit configuration                      |
| `freeze`   | —                                          | Block further silo commits                   |
| `unfreeze` | —                                          | Unblock silo commits                         |
| `snapshot` | —                                          | Create a tar.gz archive of the project       |
| `purge`    | —                                          | Erase all silo history                       |
| `cleanup`  | —                                          | Remove orphaned objects, stale notes/tags    |
| `gc`       | `[-f]`                                     | Garbage collect unreachable commits/objects  |
| `verify`   | —                                          | Check repository integrity                   |
| `info`     | —                                          | Show repository statistics                   |
| `bridge`   | `enable\|disable\|status`                  | Git post-commit hook for auto silo commits   |
| `import`   | `git [<dir>]` / `gh <repo>`                | Import from Git (auto-detect) or clone+import |

## Directory structure

```
my-project/
  .silo/
    config.json         # local preferences (overrides global)
    index.db            # SQLite index for fast status
    HEAD                # current branch pointer
    objects/            # content-addressable file storage
    commits/            # JSON snapshots of every save
    branches/           # branch name -> commit hash
    stash/              # saved working changes
    tags/               # named commit pointers
    notes/              # commit annotations
    logs/history.log    # append-only audit trail
  .siloignore           # ignore patterns (optional)
```

## How it works

Silo takes a snapshot of every file in your project each time you run
`silo commit`. No staging area, no index to manage. Each commit stores
a complete tree of file hashes. The SQLite index gives fast status
checks by comparing current file hashes against the last commit.

This makes silo ideal for AI agents and single-developer workflows
where staging is unnecessary overhead.

## Configuration

Config keys are validated against a known schema. Unknown keys produce
a warning. Supported keys: `name`, `email`, `frozen`.

```bash
silo config set name "Alice"          # local config
silo config set -g email "a@b.com"    # global (~/.config/silo/)
silo config list                       # merged (local overrides global)
silo config list -g                    # global only
```

## .siloignore

Place a `.siloignore` file in the project root to exclude files from
commits. Uses `fnmatch` globbing. Trailing `/` matches directory
prefixes.

```
.venv/
build/
__pycache__/
*.pyc
dist/
*.egg-info/
```

## Bridge

Auto-create silo commits on every `git commit`:

```bash
silo bridge enable    # install post-commit hook
silo bridge disable   # remove hook
silo bridge status    # check status
```

## Compared to Git

|          | Git                 | Silo                 |
| -------- | ------------------- | -------------------- |
| Staging  | Required            | None                 |
| Merging  | Core feature        | Not planned          |
| Storage  | Packfiles + objects | Flat JSON + objects  |
| Index    | Binary index        | SQLite               |
| History  | DAG                 | Linear chain         |
| Use case | Teams, CI/CD        | Solo devs, AI agents |

## License

MIT
