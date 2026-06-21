import json
import time
import hashlib
from pathlib import Path

import click
import questionary

from ..engine import scan_tree, snapshot_to_objects, diff_trees
from ..database import (
    init_db, get_db, update_index, get_index, clear_index,
    save_commit, load_commit, list_commits, resolve_ref,
    get_head, set_head, log_action, get_config,
)
from ..models import Commit, Tag
from ..utils import ensure_dirs, readable_time
from ..theme import ok, err, t
from ._common import require_silo


@click.command(help="Initialize a new silo repository in a directory")
@click.argument("directory", default=".")
def init(directory):
    d = Path(directory).resolve()
    ensure_dirs(d)
    silo_dir = d / ".silo"
    if silo_dir.exists():
        ok(f"already initialized in {d}")
        return
    conn = init_db(silo_dir)
    conn.close()

    gi = silo_dir / ".gitignore"
    gi.write_text(
        "# Silo runtime data — safe to ignore\n"
        "/*\n"
        "!/config.json\n"
        "!/HEAD\n"
    )

    log_action(silo_dir, "init", f"dir={d}")
    ok(f"initialized empty repository in {silo_dir}")
    click.echo(f"  {t('config.json', 'file')} and {t('HEAD', 'file')} are safe to commit to git")
    click.echo(f"  run {t('silo commit', 'highlight')} to create the first snapshot")


@click.command(help="Snapshot all files with a commit message")
@click.argument("message", required=False)
@click.option("--co", "-c", multiple=True, help="Co-author names")
def commit(message, co):
    silo_dir = require_silo()
    if not silo_dir:
        return

    cfg = get_config(silo_dir)
    if cfg.get("frozen") == "true":
        err("commits are frozen (silo config set frozen false to unlock)")
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
        ok("nothing to commit, working tree clean")
        return

    if not message:
        message = questionary.text("Commit message:").ask()
        if not message:
            err("aborted: empty message")
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

    nfiles = len(added) + len(modified) + len(removed)
    log_action(silo_dir, "commit", f"[{h[:8]}] {message} ({nfiles} files)")

    click.echo(f"[{t(branch or 'main', 'branch')} {t(h[:8], 'hash')}] {message}")
    parts = []
    if added:
        parts.append(f"{len(added)}{t('+', 'added')}")
    if modified:
        parts.append(f"{len(modified)}{t('~', 'modified')}")
    if removed:
        parts.append(f"{len(removed)}{t('-', 'removed')}")
    click.echo(f"  {nfiles} file(s) changed: {', '.join(parts)}")


@click.command(help="Show working tree changes against last commit")
@click.option("--ignored", is_flag=True, help="Show ignored files")
def status(ignored):
    silo_dir = require_silo()
    if not silo_dir:
        return

    project_dir = silo_dir.parent
    conn = get_db(silo_dir)
    index = get_index(conn)
    conn.close()

    current = scan_tree(project_dir)
    added, modified, removed = diff_trees(index, current)

    if not added and not modified and not removed:
        ok("working tree clean")
        return

    if added:
        click.echo(t("Changes to be added:", "added"))
        for f in sorted(added):
            click.echo(f"  {t('+', 'added')} {f}")
    if modified:
        click.echo(t("Changes not staged:", "modified"))
        for f in sorted(modified):
            click.echo(f"  {t('~', 'modified')} {f}")
    if removed:
        click.echo(t("Deleted files:", "removed"))
        for f in sorted(removed):
            click.echo(f"  {t('-', 'removed')} {f}")


@click.command(help="Show commit history")
@click.option("--oneline", is_flag=True, help="Compact format")
@click.option("--graph", is_flag=True, help="ASCII graph with colors")
def log(oneline, graph):
    silo_dir = require_silo()
    if not silo_dir:
        return

    head_hash, branch = get_head(silo_dir)
    if not head_hash:
        ok("no commits yet")
        return

    commits = list_commits(silo_dir)
    if not commits:
        ok("no commits found")
        return

    for i, c in enumerate(commits):
        ts = readable_time(c.timestamp)
        if oneline:
            click.echo(f"{t(c.hash[:8], 'hash')} {c.message}")
        elif graph:
            sym = "*" if c.hash == head_hash else "o"
            marker = t(sym, "highlight") + " " + t(c.hash[:8], "hash")
            ref = ""
            if c.branch:
                ref = f" ({t(c.branch, 'branch')})"
            click.echo(f"  {marker}{ref} {c.message}")
            click.echo(f"  {t('|', 'dim')}  {ts}")
        else:
            click.echo(f"commit {t(c.hash, 'hash')}")
            if c.branch:
                click.echo(f"Branch: {t(c.branch, 'branch')}")
            click.echo(f"Author: {c.author}")
            click.echo(f"Date:   {ts}")
            click.echo("")
            click.echo(f"    {c.message}")
            if c.co_authors:
                click.echo(f"    Co-authored-by: {', '.join(c.co_authors)}")
            click.echo("")


