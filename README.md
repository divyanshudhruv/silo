# silo — local-first version manager

**Git? Never heard of her.** Silo is a dead-simple, standalone version tracker that lives in your project. No servers, no remotes, no accounts — just you and your files.

```bash
silo init
silo commit "first snapshot"
silo log
silo diff
silo tag ship-it --branch main
```

## Why?

- **Zero infrastructure** — no GitHub, no servers, no accounts
- **One binary** — `pip install silo` and you're done
- **Portable** — `.silo/` stays in your project, move it anywhere
- **Transparent** — all data is flat JSON files, easily inspectable
- **Snapshots** — `silo snapshot` creates a `.tar.gz` archive of your project

## Features at a glance

| Command | What it does |
|---|---|
| `init` | Create a new silo repo |
| `commit` | Snapshot your working tree |
| `log` | Browsable commit history with tags & notes |
| `diff` | See what changed, compare any two commits |
| `show` | Full commit details including files |
| `branch` | Create, list, rename, delete branches |
| `switch` | Jump between branches (rewrites working tree) |
| `reset` | Move HEAD back, delete commits after it |
| `stash` | Park modified files and restore them later |
| `tag` | Tag commits — single or whole branch at once |
| `note` | Annotate commits with freeform text |
| `snapshot` | Archive entire project as `.tar.gz` |
| `reinit` | Wipe history and start fresh |
| `gc` | Reclaim space from unreachable commits |
| `verify` | Check repository integrity |
| `bridge` | Auto-silo on every git commit |
| `import` | Pull history from git repos |

## How it works

Silo stores everything in `.silo/` inside your project:

```
.silo/
  config.json      # your name, email, settings
  HEAD             # current branch pointer
  index.db         # file index for fast status
  objects/         # content-addressed blobs (sha256)
  commits/         # commit metadata as JSON
  branches/        # branch → commit mappings
  tags/            # named references to commits
  notes/           # freeform annotations
  stash/           # parked working tree copies
  logs/            # audit trail
  .gitignore       # safe to commit .silo/ to git
```

Every file is hashed once (sha256) and stored in `objects/`. Commits are lightweight JSON files pointing to a tree of those hashes. No packfiles, no deltas, no magic.

## Pro tips

- **.siloignore** — add patterns to exclude files (similar to `.gitignore`)
- **usegitignore** — `silo config set usegitignore true` to use `.gitignore` instead
- **Tags on branches** — `silo tag v1.0 --branch main` attaches to every commit on the branch
- **Bridge mode** — `silo bridge enable` installs a git hook; every `git commit` auto-creates a silo commit
- **NO_COLOR** — set `NO_COLOR=1` to disable colored output

## Install

```bash
pip install silo
```

Or from source:

```bash
git clone https://github.com
cd silo
pip install -e .
```

---

See [docs/commands.md](docs/commands.md) for the full command reference.
