import json
import hashlib
import subprocess
from pathlib import Path

import click
import questionary

from ..engine import scan_tree, snapshot_to_objects
from ..database import (
    init_db, get_db, update_index,
    save_commit, set_head, log_action, get_config, save_config,
)
from ..models import Commit
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group("import", cls=ColorGroup, help="Import history from Git or GitHub")
def import_cmd():
    pass


@import_cmd.command("git", help="Import commits from a Git repository")
@click.argument("git_dir", required=False)
def git_cmd(git_dir):
    if not git_dir:
        git_dir = questionary.text("Path to Git repository:").ask()
        if not git_dir:
            return

    git_path = Path(git_dir).resolve()
    if not (git_path / ".git").exists():
        err(f"not a git repository: {git_path}")
        return

    silo_dir = git_path / ".silo"
    if silo_dir.exists():
        err(f"already has a silo repo: {git_path}")
        return

    conn = init_db(silo_dir)
    conn.close()
    log_action(silo_dir, "import", f"from git: {git_path}")
    ok(f"importing {git_path} ...")

    branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(git_path), capture_output=True, text=True
    )
    orig_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "master"

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

    for i, entry in enumerate(entries):
        lines = entry.strip().split("\n")
        if len(lines) < 4:
            continue
        h_in = lines[0]
        ts = float(lines[1])
        author = lines[2]
        msg = "\n".join(lines[3:])
        last_author = author

        subprocess.run(["git", "checkout", "--force", h_in],
                      cwd=str(git_path), capture_output=True)
        tree = scan_tree(git_path)
        snapshot_to_objects(silo_dir, git_path, tree)

        parent = None
        if i > 0:
            prev_entry = entries[i - 1].strip().split("\n")
            parent = prev_entry[0]

        commit_data = {
            "tree": tree,
            "parent": parent,
            "author": author,
            "message": msg,
            "co_authors": [],
            "timestamp": ts,
            "branch": "main",
        }
        raw = json.dumps(commit_data, sort_keys=True).encode()
        ch = hashlib.sha256(raw).hexdigest()
        c_obj = Commit(hash=ch, **commit_data)
        save_commit(silo_dir, c_obj)
        set_head(silo_dir, ch, "main")
        conn = get_db(silo_dir)
        update_index(conn, tree)
        conn.close()
        log_action(silo_dir, "commit", f"[{ch[:8]}] {msg}")

        click.echo(f"  [{t(f'{i+1}/{total}', 'highlight')}] {t(ch[:8], 'hash')} {msg[:50]}")

    subprocess.run(["git", "checkout", orig_branch],
                  cwd=str(git_path), capture_output=True)

    if last_author and "@" in last_author:
        import re
        m = re.match(r"(.+)\s+<([^>]+)>", last_author)
        if m:
            cfg.set("name", m.group(1))
            cfg.set("email", m.group(2))
            save_config(silo_dir, cfg)
            click.echo(f"  config: {t('name', 'file')}={t(cfg.get('name'), 'modified')}, {t('email', 'file')}={t(cfg.get('email'), 'modified')}")

    ok(f"imported {t(str(total), 'hash')} commits from {t(str(git_path), 'file')}")


@import_cmd.command(help="Clone a GitHub repo and import its history")
@click.argument("repo", required=False)
def gh_cmd(repo):
    import tempfile

    if not repo:
        repo = questionary.text("GitHub repo (user/repo or URL):").ask()
        if not repo:
            return

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
        import shutil
        shutil.rmtree(str(tmp))
        return

    ok("importing cloned repo ...")
    ctx = click.get_current_context()
    ctx.invoke(git_cmd, git_dir=str(tmp / "repo"))

    import shutil
    shutil.rmtree(str(tmp))
