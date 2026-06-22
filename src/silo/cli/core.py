import json
import time
import hashlib
from difflib import unified_diff
from datetime import datetime
from pathlib import Path

import click
import questionary

from ..engine import scan_tree, scan_tree_with_content, snapshot_to_objects, diff_trees, load_blob
from ..database import (
    init_db, get_db, update_index, get_index, clear_index,
    save_commit, load_commit, resolve_commit, list_commits, list_commits_meta,
    get_head, set_head, log_action, get_config,
    replace_commit_in_tags_notes,
    list_tags, load_tag, resolve_tag_commits,
    list_notes, load_note, resolve_note_commits,
)
from ..models import Commit, Note
from ..utils import ensure_dirs, readable_time, load_ignore_patterns, filter_ignored
from ..theme import ok, err, t
from ._common import require_silo


def _fmt_message(msg):
    if msg.startswith("auto:"):
        return t(" auto ", "auto") + msg[5:]
    return msg


def _annotations(silo_dir):
    tag_map = {}
    for name in list_tags(silo_dir):
        tag = load_tag(silo_dir, name)
        if tag:
            for h in resolve_tag_commits(silo_dir, tag):
                tag_map.setdefault(h, []).append(name)

    note_map = {}
    for note in list_notes(silo_dir):
        for h in resolve_note_commits(silo_dir, note):
            preview = note.text[:40] + ("..." if len(note.text) > 40 else "")
            note_map.setdefault(h, []).append(f"{note.hash[:8]} {preview}")

    return tag_map, note_map


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
    click.echo(f"  create {t('.siloignore', 'file')} in project root to exclude patterns")
    click.echo(f"  or set {t('usegitignore', 'file')}=true with {t('silo config set usegitignore true', 'highlight')} to use .gitignore instead")
    click.echo(f"  run {t('silo commit', 'highlight')} to create the first snapshot")


@click.command(help="Snapshot all files with a commit message")
@click.argument("message", required=False)
@click.option("--co", "-c", multiple=True, help="Co-author names")
@click.option("--noignore", is_flag=True, help="Ignore .siloignore and snapshot all files")
def commit(message, co, noignore):
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

    ignore = None if noignore else load_ignore_patterns(silo_dir)
    current_tree, contents = scan_tree_with_content(project_dir, ignore)
    if ignore:
        keep = filter_ignored(list(parent_tree), ignore)
        parent_tree = {k: parent_tree[k] for k in keep}
    added, modified, removed = diff_trees(parent_tree, current_tree)

    if not added and not modified and not removed:
        ok("nothing to commit, working tree clean")
        return

    if not message:
        message = questionary.text("Commit message:").ask()
        if not message:
            err("aborted: empty message")
            return

    snapshot_to_objects(silo_dir, current_tree, contents)

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
    clear_index(conn)
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
@click.option("--noignore", is_flag=True, help="Ignore .siloignore and show all files")
def status(noignore):
    silo_dir = require_silo()
    if not silo_dir:
        return

    project_dir = silo_dir.parent
    _, branch = get_head(silo_dir)
    click.echo(f"On branch {t(branch or 'detached', 'branch')}")

    conn = get_db(silo_dir)
    index = get_index(conn)
    conn.close()

    ignore = None if noignore else load_ignore_patterns(silo_dir)
    current = scan_tree(project_dir, ignore)
    if ignore:
        keep = filter_ignored(list(index), ignore)
        index = {k: index[k] for k in keep}
    added, modified, removed = diff_trees(index, current)

    if not added and not modified and not removed:
        ok("working tree clean")
        return

    if added:
        click.echo(t("Changes to be added:", "added"))
        for f in sorted(added):
            click.echo(f"  {t('+', 'added')} {t(f, 'file')}")
    if modified:
        click.echo(t("Changes not staged:", "modified"))
        for f in sorted(modified):
            click.echo(f"  {t('~', 'modified')} {t(f, 'file')}")
    if removed:
        click.echo(t("Deleted files:", "removed"))
        for f in sorted(removed):
            click.echo(f"  {t('-', 'removed')} {t(f, 'file')}")


