import time

import click

from ..database import load_tag, save_tag, list_tags, get_head, log_action
from ..models import Tag
from ..theme import ok, err, t
from ._common import require_silo


@click.group(help="Manage tags")
def tag():
    pass


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
