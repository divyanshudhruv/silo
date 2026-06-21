import click

from ..engine import scan_tree, diff_trees, load_blob
from ..database import (
    get_db, clear_index, load_commit,
    get_head, set_head, get_branch, set_branch, list_branches,
    log_action,
)
from ..theme import ok, err, t
from ._common import require_silo


@click.command(help="Create or list branches")
@click.argument("name", required=False)
def branch(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if not name or name == "list":
        branches = list_branches(silo_dir)
        _, current = get_head(silo_dir)
        for b in branches:
            marker = t("*", "highlight") + " " if b == current else "  "
            click.echo(f"{marker}{t(b, 'branch')}")
        return

    head_hash, _ = get_head(silo_dir)
    if not head_hash:
        err("nothing to branch from, no commits yet")
        return

    if get_branch(silo_dir, name):
        err(f"branch '{name}' already exists")
        return

    set_branch(silo_dir, name, head_hash)
    log_action(silo_dir, "branch", name)
    ok(f"created branch '{t(name, 'branch')}' at {t(head_hash[:8], 'hash')}")


@click.command(help="Switch to another branch")
@click.argument("name")
def switch(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    old_hash, current_branch = get_head(silo_dir)
    if name == current_branch:
        ok(f"already on '{t(name, 'branch')}'")
        return

    commit_hash = get_branch(silo_dir, name)
    if not commit_hash:
        err(f"branch '{name}' not found")
        return

    commit = load_commit(silo_dir, commit_hash)
    if not commit:
        err(f"commit not found for branch '{name}'")
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
    ok(f"switched to branch '{t(name, 'branch')}'")


@click.command(help="Restore working tree to a previous commit")
@click.argument("commit_hash")
def revert(commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    c = load_commit(silo_dir, commit_hash)
    if not c:
        err(f"commit '{commit_hash}' not found")
        return

    project_dir = silo_dir.parent
    current = scan_tree(project_dir)

    for rel_path, h in c.tree.items():
        data = load_blob(silo_dir, h)
        if data is None:
            err(f"blob {h[:8]} missing for '{rel_path}'")
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
    ok(f"reverted to {t(c.hash[:8], 'hash')} ({c.message})")