@click.command(help="Show commit history")
@click.option("--oneline", is_flag=True, help="Compact format")
@click.option("--graph", is_flag=True, help="ASCII graph with colors")
@click.option("--author", help="Filter by author (partial match)")
@click.option("--since", help="Show commits after date (YYYY-MM-DD)")
@click.option("--grep", help="Filter by message (case-insensitive)")
@click.option("-n", type=int, help="Limit number of commits")
def log(oneline, graph, author, since, grep, n):
    silo_dir = require_silo()
    if not silo_dir:
        return

    head_hash, branch = get_head(silo_dir)
    if not head_hash:
        ok("no commits yet")
        return

    commits = list_commits_meta(silo_dir) if oneline else list_commits(silo_dir)
    if not commits:
        ok("no commits found")
        return

    if author:
        author_lower = author.lower()
        commits = [c for c in commits if author_lower in c.author.lower()]
    if since:
        try:
            since_ts = datetime.strptime(since, "%Y-%m-%d").timestamp()
            commits = [c for c in commits if c.timestamp >= since_ts]
        except ValueError:
            err(f"invalid date format: {since} (use YYYY-MM-DD)")
            return
    if grep:
        grep_lower = grep.lower()
        commits = [c for c in commits if grep_lower in c.message.lower()]
    if n is not None and n > 0:
        commits = commits[:n]

    if not commits:
        ok("no matching commits")
        return

    tag_map, note_map = _annotations(silo_dir)

    for c in commits:
        ts = readable_time(c.timestamp)
        if oneline:
            click.echo(f"{t(c.hash[:8], 'hash')} {_fmt_message(c.message)}")
        elif graph:
            sym = "*" if c.hash == head_hash else "o"
            marker = t(sym, "highlight") + " " + t(c.hash[:8], "hash")
            ref = ""
            if c.branch:
                ref = f" ({t(c.branch, 'branch')})"
            click.echo(f"  {marker}{ref} {_fmt_message(c.message)}")
            click.echo(f"  {t('|', 'dim')}  {ts}")
        else:
            click.echo(f"commit {t(c.hash, 'hash')}")
            if c.branch:
                click.echo(f"Branch: {t(c.branch, 'branch')}")
            click.echo(f"Author: {c.author}")
            for co in c.co_authors:
                click.echo(f"Co-author: {co}")
            tags = tag_map.get(c.hash, [])
            if tags:
                click.echo(f"Tags:   {', '.join(t(tn, 'tag') for tn in tags)}")
            notes = note_map.get(c.hash, [])
            if notes:
                for n in notes:
                    h, _, text = n.partition(" ")
                    click.echo(f"Notes:  {t(h, 'hash')} {text}")
            click.echo(f"Date:   {ts}")
            click.echo("")
            click.echo(f"    {_fmt_message(c.message)}")
            click.echo("")


