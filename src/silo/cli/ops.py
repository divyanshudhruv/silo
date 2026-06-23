import json
import time
import hashlib
import shutil
import zipfile
import sqlite3
from pathlib import Path

import click

from ..engine import load_blob, scan_tree_with_content, snapshot_to_objects
from ..database import (
    init_db, list_commits, list_commits_meta, list_notes,
    log_action, get_config, save_config, list_tags, list_branches,
    get_branch, load_tag, save_tag, delete_tag, walk_parents, get_head,
    load_note, load_commit, get_db, update_index, save_commit, set_head,
    resolve_tag_commits, resolve_note_commits,
)
from ..models import Commit, Tag, Note, Config
from ..utils import load_ignore_patterns, walk_files
from ..theme import ok, err, t
from ._common import require_silo


def _clean_orphans(silo_dir: Path, valid_hashes: set[str]) -> tuple[int, int, int]:
    freed: int = 0
    obj_dir: Path = silo_dir / "objects"
    if obj_dir.exists():
        for sub in obj_dir.iterdir():
            if not sub.is_dir():
                continue
            for f in sub.iterdir():
                h: str = sub.name + f.name
                if h not in valid_hashes:
                    f.unlink()
                    freed += 1

    dropped_notes = 0
    notes_dir: Path = silo_dir / "notes"
    if notes_dir.exists():
        for f in list(notes_dir.iterdir()):
            if f.suffix == ".json":
                note: Note | None = load_note(silo_dir, f.stem)
                if note:
                    if note.branch:
                        pass
                    elif note.commits:
                        valid: list[str] = [
                            c for c in note.commits if load_commit(silo_dir, c)]
                        if not valid:
                            f.unlink()
                            dropped_notes += 1
                        elif len(valid) < len(note.commits):
                            note.commits = valid
                            f.write_text(note.to_json())
                    else:
                        pass
                else:
                    f.unlink()
                    dropped_notes += 1

    dropped_tags = 0
    for t_name in list_tags(silo_dir):
        tag_obj: Tag | None = load_tag(silo_dir, t_name)
        if tag_obj:
            if tag_obj.branch:
                pass
            elif tag_obj.commits:
                valid: list[str] = [
                    c for c in tag_obj.commits if load_commit(silo_dir, c)]
                if not valid:
                    delete_tag(silo_dir, t_name)
                    dropped_tags += 1
                elif len(valid) < len(tag_obj.commits):
                    tag_obj.commits = valid
                    save_tag(silo_dir, tag_obj)
            else:
                pass
        else:
            delete_tag(silo_dir, t_name)
            dropped_tags += 1

    return freed, dropped_notes, dropped_tags


