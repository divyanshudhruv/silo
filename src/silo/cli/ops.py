import time
import shutil
import tarfile
import time

import click

from ..engine import scan_tree, load_blob
from ..database import (
    get_db, clear_index, init_db, list_commits, list_commits_meta,
    log_action, get_config, save_config, list_tags, list_branches,
    load_tag, load_commit, get_head, resolve_ref, delete_tag, save_tag,
    delete_note, update_note, load_note,
)
from ..utils import readable_time, load_ignore_patterns
from ..theme import ok, err, t
from ._common import require_silo


@click.command(help="Create a compressed archive of the project")
def snapshot():
    silo_dir = require_silo()
    if not silo_dir:
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
    ok(f"snapshot saved to {t(f'{dest}.tar.gz', 'file')}")


@click.command(help="Erase all silo history and start fresh")
def purge():
    silo_dir = require_silo()
    if not silo_dir:
        return

    if click.confirm(t("silo: this will erase all history. continue?", "warn")):
        for d in ["objects", "commits", "branches", "stash", "tags", "notes", "logs"]:
            p = silo_dir / d
            if p.exists():
                shutil.rmtree(p)
        db = silo_dir / "index.db"
        if db.exists():
            db.unlink()
        init_db(silo_dir)
        log_action(silo_dir, "purge", "all history cleared")
        ok("history purged")


@click.command(help="Remove orphaned objects, stale notes/tags, and empty stashes")
def cleanup():
    silo_dir = require_silo()
    if not silo_dir:
        return

    committed = {c.hash for c in list_commits(silo_dir)}

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

    dropped_notes = 0
    notes_dir = silo_dir / "notes"
    if notes_dir.exists():
        for f in notes_dir.iterdir():
            if f.stem not in committed:
                f.unlink()
                dropped_notes += 1

    dropped_tags = 0
    for t_name in list_tags(silo_dir):
        th = load_tag(silo_dir, t_name)
        if th and th not in committed:
            delete_tag(silo_dir, t_name)
            dropped_tags += 1

    stash_dir = silo_dir / "stash"
    if stash_dir.exists():
        for d in list(stash_dir.iterdir()):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    parts = []
    if freed:
        parts.append(f"{freed} objects")
    if dropped_notes:
        parts.append(f"{dropped_notes} notes")
    if dropped_tags:
        parts.append(f"{dropped_tags} tags")
    if parts:
        ok(f"cleaned up {', '.join(parts)}")
    else:
        ok("nothing to clean")


@click.command(help="Block future silo commits")
def freeze():
    silo_dir = require_silo()
    if not silo_dir:
        return

    cfg = get_config(silo_dir)
    cfg.set("frozen", "true")
    save_config(silo_dir, cfg)
    log_action(silo_dir, "freeze", "silo commits locked")
    ok("future silo commits blocked (silo config set frozen false to unlock)")


@click.command(help="Unblock silo commits")
def unfreeze():
    silo_dir = require_silo()
    if not silo_dir:
        return

    cfg = get_config(silo_dir)
    cfg.set("frozen", "false")
    save_config(silo_dir, cfg)
    log_action(silo_dir, "unfreeze", "silo commits unlocked")
    ok("commits unlocked")


@click.command(help="Show repository statistics")
def info():
    silo_dir = require_silo()
    if not silo_dir:
        return

    commits = list_commits_meta(silo_dir)
    branches = list_branches(silo_dir)

    obj_dir = silo_dir / "objects"
    obj_count = 0
    obj_size = 0
    if obj_dir.exists():
        for sub in obj_dir.iterdir():
            if not sub.is_dir():
                continue
            for f in sub.iterdir():
                obj_count += 1
                obj_size += f.stat().st_size

    tag_names = list_tags(silo_dir)
    stash_dir = silo_dir / "stash"
    stash_count = len([d for d in stash_dir.iterdir() if d.is_dir()]) if stash_dir.exists() else 0

    head_hash, cur_branch = get_head(silo_dir)

    click.echo(f"Repository: {t(silo_dir.parent.name, 'file')}")
    click.echo(f"Commits:    {t(str(len(commits)), 'hash')}")
    click.echo(f"Branches:   {t(str(len(branches)), 'branch')}")
    click.echo(f"Current:    {t(cur_branch or 'detached', 'branch')}")
    click.echo(f"Tags:       {t(str(len(tag_names)), 'file')}")
    click.echo(f"Stashes:    {t(str(stash_count), 'file')}")
    click.echo(f"Objects:    {t(str(obj_count), 'hash')} ({t(_fmt_size(obj_size), 'dim')})")


