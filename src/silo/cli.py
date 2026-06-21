import os
import json
import time
import hashlib
from pathlib import Path

import click

from .engine import scan_tree, snapshot_to_objects, diff_trees
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

    cfg = get_config(silo_dir)
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


def main():
    cli()
