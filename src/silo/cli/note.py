import time

import click

from ..database import (
    get_head, load_commit, save_note, load_note,
    delete_note, update_note, resolve_ref, log_action,
)
from ..models import Note
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="Annotate commits with notes", invoke_without_command=True)
@click.option("--delete", "-d", "del_ref", help="Delete note for a commit")
@click.option("--move", "-m", nargs=2, metavar="TEXT REF", help="Replace note text for a commit")
@click.pass_context
def note(ctx, del_ref, move):
    silo_dir = require_silo()
    if not silo_dir:
        return
    if ctx.invoked_subcommand is not None:
        return

    if del_ref:
        resolved = resolve_ref(silo_dir, del_ref)
        if resolved:
            del_ref = resolved
        if delete_note(silo_dir, del_ref):
            log_action(silo_dir, "note", f"deleted for {del_ref[:8]}")
            ok(f"note deleted for {t(del_ref[:8], 'hash')}")
        else:
            err(f"no note for {t(del_ref[:8], 'hash')}")
        return

    if move:
        text, ref = move
        resolved = resolve_ref(silo_dir, ref)
        if resolved:
            ref = resolved
        update_note(silo_dir, ref, text)
        log_action(silo_dir, "note", f"updated for {ref[:8]}")
        ok(f"note updated for {t(ref[:8], 'hash')}")
        return

    click.echo(ctx.get_help())


@note.command("add", help="Add a note to a commit")
@click.argument("text")
@click.argument("commit_hash", required=False)
def note_add(text, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if not commit_hash:
        head_hash, _ = get_head(silo_dir)
        commit_hash = head_hash
        if not commit_hash:
            err("no commits yet")
            return

    resolved = resolve_ref(silo_dir, commit_hash)
    if resolved:
        commit_hash = resolved

    c = load_commit(silo_dir, commit_hash)
    if not c:
        err(f"commit '{commit_hash}' not found")
        return

    n = Note(commit_hash=commit_hash, text=text, timestamp=time.time())
    save_note(silo_dir, n)
    log_action(silo_dir, "note", f"added to {commit_hash[:8]}")
    ok(f"note added to {t(commit_hash[:8], 'hash')}")


@note.command("list", help="Show notes for a commit")
@click.argument("commit_hash", required=False)
def note_list(commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if not commit_hash:
        head_hash, _ = get_head(silo_dir)
        commit_hash = head_hash
        if not commit_hash:
            err("no commits yet")
            return

    resolved = resolve_ref(silo_dir, commit_hash)
    if resolved:
        commit_hash = resolved

    text = load_note(silo_dir, commit_hash)
    if text:
        click.echo(text)
    else:
        ok(f"no notes for {t(commit_hash[:8], 'hash')}")



