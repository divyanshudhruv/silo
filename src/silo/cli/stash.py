import shutil

import click
import questionary

from ..engine import scan_tree, diff_trees
from ..database import get_head, load_commit, log_action
from ..utils import ensure_dirs, load_ignore_patterns
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


def _stash_names(silo_dir):
    stash_dir = silo_dir / "stash"
    if not stash_dir.exists():
        return []
    return sorted(d.name for d in stash_dir.iterdir() if d.is_dir())


@click.group(cls=ColorGroup, help="Manage stashed changes")
def stash():
    pass


@stash.command("this", help="Stash modified files under a name")
@click.argument("name")
def stash_this(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    project_dir = silo_dir.parent
    stash_dir = silo_dir / "stash" / name
    if stash_dir.exists():
        err(f"stash '{name}' already exists")
        return

    head_hash, _ = get_head(silo_dir)
    parent_tree = {}
    if head_hash:
        c = load_commit(silo_dir, head_hash)
        if c:
            parent_tree = c.tree

    ignore = load_ignore_patterns(silo_dir)
    current = scan_tree(project_dir, ignore)
    _, modified, _ = diff_trees(parent_tree, current)

    if not modified:
        ok("nothing to stash")
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
    ok(f"stashed {len(modified)} files as '{t(name, 'file')}'")


@stash.command("put", help="Stash all files under a name")
@click.argument("name")
def stash_put(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    project_dir = silo_dir.parent
    stash_dir = silo_dir / "stash" / name
    if stash_dir.exists():
        err(f"stash '{name}' already exists")
        return

    ignore = load_ignore_patterns(silo_dir)
    current = scan_tree(project_dir, ignore)
    ensure_dirs(stash_dir)
    for rel_path, h in current.items():
        src = project_dir / rel_path
        if src.exists():
            dst = stash_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            src.unlink()

    log_action(silo_dir, "stash", f"put '{name}'")
    ok(f"stashed all files as '{t(name, 'file')}'")


@stash.command("revert", help="Restore a stash and remove it")
@click.argument("name", required=False)
def stash_revert(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    names = _stash_names(silo_dir)
    if not names:
        err("no stashes found")
        return

    if not name:
        name = questionary.select("Revert stash:", choices=names).ask()
        if not name:
            return

    stash_dir = silo_dir / "stash" / name
    if not stash_dir.exists():
        err(f"stash '{name}' not found")
        return

    project_dir = silo_dir.parent
    files = [f for f in stash_dir.rglob("*") if f.is_file()]
    for f in files:
        rel = f.relative_to(stash_dir)
        dst = project_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(f.read_bytes())

    shutil.rmtree(stash_dir)
    log_action(silo_dir, "stash", f"reverted '{name}'")
    ok(f"restored stash '{t(name, 'file')}' ({len(files)} files)")


@stash.command("drop", help="Delete a stash without restoring")
@click.argument("name", required=False)
def stash_drop(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    names = _stash_names(silo_dir)
    if not names:
        err("no stashes found")
        return

    if not name:
        name = questionary.select("Drop stash:", choices=names).ask()
        if not name:
            return

    stash_dir = silo_dir / "stash" / name
    if not stash_dir.exists():
        err(f"stash '{name}' not found")
        return

    shutil.rmtree(stash_dir)
    log_action(silo_dir, "stash", f"dropped '{name}'")
    ok(f"dropped stash '{t(name, 'file')}'")


@stash.command("list", help="List all stashes")
def stash_list():
    silo_dir = require_silo()
    if not silo_dir:
        return

    names = _stash_names(silo_dir)
    if names:
        click.echo("\n".join(t(n, "file") for n in names))
    else:
        ok("no stashes")
