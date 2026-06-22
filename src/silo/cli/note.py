import time
import hashlib

import click

from ..database import (
    resolve_commit, save_note, load_note, list_notes,
    delete_note, update_note, log_action,
)
from ..models import Note
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


@click.group(cls=ColorGroup, help="Annotate commits with notes")
def note():
    pass


@note.command("create", help="Create an unattached note")
@click.argument("text")
def note_create(text):
    silo_dir = require_silo()
    if not silo_dir:
        return

    note_hash = hashlib.sha256(f"{text}{time.time_ns()}".encode()).hexdigest()
    note_obj = Note(hash=note_hash, text=text, commits=[], timestamp=time.time())
    save_note(silo_dir, note_obj)
    log_action(silo_dir, "note", f"created {note_hash[:8]}")
    ok(f"created note {t(note_hash[:8], 'hash')} (unattached)")


@note.command("weld", help="Attach note to a commit")
@click.argument("note_hash")
@click.argument("commit_hash")
def note_weld(note_hash, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    note_obj = load_note(silo_dir, note_hash)
    if not note_obj:
        err(f"note '{note_hash[:8]}' not found")
        return

    _, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err(f"commit '{commit_hash}' not found")
        return

    if c.hash not in note_obj.commits:
        note_obj.commits.append(c.hash)
    note_obj.timestamp = time.time()
    save_note(silo_dir, note_obj)
    log_action(silo_dir, "note", f"welded {note_hash[:8]} -> {c.hash[:8]}")
    ok(f"welded note {t(note_hash[:8], 'hash')} to {t(c.hash[:8], 'hash')}")


@note.command("unweld", help="Detach note from a commit")
@click.argument("note_hash")
@click.argument("commit_hash")
def note_unweld(note_hash, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    note_obj = load_note(silo_dir, note_hash)
    if not note_obj:
        err(f"note '{note_hash[:8]}' not found")
        return

    resolved, _ = resolve_commit(silo_dir, commit_hash)
    target = resolved or commit_hash

    if target not in note_obj.commits:
        err(f"note {t(note_hash[:8], 'hash')} is not attached to {t(target[:8], 'hash')}")
        return

    note_obj.commits = [c for c in note_obj.commits if c != target]
    note_obj.timestamp = time.time()
    save_note(silo_dir, note_obj)
    log_action(silo_dir, "note", f"unwelded {note_hash[:8]} from {target[:8]}")
    ok(f"unwelded note {t(note_hash[:8], 'hash')} from {t(target[:8], 'hash')}")


@note.command("add", help="Create note and attach to a commit")
@click.argument("text")
@click.argument("commit_hash", required=False)
def note_add(text, commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    commit_hash, c = resolve_commit(silo_dir, commit_hash)
    if not c:
        err("no commits yet" if not commit_hash else f"commit '{commit_hash}' not found")
        return

    note_hash = hashlib.sha256(f"{text}{time.time_ns()}".encode()).hexdigest()
    note_obj = Note(hash=note_hash, text=text, commits=[c.hash], timestamp=time.time())
    save_note(silo_dir, note_obj)
    log_action(silo_dir, "note", f"added {note_hash[:8]} to {c.hash[:8]}")
    ok(f"note {t(note_hash[:8], 'hash')} added to {t(c.hash[:8], 'hash')}")


@note.command("list", help="List all notes")
def note_list():
    silo_dir = require_silo()
    if not silo_dir:
        return

    notes = list_notes(silo_dir)
    if not notes:
        ok("no notes")
        return

    for n in notes:
        count = len(n.commits) if n.commits else 0
        preview = n.text[:50] + ("..." if len(n.text) > 50 else "")
        if count:
            click.echo(f"{t(n.hash[:8], 'hash')} {preview} ({t(str(count), 'modified')} commit{'s' if count > 1 else ''})")
        else:
            click.echo(f"{t(n.hash[:8], 'hash')} {preview} ({t('unattached', 'dim')})")


@note.command("show", help="Show note details")
@click.argument("note_hash")
def note_show(note_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    note_obj = load_note(silo_dir, note_hash)
    if not note_obj:
        err(f"note '{note_hash[:8]}' not found")
        return

    click.echo(f"hash:   {t(note_obj.hash, 'hash')}")
    click.echo(f"text:   {note_obj.text}")
    if note_obj.commits:
        click.echo(f"commits ({len(note_obj.commits)}):")
        for c in note_obj.commits:
            click.echo(f"  {t(c[:8], 'hash')}")
    else:
        click.echo(f"commits: (unattached)")


@note.command("delete", help="Delete a note")
@click.argument("note_hash")
def note_delete(note_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if delete_note(silo_dir, note_hash):
        log_action(silo_dir, "note", f"deleted {note_hash[:8]}")
        ok(f"note {t(note_hash[:8], 'hash')} deleted")
    else:
        err(f"note '{note_hash[:8]}' not found")


@note.command("edit", help="Replace note text")
@click.argument("note_hash")
@click.argument("text")
def note_edit(note_hash, text):
    silo_dir = require_silo()
    if not silo_dir:
        return

    if update_note(silo_dir, note_hash, text):
        log_action(silo_dir, "note", f"edited {note_hash[:8]}")
        ok(f"note {t(note_hash[:8], 'hash')} updated")
    else:
        err(f"note '{note_hash[:8]}' not found")
