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


def main():
    cli()
