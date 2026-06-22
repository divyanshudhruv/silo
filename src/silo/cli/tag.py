import time

import click

from ..database import (
    load_tag, save_tag, list_tags, delete_tag, rename_tag,
    resolve_commit, log_action,
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


@tag.command("weld", help="Attach tag to a commit")
@click.argument("name")
@click.argument("commit_hash")
def tag_weld(name, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    tag_obj = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    _, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err(f"commit '{commit_hash}' not found")
        return

    if c.hash not in tag_obj.commits:
        tag_obj.commits.append(c.hash)
    tag_obj.timestamp = time.time()
    save_tag(silo_dir, tag_obj)
    log_action(silo_dir, "tag", f"welded '{name}' -> {c.hash[:8]}")
    ok(f"welded tag '{t(name, 'tag')}' to {t(c.hash[:8], 'hash')}")


@tag.command("unweld", help="Detach tag from a commit")
@click.argument("name")
@click.argument("commit_hash")
def tag_unweld(name, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    tag_obj = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    resolved, _ = resolve_commit(silo_dir, commit_hash)
    target = resolved or commit_hash

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
        if tag_obj and tag_obj.commits:
            count = len(tag_obj.commits)
            h = tag_obj.commits[0][:8]
            click.echo(f"{t(name, 'tag')} -> {t(h, 'hash')} (+{count-1})" if count > 1 else f"{t(name, 'tag')} -> {t(h, 'hash')}")
        elif tag_obj:
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
    if tag_obj.commits:
        click.echo(f"commits ({len(tag_obj.commits)}):")
        for c in tag_obj.commits:
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
