# Commands reference

## init

```
silo init [directory]
```

Create a new silo repository. If `directory` is omited, uses the current directory. Creates `.silo/` with `config.json`, `HEAD`, `index.db`, and storage directories.

On first init, Silo automatically creates an empty `.siloignore` file in the project root (if none exists) and appends `.silo/` to the project's `.gitignore` (if present). It then scans all project files and creates an initial commit with message `"silo: initial commit"`.

The generated `.silo/config.json` includes all config keys with default values — edit them with `silo config set`.

---

## commit

```
silo commit "<message>" [--co <name>] [--noignore]
```

Snapshot all tracked files with a message. The `--co` flag (repeatable) adds co-authors. `--noignore` bypasses ignore files and snapshots all files.

Uses a single-pass scan: files are hashed and read in one pass. Excluded directories (`.silo/`, `.git/`, `__pycache__/`, and patterns from the active ignore file) are skipped before descending. By default `.siloignore` is used; set `use_gitignore=true` in config to use `.gitignore` instead.

```
silo commit                         # prompts for message interactively
silo commit "fix: handle edge case"
silo commit "pair programming" --co "Bob <bob@x.com>"
silo commit "full snapshot" --noignore
```

---

## status

```
silo status [--noignore]
```

Show working tree changes against the last commit. Three sections:

- `Changes to be added:` — files in working tree not in last commit
- `Changes not staged:` — files modified since last commit
- `Deleted files:` — files in last commit not in working tree

`--noignore` shows all files including those matched by `.siloignore`.

```
silo status
silo status --noignore
```

---

## log

```
silo log [--oneline] [--graph] [--author <name>] [--since <date>] [--grep <pattern>] [-n <count>]
```

Show commit history. Full format includes attached tags and notes per commit.

```
silo log                        # full log
silo log --oneline              # compact: hash + message
silo log --graph                # * for HEAD, o for others, branch labels
silo log --author "Alice"       # case-insensitive author match
silo log --since 2026-01-01     # commits after date
silo log --grep "fix"           # case-insensitive message match
silo log -n 5                   # last 5 commits
silo log --oneline -n 3 --author "Bob"
```

---

## diff

```
silo diff [<ref1> [<ref2>]] [--stat] [--noignore]
```

Show differences between commits or working tree:

- No args: working tree vs last commit (respects `.siloignore`)
- One ref: last commit vs that ref
- Two refs: ref1 vs ref2
- `--stat`: file names only, no content
- `--noignore`: bypass `.siloignore` when comparing working tree

```
silo diff
silo diff --stat
silo diff HEAD~1
silo diff abc1234 def5678
silo diff --noignore
```

---

## show

```
silo show [<ref>]
```

Show commit details (hash, author, date, branch, message, attached tags and notes) and file changes (added/modified/deleted with full paths). Defaults to HEAD.

```
silo show
silo show abc1234
silo show HEAD~2
```

---

## branch

Manage branches. Subcommand-only (no `-d`/`-m` flags).

```
silo branch create <name> [<ref>]     # create branch at a commit
silo branch list                       # list branches (* = current)
silo branch delete <name>              # delete a branch
silo branch rename <old> <new>         # rename a branch
```

```
silo branch create feature-x
silo branch create bugfix abc1234
silo branch list
silo branch delete old-feature
silo branch rename feature-x feature-y
```

---

## switch

```
silo switch [name]
```

Switch to another branch. Restores files from the target commit's tree. Removes files tracked in current tree but absent in the target tree.

Omitting `name` shows an interactive branch picker (excludes current branch).

```
silo switch feature-x
silo switch              # interactive picker
```

---

## reset

```
silo reset [ref]
```

Move HEAD and delete all descendant commits on the current branch. Uses parent-chain walk — only deletes commits between HEAD and target. Commits on other branches are never touched.

Omitting `ref` shows an interactive commit picker.

```
silo reset abc1234
silo reset              # interactive picker
```

---

## amend

```
silo amend "<message>" [<ref>]
```

Edit a commit message. Defaults to HEAD. Updates tags and notes that pointed to the old hash.

```
silo amend "fix: typo in readme"
silo amend "new message" abc1234
```

---

## tag

Manage tags. Subcommand-only (no `-d`/`-m` flags).

```
silo tag create <name>                       # create unattached tag
silo tag weld <name> [<hash>]                # attach tag to a commit
silo tag weld <name> --branch <branch>       # attach to ALL commits on a branch
silo tag unweld <name> [<hash>]              # detach tag from a commit
silo tag unweld <name> --branch <branch>     # detach from ALL commits on a branch
silo tag add <name> [<ref>]                  # create and attach in one step
silo tag list                                # list all tags
silo tag show <name>                         # show tag details + commits
silo tag delete <name>                       # delete a tag
silo tag rename <old> <new>                  # rename a tag
```

