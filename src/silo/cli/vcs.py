import click
import questionary
from pathlib import Path
import sqlite3

from ..engine import load_blob, scan_tree, diff_trees
from ..database import (
    get_db, clear_index, update_index, load_commit, resolve_ref,
    get_head, set_head, get_branch, set_branch, list_branches,
    delete_branch, rename_branch, log_action, list_commits,
)
from ..models import Commit
from ..utils import load_ignore_patterns
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="Manage branches")
def branch() -> None:
    pass


@branch.command("create", help="Create a new branch at a commit")
@click.argument("name")
@click.argument("commit_hash", required=False)
def branch_create(name: str, commit_hash: str | None) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    head_hash, _ = get_head(silo_dir)
    if not head_hash:
        err("nothing to branch from, no commits yet")
        return

    ref: str = commit_hash or head_hash
    resolved: str | None = resolve_ref(silo_dir, ref)
    target: str = resolved or ref

    if get_branch(silo_dir, name) is not None:
        err(f"branch '{name}' already exists")
        return

    set_branch(silo_dir, name, target)  # type: ignore
    log_action(silo_dir, "branch", f"'{name}' -> {target[:8]}")
    ok(f"created branch '{t(name, 'branch')}' at {t(target[:8], 'hash')}")


@branch.command("list", help="List all branches")
def branch_list() -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    branches: list[str] = list_branches(silo_dir)
    _, current = get_head(silo_dir)
    if branches:
        for b in branches:
            marker: str = t("*", "highlight") + " " if b == current else "  "
            click.echo(f"{marker}{t(b, 'branch')}")
    else:
        ok("no branches")


@branch.command("delete", help="Delete a branch")
@click.argument("name")
def branch_delete(name: str) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if delete_branch(silo_dir, name):
        log_action(silo_dir, "branch", f"deleted '{name}'")
        ok(f"deleted branch '{t(name, 'branch')}'")
    else:
        err(f"cannot delete '{name}' (not found or current branch)")


@branch.command("rename", help="Rename a branch")
@click.argument("old")
@click.argument("new")
def branch_rename(old: str, new: str) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if rename_branch(silo_dir, old, new):
        log_action(silo_dir, "branch", f"renamed '{old}' -> '{new}'")
        ok(f"renamed branch '{t(old, 'branch')}' -> '{t(new, 'branch')}'")
    else:
        err(f"cannot rename '{old}' (not found or '{new}' exists)")


@click.command(help="Switch to another branch")
@click.argument("name", required=False)
def switch(name: str | None) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    branches: list[str] = list_branches(silo_dir)
    _, current_branch = get_head(silo_dir)

    if not name:
        choices: list[str] | None = [
            b for b in branches if b != current_branch]
        if not choices:
            ok("only one branch exists")
            return
        name: str | None = questionary.select(
            "Switch to branch:", choices=choices).ask()
        if not name:
            return

    if name == current_branch:
        ok(f"already on '{t(name, 'branch')}'")
        return

    commit_hash: str | None = get_branch(silo_dir, name)
    if not commit_hash:
        err(f"branch '{name}' not found")
        return

    commit: Commit | None = load_commit(silo_dir, commit_hash)
    if not commit:
        err(f"commit not found for branch '{name}'")
        return

    project_dir: Path = silo_dir.parent
    ignore: list[str] | None = load_ignore_patterns(silo_dir)
    current_tree: dict[str, str] = scan_tree(project_dir, ignore)
    head_hash, _ = get_head(silo_dir)
    if head_hash:
        head_commit: Commit | None = load_commit(silo_dir, head_hash)
        if head_commit:
            dirty_a, dirty_m, dirty_r = diff_trees(head_commit.tree, current_tree)
            if dirty_a or dirty_m or dirty_r:
                if not click.confirm(t("working tree has uncommitted changes. switch anyway?", "warn")):
                    return

    added, modified, removed = diff_trees(current_tree, commit.tree)

    for rel_path in added:
        data: bytes | None = load_blob(silo_dir, commit.tree[rel_path])
        if data is None:
            continue
        f: Path = project_dir / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)

    for rel_path in modified:
        data: bytes | None = load_blob(silo_dir, commit.tree[rel_path])
        if data is None:
            continue
        f: Path = project_dir / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)

    for rel_path in removed:
        f: Path = project_dir / rel_path
        if f.exists():
            f.unlink()

    conn: sqlite3.Connection | None = get_db(silo_dir)
    clear_index(conn)
    update_index(conn, commit.tree)
    conn.close()

    set_head(silo_dir, commit_hash, name)  # type: ignore
    log_action(silo_dir, "switch", f"to '{name}'")
    ok(f"switched to branch '{t(name, 'branch')}'")


@click.command(help="Move HEAD to a commit and delete all commits after it")
@click.argument("commit_hash", required=False)
def reset(commit_hash: str | None) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    head_hash, branch = get_head(silo_dir)
    if not head_hash:
        err("no HEAD commit")
        return

    if not commit_hash:
        commits: list[Commit] = list_commits(silo_dir)
        if not commits:
            err("no commits yet")
            return
        choices: list[str] | None = [
            f"{c.hash[:8]}  {c.message[:60]}" for c in commits]
        picked: str | None = questionary.select(
            "Reset to commit:", choices=choices).ask()
        if not picked:
            return
        commit_hash: str | None = picked.split()[0]

    resolved: str | None = resolve_ref(silo_dir, commit_hash)
    if resolved:
        commit_hash: str | None = resolved

    target: Commit | None = load_commit(silo_dir, commit_hash or "")
    if not target:
        err(f"commit '{commit_hash}' not found")
        return

    to_delete: list[str] = []
    cur: str | None = head_hash
    while cur and cur != commit_hash:
        to_delete.append(cur)
        c: Commit | None = load_commit(silo_dir, cur)
        if not c:
            break
        cur: str | None = c.parent

    if cur != commit_hash:
        err(f"commit '{commit_hash}' is not an ancestor of HEAD")
        return

    for h in to_delete:
        p: Path = silo_dir / "commits" / f"{h}.json"
        if p.exists():
            p.unlink()

    set_head(silo_dir, commit_hash, branch)  # type: ignore

    conn: sqlite3.Connection | None = get_db(silo_dir)
    clear_index(conn)
    update_index(conn, target.tree)
    conn.close()

    log_action(silo_dir, "reset",
               f"to {target.hash[:8]}, dropped {len(to_delete)} commits")
    ok(f"reset to {t(target.hash[:8], 'hash')} ({target.message})")
    if to_delete:
        click.echo(
            f"  removed {t(str(len(to_delete)), 'hash')} commit(s) after it")