@click.command(help="Show differences between commits or working tree")
@click.argument("commit1", required=False)
@click.argument("commit2", required=False)
def diff(commit1, commit2):
    silo_dir = require_silo()
    if not silo_dir:
        return

    project_dir = silo_dir.parent
    head_hash, _ = get_head(silo_dir)

    if commit1:
        r1 = resolve_ref(silo_dir, commit1)
        if r1:
            commit1 = r1
    if commit2:
        r2 = resolve_ref(silo_dir, commit2)
        if r2:
            commit2 = r2

    if commit1 and commit2:
        c1 = load_commit(silo_dir, commit1)
        c2 = load_commit(silo_dir, commit2)
        if not c1 or not c2:
            err("invalid commit hash")
            return
        tree1, tree2 = c1.tree, c2.tree
    elif commit1:
        c1 = load_commit(silo_dir, commit1)
        if not c1:
            err("invalid commit hash")
            return
        parent_tree = {}
        if c1.parent:
            pc = load_commit(silo_dir, c1.parent)
            if pc:
                parent_tree = pc.tree
        tree1, tree2 = parent_tree, c1.tree
    else:
        if not head_hash:
            ok("no commits yet")
            return
        head = load_commit(silo_dir, head_hash)
        current = scan_tree(project_dir)
        tree1, tree2 = head.tree, current

    a, m, r = diff_trees(tree1, tree2)

    if not a and not m and not r:
        ok("no differences")
        return

    nfiles = len(a) + len(m) + len(r)
    click.echo(f"{nfiles} file(s) changed:")

    for f in sorted(a):
        click.echo(f"  {t('+', 'added')} {f}")
    for f in sorted(m):
        click.echo(f"  {t('~', 'modified')} {f}")
    for f in sorted(r):
        click.echo(f"  {t('-', 'removed')} {f}")


@click.command(help="Edit a commit message")
@click.argument("message", required=False)
@click.argument("commit_hash", required=False)
def amend(message, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if commit_hash:
        resolved = resolve_ref(silo_dir, commit_hash)
        if resolved:
            commit_hash = resolved
    else:
        commit_hash, _ = get_head(silo_dir)

    if not commit_hash:
        err("no commits yet")
        return

    c = load_commit(silo_dir, commit_hash)
    if not c:
        err("commit not found")
        return

    branch = c.branch

    if not message:
        message = questionary.text("Amend message:", default=c.message).ask()
        if not message:
            err("aborted: empty message")
            return

    if message == c.message:
        ok("no change")
        return

    commit_data = {
        "tree": c.tree,
        "parent": c.parent,
        "author": c.author,
        "message": message,
        "co_authors": c.co_authors,
        "timestamp": time.time(),
        "branch": c.branch,
    }
    raw = json.dumps(commit_data, sort_keys=True).encode()
    new_hash = hashlib.sha256(raw).hexdigest()
    new_commit = Commit(hash=new_hash, **commit_data)
    save_commit(silo_dir, new_commit)

    old_p = silo_dir / "commits" / f"{commit_hash}.json"
    if old_p.exists():
        old_p.unlink()

    from ..database import list_tags, load_tag, save_tag, load_note, save_note

    for t_name in list_tags(silo_dir):
        h = load_tag(silo_dir, t_name)
        if h == commit_hash:
            tag_obj = Tag(name=t_name, commit_hash=new_hash, timestamp=time.time())
            save_tag(silo_dir, tag_obj)

    old_note = load_note(silo_dir, commit_hash)
    if old_note:
        notes_dir = silo_dir / "notes"
        old_np = notes_dir / f"{commit_hash}.txt"
        if old_np.exists():
            old_np.rename(notes_dir / f"{new_hash}.txt")

    set_head(silo_dir, new_hash, branch)

    conn = get_db(silo_dir)
    clear_index(conn)
    update_index(conn, c.tree)
    conn.close()

    log_action(silo_dir, "amend", f"[{new_hash[:8]}] {message}")
    ok(f"amended {t(commit_hash[:8], 'hash')} as {t(new_hash[:8], 'hash')} ({message})")
