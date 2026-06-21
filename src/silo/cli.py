import os
import json
import time
import hashlib
import shutil
import tarfile
from pathlib import Path

import click

from .engine import scan_tree, snapshot_to_objects, diff_trees, load_blob
from .database import (
    init_db, get_db, update_index, get_index, clear_index,
    save_commit, load_commit, list_commits,
    get_head, set_head, get_branch, set_branch, list_branches,
    log_action, save_tag, load_tag, list_tags,
    save_note, load_note, get_config, save_config,
)
from .models import Commit, Tag, Note
from .utils import find_silo_dir, ensure_dirs, readable_time


@click.group()
def cli():
    pass


@cli.command()
@click.argument("directory", default=".")
def init(directory):
    d = Path(directory).resolve()
    ensure_dirs(d)
    silo_dir = d / ".silo"
    if silo_dir.exists():
        click.echo(f"silo: already initialized in {d}")
        return
    conn = init_db(silo_dir)
    conn.close()
    log_action(silo_dir, "init", f"dir={d}")
    click.echo(f"silo: initialized empty repository in {silo_dir}")


@cli.command()
@click.argument("message")
@click.option("--co", "-c", multiple=True, help="Co-author names")
def commit(message, co):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    cfg = get_config(silo_dir)
    if cfg.get("frozen") == "true":
        click.echo("silo: commits are frozen (silo config set frozen false to unlock)")
        return

    project_dir = silo_dir.parent
    head_hash, branch = get_head(silo_dir)

    parent_tree = {}
    if head_hash:
        parent_commit = load_commit(silo_dir, head_hash)
        if parent_commit:
            parent_tree = parent_commit.tree

    current_tree = scan_tree(project_dir)
    added, modified, removed = diff_trees(parent_tree, current_tree)

    if not added and not modified and not removed:
        click.echo("silo: nothing to commit, working tree clean")
        return

    snapshot_to_objects(silo_dir, project_dir, current_tree)

    commit_data = {
        "tree": current_tree,
        "parent": head_hash or None,
        "author": f"{cfg.get('name')} <{cfg.get('email')}>",
        "message": message,
        "co_authors": list(co),
        "timestamp": time.time(),
        "branch": branch or "main",
    }

    raw = json.dumps(commit_data, sort_keys=True).encode()
    h = hashlib.sha256(raw).hexdigest()
    commit_obj = Commit(hash=h, **commit_data)
    save_commit(silo_dir, commit_obj)
    set_head(silo_dir, h, branch or "main")

    conn = get_db(silo_dir)
    update_index(conn, current_tree)
    conn.close()

    summary = []
    if added:
        summary.append(f"{len(added)} added")
    if modified:
        summary.append(f"{len(modified)} modified")
    if removed:
        summary.append(f"{len(removed)} removed")
    log_action(silo_dir, "commit", f"[{h[:8]}] {message} ({', '.join(summary)})")

    click.echo(f"[{h[:8]}] {message}")
    click.echo(f" {', '.join(summary)}")


@cli.command()
@click.option("--ignored", is_flag=True, help="Show ignored files")
def status(ignored):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    project_dir = silo_dir.parent
    conn = get_db(silo_dir)
    index = get_index(conn)
    conn.close()

    current = scan_tree(project_dir)
    added, modified, removed = diff_trees(index, current)

    if not added and not modified and not removed:
        click.echo("silo: working tree clean")
        return

    if added:
        click.echo("Added files:")
        for f in sorted(added):
            click.echo(f"  + {f}")
    if modified:
        click.echo("Modified files:")
        for f in sorted(modified):
            click.echo(f"  ~ {f}")
    if removed:
        click.echo("Removed files:")
        for f in sorted(removed):
            click.echo(f"  - {f}")


@cli.command()
@click.option("--oneline", is_flag=True, help="Compact format")
@click.option("--graph", is_flag=True, help="ASCII graph")
def log(oneline, graph):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    head_hash, branch = get_head(silo_dir)
    if not head_hash:
        click.echo("silo: no commits yet")
        return

    commits = list_commits(silo_dir)
    if not commits:
        click.echo("silo: no commits found")
        return

    for c in commits:
        ts = readable_time(c.timestamp)
        if oneline:
            click.echo(f"{c.hash[:8]} {c.message}")
        elif graph:
            sym = "*" if c.hash == head_hash else "|"
            click.echo(f"{sym} {c.hash[:8]} ({c.branch}) {ts}")
            click.echo(f"{sym}   {c.message}")
        else:
            click.echo(f"commit {c.hash}")
            click.echo(f"Author: {c.author}")
            click.echo(f"Date:   {ts}")
            click.echo(f"Branch: {c.branch}")
            click.echo(f"\n    {c.message}")
            if c.co_authors:
                click.echo(f"    Co-authored-by: {', '.join(c.co_authors)}")
            click.echo("")


