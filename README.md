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
| `init`     | `[dir]`                                | Create a new silo repository           |
| `commit`   | `"<msg>" [--co <name>]`                | Snapshot all files                     |
| `status`   | `[--ignored]`                          | Show working tree changes              |
| `log`      | `[--oneline] [--graph]`                | Show commit history                    |
| `diff`     | `[<c1> [<c2>]]`                        | Compare commits or working tree        |
| `branch`   | `<name>` / `list`                      | Create or list branches                |
| `switch`   | `<name>`                               | Switch branches                        |
| `stash`    | `this\|put\|revert\|drop\|list <name>` | Save/restore working changes           |
| `tag`      | `add\|list [<name> [<commit>]]`        | Tag commits                            |
| `note`     | `add\|list <commit> <text>`            | Annotate commits                       |
| `revert`   | `<commit>`                             | Restore working tree to a commit       |
| `config`   | `set\|list <key> <val>`                | View/edit configuration                |
| `freeze`   | —                                      | Block further silo commits             |
| `unfreeze` | —                                      | Unblock silo commits                   |
| `snapshot` | —                                      | Create a tar.gz archive of the project |
| `purge`    | —                                      | Erase all silo history                 |
| `cleanup`  | —                                      | Remove orphaned objects                |
| `grid`     | —                                      | Show commit history in a table         |
| `import`   | `git\|gh <path>`                       | Import from Git or GitHub              |

## Directory structure

```
my-project/
  .silo/
    config.json         # user preferences
    index.db            # SQLite index for fast status
    HEAD                # current branch pointer
    objects/            # content-addressable file storage
    commits/            # JSON snapshots of every save
    branches/           # branch name -> commit hash
    stash/              # saved working changes
    tags/               # named commit pointers
    notes/              # commit annotations
    logs/history.log    # append-only audit trail
```

## How it works

Silo takes a snapshot of every file in your project each time you run
`silo commit`. No staging area, no index to manage. Each commit stores
a complete tree of file hashes. The SQLite index gives fast status
checks by comparing current file hashes against the last commit.

This makes silo ideal for AI agents and single-developer workflows
where staging is unnecessary overhead.

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
