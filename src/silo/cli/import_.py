import json
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from ..engine import snapshot_to_objects
from ..database import (
    init_db, get_db, update_index,
    save_commit, set_head, log_action, get_config, save_config,
)
from ..models import Commit
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


def _git_tree(git_path, commit_hash):
    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", commit_hash],
        cwd=str(git_path), capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    tree = {}
    for entry in result.stdout.strip("\x00").split("\x00"):
        if not entry.strip():
            continue
        parts = entry.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        # meta: "mode type hash"
        blob_hash = meta.split()[-1]
        tree[path] = blob_hash
    return tree


def _import_commit(git_path, silo_dir, commit_hash):
    git_tree = _git_tree(git_path, commit_hash)
    if git_tree is None:
        return None, None

    tree = {}
    contents = {}
    for path, blob_hash in git_tree.items():
        res = subprocess.run(
            ["git", "cat-file", "-p", blob_hash],
            cwd=str(git_path), capture_output=True
        )
        if res.returncode != 0:
            continue
        data = res.stdout
        h = hashlib.sha256(data).hexdigest()
        tree[path] = h
        contents[path] = data

    snapshot_to_objects(silo_dir, tree, contents)
    return tree, contents


@click.group("import", cls=ColorGroup, help="Import history from Git or GitHub")
def import_cmd():
    pass


@import_cmd.command("git", help="Import commits from the current git repository")
@click.argument("git_dir", required=False, default=".")
def git_cmd(git_dir):
    git_path = Path(git_dir).resolve()
    if not (git_path / ".git").exists():
        err(f"not a git repository: {git_path}")
        return

    silo_dir = git_path / ".silo"
    if silo_dir.exists():
        if not click.confirm(t(f"silo already exists in {git_path}. reinitialize? existing data will be lost.", "warn")):
            return
        for d in ["objects", "commits", "branches", "stash", "tags", "notes", "logs"]:
            p = silo_dir / d
            if p.exists():
                shutil.rmtree(p)
        db = silo_dir / "index.db"
        if db.exists():
            db.unlink()

    conn = init_db(silo_dir)
    conn.close()
    log_action(silo_dir, "import", f"from git: {git_path}")
    ok(f"importing {git_path} ...")

    result = subprocess.run(
        ["git", "log", "--first-parent", "--format=%H%n%ct%n%an <%ae>%n%s%n==SILO==="],
        cwd=str(git_path), capture_output=True, text=True
    )
    if result.returncode != 0:
        err(f"git log failed: {result.stderr}")
        return

    entries = result.stdout.strip().split("==SILO===")
    entries = [e.strip() for e in entries if e.strip()]
    entries.reverse()
    total = len(entries)
    cfg = get_config(silo_dir)

    last_author = None
    prev_silo_hash = None

    for i, entry in enumerate(entries):
        lines = entry.strip().split("\n")
        if len(lines) < 4:
            continue
        ts = float(lines[1])
        author = lines[2]
        msg = "\n".join(lines[3:])
        last_author = author

        tree, contents = _import_commit(git_path, silo_dir, lines[0])
        if tree is None:
            continue

        commit_data = {
            "tree": tree,
            "parent": prev_silo_hash,
            "author": author,
            "message": msg,
            "co_authors": [],
            "timestamp": ts,
            "branch": "main",
        }
        raw = json.dumps(commit_data, sort_keys=True).encode()
        ch = hashlib.sha256(raw).hexdigest()
        prev_silo_hash = ch
        c_obj = Commit(hash=ch, **commit_data)
        save_commit(silo_dir, c_obj)
        set_head(silo_dir, ch, "main")
        conn = get_db(silo_dir)
        update_index(conn, tree)
        conn.close()
        log_action(silo_dir, "commit", f"[{ch[:8]}] {msg}")

        click.echo(f"  [{t(f'{i+1}/{total}', 'highlight')}] {t(ch[:8], 'hash')} {msg[:50]}")

    if last_author and "@" in last_author:
        m = re.match(r"(.+)\s+<([^>]+)>", last_author)
        if m:
            cfg.set("name", m.group(1))
            cfg.set("email", m.group(2))
            save_config(silo_dir, cfg)
            click.echo(f"  config: {t('name', 'file')}={t(cfg.get('name'), 'modified')}, {t('email', 'file')}={t(cfg.get('email'), 'modified')}")

    ok(f"imported {t(str(total), 'hash')} commits from {t(str(git_path), 'file')}")


@import_cmd.command(help="Clone a GitHub repo and import its history")
@click.argument("repo")
def gh_cmd(repo):
    tmp = Path(tempfile.mkdtemp(suffix="_silo_import"))
    url = repo
    if "/" in repo and not repo.startswith("http"):
        url = f"https://github.com/{repo}.git"

    ok(f"cloning {url} ...")
    result = subprocess.run(
        ["git", "clone", "--quiet", url, str(tmp / "repo")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err(f"clone failed: {result.stderr}")
        shutil.rmtree(str(tmp))
        return

    ok("importing cloned repo ...")
    ctx = click.get_current_context()
    ctx.invoke(git_cmd, git_dir=str(tmp / "repo"))

    shutil.rmtree(str(tmp))