@cli.command()
@click.argument("commit1", required=False)
@click.argument("commit2", required=False)
def diff(commit1, commit2):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    project_dir = silo_dir.parent
    head_hash, _ = get_head(silo_dir)

    if commit1 and commit2:
        c1 = load_commit(silo_dir, commit1)
        c2 = load_commit(silo_dir, commit2)
        if not c1 or not c2:
            click.echo("silo: invalid commit hash", err=True)
            return
        tree1, tree2 = c1.tree, c2.tree
    elif commit1:
        c1 = load_commit(silo_dir, commit1)
        if not c1:
            click.echo("silo: invalid commit hash", err=True)
            return
        parent_tree = {}
        if c1.parent:
            pc = load_commit(silo_dir, c1.parent)
            if pc:
                parent_tree = pc.tree
        tree1, tree2 = parent_tree, c1.tree
    else:
        if not head_hash:
            click.echo("silo: no commits yet")
            return
        head = load_commit(silo_dir, head_hash)
        current = scan_tree(project_dir)
        tree1, tree2 = head.tree, current

    a, m, r = diff_trees(tree1, tree2)

    if not a and not m and not r:
        click.echo("silo: no differences")
        return

    for f in sorted(a):
        click.echo(f"+ {f}")
    for f in sorted(m):
        click.echo(f"~ {f}")
    for f in sorted(r):
        click.echo(f"- {f}")


@cli.command()
@click.argument("name", required=False)
def branch(name):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    if not name or name == "list":
        branches = list_branches(silo_dir)
        _, current = get_head(silo_dir)
        for b in branches:
            marker = "* " if b == current else "  "
            click.echo(f"{marker}{b}")
        return

    head_hash, _ = get_head(silo_dir)
    if not head_hash:
        click.echo("silo: nothing to branch from, no commits yet", err=True)
        return

    if get_branch(silo_dir, name):
        click.echo(f"silo: branch '{name}' already exists", err=True)
        return

    set_branch(silo_dir, name, head_hash)
    log_action(silo_dir, "branch", name)
    click.echo(f"silo: created branch '{name}' at {head_hash[:8]}")


@cli.command()
@click.argument("name")
def switch(name):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    old_hash, current_branch = get_head(silo_dir)
    if name == current_branch:
        click.echo(f"silo: already on '{name}'")
        return

    commit_hash = get_branch(silo_dir, name)
    if not commit_hash:
        click.echo(f"silo: branch '{name}' not found", err=True)
        return

    commit = load_commit(silo_dir, commit_hash)
    if not commit:
        click.echo(f"silo: commit not found for branch '{name}'", err=True)
        return

    project_dir = silo_dir.parent
    for rel_path, h in commit.tree.items():
        data = load_blob(silo_dir, h)
        if data is None:
            continue
        f = project_dir / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)

    if old_hash:
        old = load_commit(silo_dir, old_hash)
        if old:
            for rel_path in old.tree:
                if rel_path not in commit.tree:
                    f = project_dir / rel_path
                    if f.exists():
                        f.unlink()

    conn = get_db(silo_dir)
    clear_index(conn)
    conn.close()
    set_head(silo_dir, commit_hash, name)
    log_action(silo_dir, "switch", f"to '{name}'")
    click.echo(f"silo: switched to branch '{name}'")


@cli.group()
def stash():
    pass


