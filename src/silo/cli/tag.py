import time
from pathlib import Path
import click

from ..database import (
    load_tag, save_tag, list_tags, delete_tag, rename_tag,
    resolve_commit, resolve_tag_commits,
    log_action,
)
from ..models import Tag, Commit
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup
from ._entity import weld_entity, unweld_entity


@click.group(cls=ColorGroup, help="Manage tags")
def tag() -> None:
    pass


@tag.command("create", help="Create an unattached tag")
@click.argument("name")
def tag_create(name: str) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if load_tag(silo_dir, name) is not None:
        err(f"tag '{name}' already exists")
        return

    tag_obj: Tag = Tag(name=name, commits=[], timestamp=time.time())
    save_tag(silo_dir, tag_obj)
    log_action(silo_dir, "tag", f"created '{name}'")
    ok(f"created tag '{t(name, 'tag')}' (unattached)")


@tag.command("weld", help="Attach tag to a commit or all commits on a branch")
@click.argument("name")
@click.argument("commit_hash", required=False)
@click.option("--branch", "-b", help="Attach to all commits on this branch")
def tag_weld(name: str, commit_hash: str | None, branch: str | None) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    tag_obj: Tag | None = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    ok_flag, result = weld_entity(
        silo_dir, tag_obj, commit_hash, branch, save_tag)
    if not ok_flag:
        return

    if branch:
        log_action(
            silo_dir, "tag", f"welded '{name}' -> branch '{branch}' ({len(result)} commits)")
        ok(f"welded tag '{t(name, 'tag')}' to {t(str(len(result)), 'hash')} commit(s) on branch '{t(branch, 'branch')}'")
    else:
        log_action(silo_dir, "tag", f"welded '{name}' -> {result.hash[:8]}")
        ok(f"welded tag '{t(name, 'tag')}' to {t(result.hash[:8], 'hash')}")


@tag.command("unweld", help="Detach tag from a commit or all commits on a branch")
@click.argument("name")
@click.argument("commit_hash", required=False)
@click.option("--branch", "-b", help="Detach from all commits on this branch")
def tag_unweld(name: str, commit_hash: str | None, branch: str | None) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    tag_obj: Tag | None = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    ok_flag, result = unweld_entity(
        silo_dir, tag_obj, commit_hash, branch, save_tag)
    if not ok_flag:
        return

    if branch:
        log_action(silo_dir, "tag",
                   f"unwelded '{name}' from branch '{branch}'")
        ok(f"unwelded tag '{t(name, 'tag')}' from branch '{t(branch, 'branch')}'")
    else:
        log_action(silo_dir, "tag", f"unwelded '{name}' from {result[:8]}")
        ok(f"unwelded tag '{t(name, 'tag')}' from {t(result[:8], 'hash')}")


@tag.command("add", help="Create tag and attach to a commit")
@click.argument("name")
@click.argument("commit_hash", required=False)
def tag_add(name: str, commit_hash: str | None) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if load_tag(silo_dir, name) is not None:
        err(f"tag '{name}' already exists")
        return

    _, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err(
            "no commits to tag" if not commit_hash else f"commit '{commit_hash}' not found")
        return

    tag_obj: Tag = Tag(name=name, commits=[c.hash], timestamp=time.time())
    save_tag(silo_dir, tag_obj)
    log_action(silo_dir, "tag", f"'{name}' -> {c.hash[:8]}")
    ok(f"tagged '{t(name, 'tag')}' at {t(c.hash[:8], 'hash')}")


@tag.command("list", help="List all tags")
def tag_list() -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    tags: list[str] = list_tags(silo_dir)
    if not tags:
        ok("no tags")
        return

    for name in tags:
        tag_obj: Tag | None = load_tag(silo_dir, name)
        if tag_obj:
            resolved: list[str] | None = resolve_tag_commits(silo_dir, tag_obj)
            if resolved:
                sorted_c: list[str] = sorted(resolved)
                h: str = sorted_c[-1][:8]
                count: int = len(sorted_c)
                label: str = f" (+{count-1})" if count > 1 else ""
                branch_info: str = f" [{t(tag_obj.branch, 'branch')}]" if tag_obj.branch else ""
                click.echo(
                    f"{t(name, 'tag')} -> {t(h, 'hash')}{label}{branch_info}")
            else:
                click.echo(f"{t(name, 'tag')} (unattached)")
        else:
            click.echo(f"{t(name, 'tag')} -> ?")


@tag.command("show", help="Show tag details")
@click.argument("name")
def tag_show(name: str) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    tag_obj: Tag | None = load_tag(silo_dir, name)
    if not tag_obj:
        err(f"tag '{name}' not found")
        return

    click.echo(f"tag:  {t(name, 'tag')}")
    if tag_obj.branch:
        click.echo(f"branch: {t(tag_obj.branch, 'branch')}")
    resolved: list[str] | None = resolve_tag_commits(silo_dir, tag_obj)
    if resolved:
        sorted_c: list[str] = sorted(resolved)
        click.echo(f"commits ({len(sorted_c)}):")
        for c in sorted_c:
            click.echo(f"  {t(c[:8], 'hash')}")
    else:
        click.echo("commits: (unattached)")


@tag.command("delete", help="Delete a tag")
@click.argument("name")
def tag_delete(name: str) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if delete_tag(silo_dir, name) is not None:
        log_action(silo_dir, "tag", f"deleted '{name}'")
        ok(f"tag '{t(name, 'tag')}' deleted")
    else:
        err(f"tag '{name}' not found")


@tag.command("rename", help="Rename a tag")
@click.argument("old")
@click.argument("new")
def tag_rename(old: str, new: str) -> None:
    silo_dir: Path | None = require_silo()
    if not silo_dir:
        return

    if rename_tag(silo_dir, old, new) is not None:
        log_action(silo_dir, "tag", f"renamed '{old}' -> '{new}'")
        ok(f"renamed tag '{t(old, 'tag')}' -> '{t(new, 'tag')}'")
    else:
        err(f"cannot rename '{old}' (not found or '{new}' exists)")
