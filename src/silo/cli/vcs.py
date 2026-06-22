import click
import questionary

from ..engine import load_blob
from ..database import (
    get_db, clear_index, update_index, load_commit, resolve_ref,
    get_head, set_head, get_branch, set_branch, list_branches,
    delete_branch, rename_branch, log_action,
)
from ..theme import ok, err, t
from ._common import require_silo


@click.command(help="Create, list, delete, or rename branches")
@click.argument("name", required=False)
@click.option("--delete", "-d", "del_name", help="Delete a branch")
@click.option("--move", "-m", nargs=2, metavar="OLD NEW", help="Rename a branch")
def branch(name, del_name, move):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if del_name:
        if delete_branch(silo_dir, del_name):
            log_action(silo_dir, "branch", f"deleted '{del_name}'")
            ok(f"deleted branch '{t(del_name, 'branch')}'")
        else:
            err(f"cannot delete '{del_name}' (not found or current branch)")
        return

    if move:
        old, new = move
        if rename_branch(silo_dir, old, new):
            log_action(silo_dir, "branch", f"renamed '{old}' -> '{new}'")
            ok(f"renamed branch '{t(old, 'branch')}' -> '{t(new, 'branch')}'")
        else:
            err(f"cannot rename '{old}' (not found or '{new}' exists)")
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
@click.argument("name", required=False)
def switch(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    branches = list_branches(silo_dir)
    _, current_branch = get_head(silo_dir)

    if not name:
        choices = [b for b in branches if b != current_branch]
        if not choices:
            ok("only one branch exists")
            return
        name = questionary.select("Switch to branch:", choices=choices).ask()
        if not name:
            return

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

    for f in project_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(project_dir)
        parts = rel.parts
        if any(p.startswith(".silo") for p in parts) or any(p == ".git" for p in parts):
            continue
        rel_str = str(rel.as_posix())
        if rel_str not in commit.tree:
            f.unlink()

    conn = get_db(silo_dir)
    clear_index(conn)
    update_index(conn, commit.tree)
    conn.close()

    set_head(silo_dir, commit_hash, name)
    log_action(silo_dir, "switch", f"to '{name}'")
    ok(f"switched to branch '{t(name, 'branch')}'")


@click.command(help="Move HEAD to a commit and delete all commits after it")
@click.argument("commit_hash", required=False)
def reset(commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    head_hash, branch = get_head(silo_dir)
    if not head_hash:
        err("no HEAD commit")
        return

    if not commit_hash:
        commits = list_commits(silo_dir)
        if not commits:
            err("no commits yet")
            return
        choices = [f"{c.hash[:8]}  {c.message[:60]}" for c in commits]
        picked = questionary.select("Reset to commit:", choices=choices).ask()
        if not picked:
            return
        commit_hash = picked.split()[0]

    resolved = resolve_ref(silo_dir, commit_hash)
    if resolved:
        commit_hash = resolved

    target = load_commit(silo_dir, commit_hash)
    if not target:
        err(f"commit '{commit_hash}' not found")
        return

    # Walk parent chain from HEAD to target, delete descendants
    to_delete = []
    cur = head_hash
    while cur and cur != commit_hash:
        to_delete.append(cur)
        c = load_commit(silo_dir, cur)
        if not c:
            break
        cur = c.parent

    if cur != commit_hash:
        err(f"commit '{commit_hash}' is not an ancestor of HEAD")
        return

    for h in to_delete:
        p = silo_dir / "commits" / f"{h}.json"
        if p.exists():
            p.unlink()

    set_head(silo_dir, commit_hash, branch)

    conn = get_db(silo_dir)
    clear_index(conn)
    update_index(conn, target.tree)
    conn.close()

    log_action(silo_dir, "reset", f"to {target.hash[:8]}, dropped {len(to_delete)} commits")
    ok(f"reset to {t(target.hash[:8], 'hash')} ({target.message})")
    if to_delete:
        click.echo(f"  removed {len(to_delete)} commit(s) after it")