@stash.command()
@click.argument("name")
def this(name):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    project_dir = silo_dir.parent
    stash_dir = silo_dir / "stash" / name
    if stash_dir.exists():
        click.echo(f"silo: stash '{name}' already exists", err=True)
        return

    head_hash, _ = get_head(silo_dir)
    parent_tree = {}
    if head_hash:
        c = load_commit(silo_dir, head_hash)
        if c:
            parent_tree = c.tree

    current = scan_tree(project_dir)
    _, modified, _ = diff_trees(parent_tree, current)

    if not modified:
        click.echo("silo: nothing to stash")
        return

    ensure_dirs(stash_dir)
    for rel_path in modified:
        src = project_dir / rel_path
        if src.exists():
            dst = stash_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            src.unlink()

    log_action(silo_dir, "stash", f"saved '{name}'")
    click.echo(f"silo: stashed {len(modified)} files as '{name}'")


@stash.command()
@click.argument("name")
def put(name):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    project_dir = silo_dir.parent
    stash_dir = silo_dir / "stash" / name
    if stash_dir.exists():
        click.echo(f"silo: stash '{name}' already exists", err=True)
        return

    current = scan_tree(project_dir)
    ensure_dirs(stash_dir)
    for rel_path, h in current.items():
        src = project_dir / rel_path
        if src.exists():
            dst = stash_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            src.unlink()

    log_action(silo_dir, "stash", f"put '{name}'")
    click.echo(f"silo: stashed all files as '{name}'")


@stash.command()
@click.argument("name")
def revert(name):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    stash_dir = silo_dir / "stash" / name
    if not stash_dir.exists():
        click.echo(f"silo: stash '{name}' not found", err=True)
        return

    project_dir = silo_dir.parent
    for f in stash_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(stash_dir)
        dst = project_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(f.read_bytes())

    import shutil
    shutil.rmtree(stash_dir)
    log_action(silo_dir, "stash", f"reverted '{name}'")
    click.echo(f"silo: reverted stash '{name}'")


@stash.command()
@click.argument("name")
def drop(name):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    stash_dir = silo_dir / "stash" / name
    if not stash_dir.exists():
        click.echo(f"silo: stash '{name}' not found", err=True)
        return

    import shutil
    shutil.rmtree(stash_dir)
    log_action(silo_dir, "stash", f"dropped '{name}'")
    click.echo(f"silo: dropped stash '{name}'")


@stash.command("list")
def stash_list():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    stash_dir = silo_dir / "stash"
    if not stash_dir.exists():
        return

    names = sorted(d.name for d in stash_dir.iterdir() if d.is_dir())
    if names:
        click.echo("\n".join(names))
    else:
        click.echo("silo: no stashes")


@cli.group()
def tag():
    pass


@tag.command()
@click.argument("name")
@click.argument("commit_hash", required=False)
def add(name, commit_hash):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    if load_tag(silo_dir, name):
        click.echo(f"silo: tag '{name}' already exists", err=True)
        return

    if not commit_hash:
        head_hash, _ = get_head(silo_dir)
        if not head_hash:
            click.echo("silo: no commits to tag", err=True)
            return
        commit_hash = head_hash

    t = Tag(name=name, commit_hash=commit_hash, timestamp=time.time())
    save_tag(silo_dir, t)
    log_action(silo_dir, "tag", f"'{name}' -> {commit_hash[:8]}")
    click.echo(f"silo: tagged '{name}' at {commit_hash[:8]}")


@tag.command("list")
def tag_list():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    tags = list_tags(silo_dir)
    if tags:
        for t in tags:
            h = load_tag(silo_dir, t)
            click.echo(f"{t} -> {h[:8] if h else '?'}")
    else:
        click.echo("silo: no tags")


@cli.group()
def note():
    pass


@note.command()
@click.argument("commit_hash")
@click.argument("text")
def add(commit_hash, text):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    c = load_commit(silo_dir, commit_hash)
    if not c:
        click.echo(f"silo: commit '{commit_hash}' not found", err=True)
        return

    n = Note(commit_hash=commit_hash, text=text, timestamp=time.time())
    save_note(silo_dir, n)
    log_action(silo_dir, "note", f"added to {commit_hash[:8]}")
    click.echo(f"silo: note added to {commit_hash[:8]}")


@note.command("list")
@click.argument("commit_hash")
def note_list(commit_hash):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    text = load_note(silo_dir, commit_hash)
    if text:
        click.echo(text)
    else:
        click.echo(f"silo: no notes for {commit_hash[:8]}")


