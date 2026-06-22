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

## How It Works

Silo is a local-first version manager. No servers, no accounts. Every commit hashes every file (sha256), stores the blobs in `objects/`, writes a JSON tree to `commits/`, and updates `index.db` for instant status checks. Branches are plain files in `branches/` pointing to commit hashes. Tags and notes can be welded to individual commits or entire branches at once.

```
.silo/
  config.json      # name, email, settings
  HEAD             # current branch pointer
  index.db         # SQLite file index for fast status
  objects/         # content-addressed blobs (sha256)
  commits/         # commit metadata as JSON
  branches/        # branch → commit mappings
  tags/            # named references to commits
  notes/           # freeform annotations
  logs/            # audit trail
```

## Directory Structure

Every silo repository has a `.silo/` directory at its root. This is the entire repository — copy it, back it up, move it. Nothing lives outside `.silo/`.

## Tags & Notes

Tags and notes use a shared `weld`/`unweld` system. Attach any tag or note to individual commits or to every commit on a branch at once:

```bash
silo tag weld v1.0 --branch main     # tag every commit on main
silo note weld <hash> --branch main  # attach note to every commit on main
silo tag unweld v1.0 abc1234         # detach from a single commit
```
