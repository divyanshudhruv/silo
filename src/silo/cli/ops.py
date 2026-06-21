import time
import shutil
import tarfile

import click

from ..engine import scan_tree
from ..database import get_db, clear_index, init_db, list_commits, log_action, get_config, save_config
from ..utils import readable_time
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


@click.command(help="Remove orphaned objects and empty stashes")
def cleanup():
    silo_dir = require_silo()
    if not silo_dir:
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

    ok(f"cleaned up {freed} orphaned objects")


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