@cli.command()
@click.argument("commit_hash")
def revert(commit_hash):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    c = load_commit(silo_dir, commit_hash)
    if not c:
        click.echo(f"silo: commit '{commit_hash}' not found", err=True)
        return

    project_dir = silo_dir.parent
    current = scan_tree(project_dir)

    for rel_path, h in c.tree.items():
        data = load_blob(silo_dir, h)
        if data is None:
            click.echo(f"silo: blob {h[:8]} missing for '{rel_path}'", err=True)
            continue
        f = project_dir / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)

    for rel_path in current:
        if rel_path not in c.tree:
            f = project_dir / rel_path
            if f.exists():
                f.unlink()

    conn = get_db(silo_dir)
    clear_index(conn)
    conn.close()
    log_action(silo_dir, "revert", f"to {c.hash[:8]}")
    click.echo(f"silo: reverted to {c.hash[:8]} ({c.message})")


@cli.group()
def config():
    pass


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    cfg = get_config(silo_dir)
    cfg.set(key, value)
    save_config(silo_dir, cfg)
    log_action(silo_dir, "config", f"{key}={value}")
    click.echo(f"silo: config {key}={value}")


@config.command("list")
def config_list():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    cfg = get_config(silo_dir)
    for k, v in cfg.data.items():
        click.echo(f"{k}={v}")


@cli.command()
def snapshot():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    project_dir = silo_dir.parent
    ts = time.strftime("%Y%m%d_%H%M%S")
    archive_name = project_dir.name + f"_snapshot_{ts}"
    dest = project_dir.parent / archive_name

    def filter_tar(ti):
        name = ti.name.replace("\\", "/")
        if name.startswith(".silo/") or name.startswith(".git/") or name.startswith(".venv/"):
            return None
        if name.endswith(".pyc") or "__pycache__" in name:
            return None
        return ti

    with tarfile.open(f"{dest}.tar.gz", "w:gz") as tar:
        tar.add(project_dir, arcname=project_dir.name, filter=filter_tar)

    log_action(silo_dir, "snapshot", str(dest))
    click.echo(f"silo: snapshot saved to {dest}.tar.gz")


@cli.command()
def purge():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    if click.confirm("silo: this will erase all history. continue?"):
        for d in ["objects", "commits", "branches", "stash", "tags", "notes", "logs"]:
            p = silo_dir / d
            if p.exists():
                shutil.rmtree(p)
        db = silo_dir / "index.db"
        if db.exists():
            db.unlink()
        init_db(silo_dir)
        log_action(silo_dir, "purge", "all history cleared")
        click.echo("silo: history purged")


@cli.command()
def cleanup():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    freed = 0
    obj_dir = silo_dir / "objects"
    if obj_dir.exists():
        used = set()
        for c in list_commits(silo_dir):
            for h in c.tree.values():
                used.add(h)
        for sub in obj_dir.iterdir():
            if not sub.is_dir():
                continue
            for f in sub.iterdir():
                h = sub.name + f.name
                if h not in used:
                    f.unlink()
                    freed += 1

    stash_dir = silo_dir / "stash"
    if stash_dir.exists():
        for d in list(stash_dir.iterdir()):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    click.echo(f"silo: cleaned up {freed} orphaned objects")


@cli.command()
def grid():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    commits = list_commits(silo_dir)
    if not commits:
        click.echo("silo: no commits yet")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        import sys
        console = Console(file=sys.stderr)
        table = Table(title="Commit History")
        table.add_column("Hash", style="cyan")
        table.add_column("Branch", style="green")
        table.add_column("Date", style="yellow")
        table.add_column("Message")
        for c in commits[:20]:
            ts = readable_time(c.timestamp)
            msg = c.message[:60] + "..." if len(c.message) > 60 else c.message
            table.add_row(c.hash[:8], c.branch or "?", ts, msg)
        console.print(table)
    except Exception:
        for c in commits[:20]:
            b = c.branch or "?"
            click.echo(f"{c.hash[:8]} | {b} | {readable_time(c.timestamp)} | {c.message}")


@cli.command()
def freeze():
    silo_dir = find_silo_dir()
    if not silo_dir:
        click.echo("silo: not a silo repository", err=True)
        return

    cfg = get_config(silo_dir)
    cfg.set("frozen", "true")
    save_config(silo_dir, cfg)
    log_action(silo_dir, "freeze", "silo commits locked")
    click.echo("silo: future silo commits blocked (silo config set frozen false to unlock)")


def main():
    cli()
