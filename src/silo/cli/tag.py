import time

import click

from ..database import (
    load_tag, save_tag, list_tags, delete_tag, rename_tag,
    get_head, resolve_ref, log_action,
)
from ..models import Tag
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="Manage tags", invoke_without_command=True)
@click.option("--delete", "-d", "del_name", help="Delete a tag")
@click.option("--move", "-m", nargs=2, metavar="NAME NEW_NAME", help="Rename a tag")
@click.pass_context
def tag(ctx, del_name, move):
    silo_dir = require_silo()
    if not silo_dir:
        return
    if ctx.invoked_subcommand is not None:
        return
    if del_name:
        if delete_tag(silo_dir, del_name):
            log_action(silo_dir, "tag", f"deleted '{del_name}'")
            ok(f"tag '{t(del_name, 'file')}' deleted")
        else:
            err(f"tag '{del_name}' not found")
        return
    if move:
        name, new_name = move
        if rename_tag(silo_dir, name, new_name):
            log_action(silo_dir, "tag", f"renamed '{name}' -> '{new_name}'")
            ok(f"renamed tag '{t(name, 'file')}' -> '{t(new_name, 'file')}'")
        else:
            err(f"cannot rename '{name}' (not found or '{new_name}' exists)")
        return
    click.echo(ctx.get_help())


@tag.command("add", help="Add a tag to a commit")
@click.argument("name")
@click.argument("commit_hash", required=False)
def tag_add(name, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if load_tag(silo_dir, name):
        err(f"tag '{name}' already exists")
        return

    if commit_hash:
        resolved = resolve_ref(silo_dir, commit_hash)
        if resolved:
            commit_hash = resolved

    if not commit_hash:
        head_hash, _ = get_head(silo_dir)
        if not head_hash:
            err("no commits to tag")
            return
        commit_hash = head_hash

    t_obj = Tag(name=name, commit_hash=commit_hash, timestamp=time.time())
    save_tag(silo_dir, t_obj)
    log_action(silo_dir, "tag", f"'{name}' -> {commit_hash[:8]}")
    ok(f"tagged '{t(name, 'file')}' at {t(commit_hash[:8], 'hash')}")


@tag.command("list", help="List all tags")
def tag_list():
    silo_dir = require_silo()
    if not silo_dir:
        return

    tags = list_tags(silo_dir)
    if tags:
        for t_name in tags:
            h = load_tag(silo_dir, t_name)
            click.echo(f"{t(t_name, 'file')} -> {t(h[:8] if h else '?', 'hash')}")
    else:
        ok("no tags")