@click.command(help="Create a compressed archive of the project")
@click.option("--noignore", is_flag=True, help="Ignore .siloignore and archive all files")
def snapshot(noignore):
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    project_dir: Path = silo_dir.parent
    ignore: list[str] | None = [
    ] if noignore else load_ignore_patterns(silo_dir)
    ts: str = time.strftime("%Y%m%d_%H%M%S")
    archive_name: str = project_dir.name + f"_snapshot_{ts}"
    dest: Path = project_dir.parent / archive_name

    with zipfile.ZipFile(f"{dest}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for f in walk_files(project_dir, ignore):
            zf.write(f, str(f.relative_to(project_dir).as_posix()))

    log_action(silo_dir, "snapshot", str(dest))
    ok(f"snapshot saved to {t(f'{dest}.zip', 'file')}")


@click.command("reinit", help="Erase all silo history and reinitialize")
def reinit():
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if click.confirm(t("silo: this will erase all history. continue?", "warn")):
        for d in ["objects", "commits", "branches", "tags", "notes", "logs"]:
            p: Path = silo_dir / d
            if p.exists():
                shutil.rmtree(p)
        db: Path = silo_dir / "index.db"
        if db.exists():
            db.unlink()
        init_db(silo_dir)

        project_dir: Path = silo_dir.parent
        cfg: Config = get_config(silo_dir)
        ignore: list[str] | None = load_ignore_patterns(silo_dir)
        current_tree, contents = scan_tree_with_content(
            project_dir, ignore)
        if current_tree:
            snapshot_to_objects(silo_dir, current_tree, contents)
            commit_data: dict[str, str | float | list[str]] = {
                "tree": current_tree,
                "parent": None,
                "author": f"{cfg.name} <{cfg.email}>",
                "message": "silo: initial commit",
                "co_authors": [],
                "timestamp": time.time(),
                "branch": "main",
            }
            raw: bytes = json.dumps(commit_data, sort_keys=True).encode()
            h: str = hashlib.sha256(raw).hexdigest()
            commit_obj: Commit = Commit(hash=h, **commit_data)
            save_commit(silo_dir, commit_obj)
            set_head(silo_dir, h, "main")
            conn: sqlite3.Connection | None = get_db(silo_dir)
            if conn is None:
                err("failed to get database connection")
                return
            update_index(conn, current_tree)
            conn.close()
            log_action(
                silo_dir, "commit", f"[{h[:8]}] silo: initial commit ({len(current_tree)} files)")

        log_action(silo_dir, "reinit", "all history reinitialized")
        ok("history reinitialized")


@click.command(help="Remove orphaned objects and stale notes/tags")
def cleanup():
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    commits: list[Commit] = list_commits(silo_dir)
    committed: set[str] = {c.hash for c in commits}
    used: set[str] = set()
    for c in commits:
        used.update(c.tree.values())

    freed, dropped_notes, dropped_tags = _clean_orphans(silo_dir, committed | used)

    parts: list[str] = []
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
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    cfg: Config = get_config(silo_dir)
    cfg.set("frozen", True)
    save_config(silo_dir, cfg)
    log_action(silo_dir, "freeze", "silo commits locked")
    ok("future silo commits blocked (silo config set frozen false to unlock)")


@click.command(help="Unblock silo commits")
def unfreeze():
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    cfg: Config = get_config(silo_dir)
    cfg.set("frozen", False)
    save_config(silo_dir, cfg)
    log_action(silo_dir, "unfreeze", "silo commits unlocked")
    ok("commits unlocked")


@click.command(help="Show repository statistics")
def info():
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    commits: list[Commit] | None = list_commits_meta(silo_dir)
    branches: list[str] = list_branches(silo_dir)

    obj_dir: Path = silo_dir / "objects"
    obj_count: int = 0
    obj_size: int = 0
    if obj_dir.exists():
        for sub in obj_dir.iterdir():
            if not sub.is_dir():
                continue
            for f in sub.iterdir():
                obj_count += 1
                obj_size += f.stat().st_size

    tag_names: list[str] = list_tags(silo_dir)
    notes: list[Note] = list_notes(silo_dir)

    head_hash, cur_branch = get_head(silo_dir)

    click.echo(f"Repository: {t(silo_dir.parent.name, 'file')}")
    click.echo(f"Commits:    {t(str(len(commits)), 'hash')}")
    click.echo(f"Branches:   {t(str(len(branches)), 'branch')}")
    click.echo(f"Current:    {t(cur_branch or 'detached', 'branch')}")
    click.echo(f"Tags:       {t(str(len(tag_names)), 'tag')}")
    click.echo(f"Notes:      {t(str(len(notes)), 'hash')}")
    click.echo(
        f"Objects:    {t(str(obj_count), 'hash')} ({t(_fmt_size(obj_size), 'dim')})")


def _fmt_size(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}TB"


@click.command(help="Garbage collect: remove unreachable commits, orphaned objects, stale notes/tags")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def gc(force):
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if not force and not click.confirm(t("silo: this will remove unreachable commits and objects. continue?", "warn")):
        return

    commits: list[Commit] = list_commits(silo_dir)
    all_hashes: set[str] = {c.hash for c in commits}

    reachable: set[str] = set()
    for b in list_branches(silo_dir):
        bh: str | None = get_branch(silo_dir, b)
        if bh and bh not in reachable:
            reachable.update(walk_parents(silo_dir, bh))

    for t_name in list_tags(silo_dir):
        tag_obj: Tag | None = load_tag(silo_dir, t_name)
        if tag_obj:
            reachable.update(resolve_tag_commits(silo_dir, tag_obj))

    for note in list_notes(silo_dir):
        reachable.update(resolve_note_commits(silo_dir, note))

    dropped_commits: int = 0
    for c in commits:
        if c.hash not in reachable:
            p: Path = silo_dir / "commits" / f"{c.hash}.json"
            if p.exists():
                p.unlink()
                dropped_commits += 1

    used_hashes: set[str] = reachable.copy()
    for c in commits:
        if c.hash in reachable:
            used_hashes.update(c.tree.values())

    freed, dropped_notes, dropped_tags = _clean_orphans(silo_dir, all_hashes | used_hashes)

    log_action(silo_dir, "gc",
               f"removed {dropped_commits} commits, {freed} objects, {dropped_notes} notes, {dropped_tags} tags")
    parts: list[str] = []
    if dropped_commits:
        parts.append(f"{dropped_commits} commits")
    if freed:
        parts.append(f"{freed} objects")
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
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    errors: int = 0
    commits: list[Commit] = list_commits(silo_dir)

    for c in commits:
        for rel_path, h in c.tree.items(): # type: ignore[arg-type]
            data: bytes | None = load_blob(silo_dir, h)
            if data is None:
                err(f"missing blob {t(h[:8], 'hash')} for '{rel_path}' in commit {t(c.hash[:8], 'hash')}")
                errors += 1

    if errors:
        err(f"found {errors} integrity error(s)")
    else:
        ok(f"all {len(commits)} commits and their blobs verified ({t('pass', 'ok')})")