Tags can be attached to multiple commits. A tag without welded commits displays as `(unattached)`. Use `--branch` to weld/unweld to every commit on a branch at once.

```
silo tag create v1.0
silo tag weld v1.0 abc1234
silo tag weld v1.0 def5678
silo tag weld v1.0 --branch main      # attaches to all commits on main
silo tag unweld v1.0 def5678
silo tag unweld v1.0 --branch main    # detaches from all commits on main
silo tag add v2.0                     # attach to HEAD
silo tag add v2.0 abc1234
silo tag list
silo tag show v1.0
silo tag delete v1.0
silo tag rename v1.0 v1.1
```

---

## note

Manage notes. Subcommand-only (no `-d`/`-m` flags).

```
silo note create "<text>"                    # create unattached note
silo note weld <hash> [<commit>]             # attach note to a commit
silo note weld <hash> --branch <branch>      # attach to ALL commits on a branch
silo note unweld <hash> [<commit>]           # detach note from a commit
silo note unweld <hash> --branch <branch>    # detach from ALL commits on a branch
silo note add "<text>" [<ref>]               # create and attach in one step
silo note list                               # list all notes
silo note show <hash>                        # show note details + commits
silo note delete <hash>                      # delete a note
silo note edit <hash> "<text>"               # replace note text
```

Notes are identified by an auto-generated hash. Each note can be attached to multiple commits. Use `--branch` to weld/unweld to every commit on a branch at once.

```
silo note create "review this later"
silo note weld <hash> abc1234
silo note weld <hash> --branch main     # attaches to all commits on main
silo note unweld <hash> abc1234
silo note unweld <hash> --branch main   # detaches from all commits on main
silo note add "initial commit note"     # attach to HEAD
silo note add "bug report" abc1234
silo note list
silo note show <hash>
silo note delete <hash>
silo note edit <hash> "updated text"
```

---

## config

```
silo config set <key> <value>
silo config list
```

Valid keys: `name`, `email`, `frozen`, `theme`, `use_gitignore`.

| Key | Default | Description |
| --- | ------- | ----------- |
| `name` | `silo-user` | Author name for commits |
| `email` | `user@silo.local` | Author email for commits |
| `frozen` | `false` | Block new commits when `true` |
| `theme` | `default` | Output color theme |
| `use_gitignore` | `false` | Use `.gitignore` instead of `.siloignore` |

When `use_gitignore` is `true`, Silo reads ignore patterns from `.gitignore` instead of `.siloignore`. Default: `false`.

Note: `.silo/`, `.git/`, and `__pycache__/` are always excluded regardless of ignore files.

```
silo config set name "Alice"
silo config set use_gitignore true
silo config list
```

---

## freeze / unfreeze

```
silo freeze          # block future commits
silo unfreeze        # unblock
```

Sets `frozen=true` in local config. Commits and imports are rejected while frozen.

---

## snapshot

```
silo snapshot [--noignore]
```

Create a `.zip` archive of the project in the parent directory. Respects `.siloignore` by default. `--noignore` archives all files including ignored ones. Always excludes `.silo/` and `.git/`.

```
silo snapshot
silo snapshot --noignore
```

---

## reinit

```
silo reinit
```

Erase all silo history and reinitialize. Removes all objects, commits, branches, tags, notes, and logs. Reinitializes `.silo/` as empty. Prompts for confirmation.

---

## cleanup

```
silo cleanup
```

Remove orphaned objects (blobs not referenced by any commit) and stale tags/notes (pointing to non-existent commits).

---

## gc

```
silo gc [-f]
```

Garbage collect. Removes unreachable commits (not on any branch's parent chain and not referenced by tag/note), then runs cleanup for orphaned objects and stale notes/tags. `-f` skips confirmation.

```
silo gc
silo gc -f
```

---

## verify

```
silo verify
```

Check repository integrity. For every commit, verify that all blobs referenced in the tree exist in `.silo/objects/`.

---

## info

```
silo info
```

Show repository statistics: commits, branches, current branch, tags, notes, object count, and total object storage size.

---

## bridge

```
silo bridge enable     # install git post-commit hook
silo bridge disable    # remove git post-commit hook
silo bridge status     # check if hook is installed
```

Bridge between git and silo. `enable` installs a git `post-commit` hook that runs `silo commit` after every git commit.

---

## import

```
silo import git [<directory>]    # import from local git repo
silo import gh <repo>            # import from GitHub
```

Import history from Git or GitHub.

- `git`: reads the git repository at `<directory>` (defaults to `.`). Reads objects via `git ls-tree` and `git cat-file`.
- `gh`: clones `<repo>` from GitHub and imports its history. Supports `user/repo` shorthand and full URLs.

```
silo import git
silo import git ../other-project
silo import gh user/repo
silo import gh https://github.com/user/repo.git
```
