import time

import click

from ..database import load_commit, save_note, load_note, log_action
from ..models import Note
from ..theme import ok, err, t
from ._common import require_silo


@click.group(help="Annotate commits with notes")
def note():
    pass


@note.command("add", help="Add a note to a commit")
@click.argument("commit_hash")
@click.argument("text")
def note_add(commit_hash, text):
    silo_dir = require_silo()
    if not silo_dir:
        return

    c = load_commit(silo_dir, commit_hash)
    if not c:
        err(f"commit '{commit_hash}' not found")
        return

    n = Note(commit_hash=commit_hash, text=text, timestamp=time.time())
    save_note(silo_dir, n)
    log_action(silo_dir, "note", f"added to {commit_hash[:8]}")
    ok(f"note added to {t(commit_hash[:8], 'hash')}")


@note.command("list", help="Show notes for a commit")
@click.argument("commit_hash")
def note_list(commit_hash):
    silo_dir = require_silo()
    if not silo_dir:
        return

    text = load_note(silo_dir, commit_hash)
    if text:
        click.echo(text)
    else:
        ok(f"no notes for {t(commit_hash[:8], 'hash')}")