@click.command(help="Show differences between commits or working tree")
@click.argument("commit1", required=False)
@click.argument("commit2", required=False)
@click.option("--stat", is_flag=True, help="Show file stats only")
@click.option("--noignore", is_flag=True, help="Ignore .siloignore when diffing working tree")
def diff(commit1, commit2, stat, noignore):
    silo_dir = require_silo()
    if not silo_dir:
        return

    project_dir = silo_dir.parent
    head_hash, _ = get_head(silo_dir)

    if commit1 and commit2:
        _, c1 = resolve_commit(silo_dir, commit1)
        _, c2 = resolve_commit(silo_dir, commit2)
        if not c1 or not c2:
            err("invalid commit hash")
            return
        tree1, tree2 = c1.tree, c2.tree
    elif commit1:
        _, c1 = resolve_commit(silo_dir, commit1)
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
        ignore = None if noignore else load_ignore_patterns(silo_dir)
        current = scan_tree(project_dir, ignore)
        tree1 = head.tree
        if ignore:
            keep = filter_ignored(list(tree1), ignore)
            tree1 = {k: tree1[k] for k in keep}
        tree2 = current

    a, m, r = diff_trees(tree1, tree2)

    if not a and not m and not r:
        ok("no differences")
        return

    nfiles = len(a) + len(m) + len(r)
    click.echo(f"{nfiles} file(s) changed:")

    for f in sorted(a):
        click.echo(f"  {t('+', 'added')} {t(f, 'file')}")
        if not stat:
            data2 = load_blob(silo_dir, a[f])
            if data2:
                click.echo(f"  {t('@@ added', 'added')}")
                for line in data2.decode().splitlines():
                    click.echo(f"  {t('+' + line, 'added')}")
    for f in sorted(m):
        click.echo(f"  {t('~', 'modified')} {t(f, 'file')}")
        if not stat:
            data1 = load_blob(silo_dir, m[f][0]) if m[f][0] else b""
            data2 = load_blob(silo_dir, m[f][1]) if m[f][1] else b""
            if data1 is None or data2 is None:
                click.echo(f"  {t('  (missing blob)', 'error')}")
            else:
                try:
                    lines1 = data1.decode().splitlines(keepends=True)
                    lines2 = data2.decode().splitlines(keepends=True)
                    for line in unified_diff(lines1, lines2, fromfile=f, tofile=f, lineterm=""):
                        if line.startswith("---") or line.startswith("+++"):
                            click.echo(f"  {t(line, 'dim')}")
                        elif line.startswith("@@"):
                            click.echo(f"  {t(line, 'highlight')}")
                        elif line.startswith("+"):
                            click.echo(f"  {t(line, 'added')}")
                        elif line.startswith("-"):
                            click.echo(f"  {t(line, 'removed')}")
                except UnicodeDecodeError:
                    click.echo(f"  {t('  (binary file)', 'dim')}")
    for f in sorted(r):
        click.echo(f"  {t('-', 'removed')} {t(f, 'file')}")
        if not stat:
            data1 = load_blob(silo_dir, r[f])
            if data1:
                click.echo(f"  {t('@@ removed', 'removed')}")
                for line in data1.decode().splitlines():
                    click.echo(f"  {t('-' + line, 'removed')}")


@click.command(help="Edit a commit message")
@click.argument("message", required=False)
@click.argument("commit_hash", required=False)
def amend(message, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    commit_hash, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err("no commits yet" if not commit_hash else "commit not found")
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

    conn_amend = get_db(silo_dir)
    conn_amend.execute("DELETE FROM commits_index WHERE hash = ?", (commit_hash,))
    conn_amend.commit()

    replace_commit_in_tags_notes(silo_dir, commit_hash, new_hash)

    set_head(silo_dir, new_hash, branch)

    clear_index(conn_amend)
    update_index(conn_amend, c.tree)
    conn_amend.close()

    log_action(silo_dir, "amend", f"[{new_hash[:8]}] {message}")
    ok(f"amended {t(commit_hash[:8], 'hash')} as {t(new_hash[:8], 'hash')} ({message})")


@click.command(help="Show details of a commit")
@click.argument("commit_hash", required=False)
def show(commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    commit_hash, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err("no commits yet" if not commit_hash else "commit not found")
        return

    parent_tree = {}
    if c.parent:
        pc = load_commit(silo_dir, c.parent)
        if pc:
            parent_tree = pc.tree

    a, m, r = diff_trees(parent_tree, c.tree)
    ts = readable_time(c.timestamp)

    tag_map, note_map = _annotations(silo_dir)

    click.echo(f"commit {t(c.hash, 'hash')}")
    click.echo(f"Author: {c.author}")
    for co in c.co_authors:
        click.echo(f"Co-authored-by: {co}")
    tags = tag_map.get(c.hash, [])
    if tags:
        click.echo(f"Tags:   {', '.join(t(tn, 'tag') for tn in tags)}")
    notes = note_map.get(c.hash, [])
    if notes:
        for n in notes:
            h, _, text = n.partition(" ")
            click.echo(f"Notes:  {t(h, 'hash')} {text}")
    click.echo(f"Date:   {ts}")
    if c.branch:
        click.echo(f"Branch: {t(c.branch, 'branch')}")
    click.echo("")
    click.echo(f"    {_fmt_message(c.message)}")
    click.echo("")
    click.echo(f"{len(a) + len(m) + len(r)} file(s) changed:")
    for f in sorted(a):
        click.echo(f"  {t('+', 'added')} {t(f, 'file')}")
    for f in sorted(m):
        click.echo(f"  {t('~', 'modified')} {t(f, 'file')}")
    for f in sorted(r):
        click.echo(f"  {t('-', 'removed')} {t(f, 'file')}")
