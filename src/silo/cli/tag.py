import time

import click

from ..database import (
    load_tag, save_tag, list_tags, delete_tag, rename_tag,
    resolve_commit, get_branch, walk_parents, resolve_tag_commits,
    log_action,
)
from ..models import Tag
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="Manage tags")
def tag():
    pass


@tag.command("create", help="Create an unattached tag")
@click.argument("name")
def tag_create(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if load_tag(silo_dir, name):
        err(f"tag '{name}' already exists")
        return

    tag_obj = Tag(name=name, commits=[], timestamp=time.time())
    save_tag(silo_dir, tag_obj)
    log_action(silo_dir, "tag", f"created '{name}'")
    ok(f"created tag '{t(name, 'tag')}' (unattached)")


@tag.command("weld", help="Attach tag to a commit or all commits on a branch")
@click.argument("name")
@click.argument("commit_hash", required=False)
@click.option("--branch", "-b", help="Attach to all commits on this branch")
def tag_weld(name, commit_hash, branch):
    silo_dir = require_silo()
    if not silo_dir:
        return

    tag_obj = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    if branch:
        branch_hash = get_branch(silo_dir, branch)
        if not branch_hash:
            err(f"branch '{branch}' not found")
            return
        commits = walk_parents(silo_dir, branch_hash)
        if not commits:
            err(f"no commits on branch '{branch}'")
            return
        tag_obj.commits = list(commits)
        tag_obj.branch = branch
        tag_obj.timestamp = time.time()
        save_tag(silo_dir, tag_obj)
        log_action(silo_dir, "tag", f"welded '{name}' -> branch '{branch}' ({len(commits)} commits)")
        ok(f"welded tag '{t(name, 'tag')}' to {t(str(len(commits)), 'hash')} commit(s) on branch '{t(branch, 'branch')}'")
    else:
        if not commit_hash:
            err("provide a commit hash or --branch")
            return
        _, c = resolve_commit(silo_dir, commit_hash)
        if not c:
            err(f"commit '{commit_hash}' not found")
            return
        tag_obj.branch = ""
        if c.hash not in tag_obj.commits:
            tag_obj.commits.append(c.hash)
        tag_obj.timestamp = time.time()
        save_tag(silo_dir, tag_obj)
        log_action(silo_dir, "tag", f"welded '{name}' -> {c.hash[:8]}")
        ok(f"welded tag '{t(name, 'tag')}' to {t(c.hash[:8], 'hash')}")


@tag.command("unweld", help="Detach tag from a commit or all commits on a branch")
@click.argument("name")
@click.argument("commit_hash", required=False)
@click.option("--branch", "-b", help="Detach from all commits on this branch")
def tag_unweld(name, commit_hash, branch):
    silo_dir = require_silo()
    if not silo_dir:
        return

    tag_obj = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    if branch:
        if tag_obj.branch != branch:
            err(f"tag '{name}' is not welded to branch '{branch}'")
            return
        tag_obj.commits = []
        tag_obj.branch = ""
        tag_obj.timestamp = time.time()
        save_tag(silo_dir, tag_obj)
        log_action(silo_dir, "tag", f"unwelded '{name}' from branch '{branch}'")
        ok(f"unwelded tag '{t(name, 'tag')}' from branch '{t(branch, 'branch')}'")
    else:
        if not commit_hash:
            err("provide a commit hash or --branch")
            return
        resolved, _ = resolve_commit(silo_dir, commit_hash)
        target = resolved or commit_hash
        if tag_obj.branch:
            tag_obj.commits = []
            tag_obj.branch = ""
        if target not in tag_obj.commits:
            err(f"tag '{name}' is not attached to {t(target[:8], 'hash')}")
            return
        tag_obj.commits = [c for c in tag_obj.commits if c != target]
        tag_obj.timestamp = time.time()
        save_tag(silo_dir, tag_obj)
        log_action(silo_dir, "tag", f"unwelded '{name}' from {target[:8]}")
        ok(f"unwelded tag '{t(name, 'tag')}' from {t(target[:8], 'hash')}")


@tag.command("add", help="Create tag and attach to a commit")
@click.argument("name")
@click.argument("commit_hash", required=False)
def tag_add(name, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if load_tag(silo_dir, name):
        err(f"tag '{name}' already exists")
        return

    commit_hash, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err("no commits to tag" if not commit_hash else f"commit '{commit_hash}' not found")
        return

    tag_obj = Tag(name=name, commits=[c.hash], timestamp=time.time())
    save_tag(silo_dir, tag_obj)
    log_action(silo_dir, "tag", f"'{name}' -> {c.hash[:8]}")
    ok(f"tagged '{t(name, 'tag')}' at {t(c.hash[:8], 'hash')}")


@tag.command("list", help="List all tags")
def tag_list():
    silo_dir = require_silo()
    if not silo_dir:
        return

    tags = list_tags(silo_dir)
    if not tags:
        ok("no tags")
        return

    for name in tags:
        tag_obj = load_tag(silo_dir, name)
        if tag_obj:
            resolved = resolve_tag_commits(silo_dir, tag_obj)
            if resolved:
                sorted_c = sorted(resolved)
                h = sorted_c[-1][:8]
                count = len(sorted_c)
                label = f" (+{count-1})" if count > 1 else ""
                branch_info = f" [{t(tag_obj.branch, 'branch')}]" if tag_obj.branch else ""
                click.echo(f"{t(name, 'tag')} -> {t(h, 'hash')}{label}{branch_info}")
            else:
                click.echo(f"{t(name, 'tag')} (unattached)")
        else:
            click.echo(f"{t(name, 'tag')} -> ?")


@tag.command("show", help="Show tag details")
@click.argument("name")
def tag_show(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    tag_obj = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    click.echo(f"tag:  {t(name, 'tag')}")
    if tag_obj.branch:
        click.echo(f"branch: {t(tag_obj.branch, 'branch')}")
    resolved = resolve_tag_commits(silo_dir, tag_obj)
    if resolved:
        sorted_c = sorted(resolved)
        click.echo(f"commits ({len(sorted_c)}):")
        for c in sorted_c:
            click.echo(f"  {t(c[:8], 'hash')}")
    else:
        click.echo(f"commits: (unattached)")


@tag.command("delete", help="Delete a tag")
@click.argument("name")
def tag_delete(name):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if delete_tag(silo_dir, name):
        log_action(silo_dir, "tag", f"deleted '{name}'")
        ok(f"tag '{t(name, 'tag')}' deleted")
    else:
        err(f"tag '{name}' not found")


@tag.command("rename", help="Rename a tag")
@click.argument("old")
@click.argument("new")
def tag_rename(old, new):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if rename_tag(silo_dir, old, new):
        log_action(silo_dir, "tag", f"renamed '{old}' -> '{new}'")
        ok(f"renamed tag '{t(old, 'tag')}' -> '{t(new, 'tag')}'")
    else:
        err(f"cannot rename '{old}' (not found or '{new}' exists)")