def _fmt_size(b):
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}TB"


@click.command(help="Garbage collect: remove unreachable commits, orphaned objects, stale notes/tags")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def gc(force):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if not force and not click.confirm(t("silo: this will remove unreachable commits and objects. continue?", "warn")):
        return

    commits = list_commits(silo_dir)
    all_hashes = {c.hash for c in commits}

    from ..database import get_branch

    # Collect reachable hashes from branches and tags
    reachable = set()
    for b in list_branches(silo_dir):
        bh = get_branch(silo_dir, b)
        if bh:
            reachable.add(bh)
            c = load_commit(silo_dir, bh)
            while c and c.parent:
                reachable.add(c.parent)
                c = load_commit(silo_dir, c.parent)

    for t_name in list_tags(silo_dir):
        th = load_tag(silo_dir, t_name)
        if th:
            reachable.add(th)

    # Delete unreachable commits
    dropped_commits = 0
    for c in commits:
        if c.hash not in reachable:
            p = silo_dir / "commits" / f"{c.hash}.json"
            if p.exists():
                p.unlink()
                dropped_commits += 1

    # Delete orphaned objects (blobs not in any commit tree)
    used_hashes = set()
    for c in commits:
        if c.hash in reachable:
            used_hashes.update(c.tree.values())

    freed_objects = 0
    obj_dir = silo_dir / "objects"
    if obj_dir.exists():
        for sub in obj_dir.iterdir():
            if not sub.is_dir():
                continue
            for f in sub.iterdir():
                h = sub.name + f.name
                if h not in used_hashes:
                    f.unlink()
                    freed_objects += 1

    # Delete notes/tags pointing to deleted commits
    dropped_notes = 0
    notes_dir = silo_dir / "notes"
    if notes_dir.exists():
        for f in notes_dir.iterdir():
            h = f.stem
            if h not in all_hashes:
                f.unlink()
                dropped_notes += 1

    dropped_tags = 0
    for t_name in list_tags(silo_dir):
        th = load_tag(silo_dir, t_name)
        if th and th not in all_hashes:
            delete_tag(silo_dir, t_name)
            dropped_tags += 1

    # Remove empty stash dirs
    stash_dir = silo_dir / "stash"
    if stash_dir.exists():
        for d in list(stash_dir.iterdir()):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    log_action(silo_dir, "gc", f"removed {dropped_commits} commits, {freed_objects} objects, {dropped_notes} notes, {dropped_tags} tags")
    parts = []
    if dropped_commits:
        parts.append(f"{dropped_commits} commits")
    if freed_objects:
        parts.append(f"{freed_objects} objects")
    if dropped_notes:
        parts.append(f"{dropped_notes} notes")
    if dropped_tags:
        parts.append(f"{dropped_tags} tags")
    if parts:
        ok(f"gc removed {', '.join(parts)}")
    else:
        ok("nothing to clean")


@click.command(help="Verify repository integrity")
def verify():
    silo_dir = require_silo()
    if not silo_dir:
        return

    errors = 0
    commits = list_commits(silo_dir)

    for c in commits:
        for rel_path, h in c.tree.items():
            data = load_blob(silo_dir, h)
            if data is None:
                err(f"missing blob {t(h[:8], 'hash')} for '{rel_path}' in commit {t(c.hash[:8], 'hash')}")
                errors += 1

    if errors:
        err(f"found {errors} integrity error(s)")
    else:
        ok(f"all {len(commits)} commits and their blobs verified ({t('pass', 'ok')})")
