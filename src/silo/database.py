import sqlite3
import time
import hashlib
from pathlib import Path

import click

from .models import Commit, Config, Tag, Note
from .utils import ensure_dirs, read_json, write_json
from .theme import warn


def init_db(silo_dir):
    ensure_dirs(silo_dir / "objects")
    ensure_dirs(silo_dir / "commits")
    ensure_dirs(silo_dir / "branches")
    ensure_dirs(silo_dir / "stash")
    ensure_dirs(silo_dir / "tags")
    ensure_dirs(silo_dir / "notes")
    ensure_dirs(silo_dir / "logs")

    conn = sqlite3.connect(str(silo_dir / "index.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_index (
            path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            mtime REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commits_index (
            hash TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            timestamp REAL NOT NULL,
            author TEXT NOT NULL,
            branch TEXT NOT NULL
        )
    """)
    conn.commit()

    if not (silo_dir / "config.json").exists():
        write_json(silo_dir / "config.json", {
            "name": "silo-user",
            "email": "user@silo.local",
        })

    if not (silo_dir / "HEAD").exists():
        (silo_dir / "HEAD").write_text("ref: refs/heads/main")

    branch_file = silo_dir / "branches" / "main"
    if not branch_file.exists():
        branch_file.write_text("")

    return conn


def get_db(silo_dir):
    return sqlite3.connect(str(silo_dir / "index.db"))


def update_index(conn, tree):
    now = time.time()
    for path, h in tree.items():
        conn.execute(
            "INSERT OR REPLACE INTO file_index (path, file_hash, mtime) VALUES (?, ?, ?)",
            (path, h, now),
        )
    conn.commit()


def get_index(conn):
    cur = conn.execute("SELECT path, file_hash FROM file_index")
    return {row[0]: row[1] for row in cur.fetchall()}


def clear_index(conn):
    conn.execute("DELETE FROM file_index")
    conn.commit()


def save_commit(silo_dir, commit, conn=None):
    p = silo_dir / "commits" / f"{commit.hash}.json"
    p.write_text(commit.to_json())
    close = conn is None
    if close:
        conn = sqlite3.connect(str(silo_dir / "index.db"))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO commits_index (hash, message, timestamp, author, branch) VALUES (?, ?, ?, ?, ?)",
            (commit.hash, commit.message, commit.timestamp, commit.author, commit.branch or ""),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        if close:
            conn.close()


def resolve_commit(silo_dir, ref=None):
    if not ref:
        h, _ = get_head(silo_dir)
        if not h:
            return None, None
        return h, load_commit(silo_dir, h)
    r = resolve_ref(silo_dir, ref)
    if not r:
        return None, None
    return r, load_commit(silo_dir, r)


def resolve_ref(silo_dir, ref):
    if not ref:
        return None
    if ref == "HEAD":
        h, _ = get_head(silo_dir)
        return h
    if ref.startswith("HEAD~"):
        try:
            n = int(ref[5:]) if len(ref) > 5 else 1
        except ValueError:
            return None
        h, _ = get_head(silo_dir)
        for _ in range(n):
            c = load_commit(silo_dir, h)
            if not c or not c.parent:
                return None
            h = c.parent
        return h
    c = find_commit(silo_dir, ref)
    if c:
        return c.hash
    return None


def find_commit(silo_dir, h):
    try:
        conn = sqlite3.connect(str(silo_dir / "index.db"))
        try:
            cur = conn.execute(
                "SELECT hash FROM commits_index WHERE hash LIKE ?",
                (h + "%",),
            )
            row = cur.fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        if row:
            return load_commit(silo_dir, row[0])
    except sqlite3.OperationalError:
        pass
    commits_dir = silo_dir / "commits"
    if not commits_dir.exists():
        return None
    for f in commits_dir.glob("*.json"):
        if f.stem.startswith(h):
            return Commit.from_json(f.read_text())
    return None


from functools import lru_cache


@lru_cache(maxsize=256)
def _load_commit_raw(silo_dir, h):
    p = silo_dir / "commits" / f"{h}.json"
    if not p.exists():
        return None
    return Commit.from_json(p.read_text())


def load_commit(silo_dir, h):
    return _load_commit_raw(silo_dir, h)


def list_commits(silo_dir, _from_sqlite=True):
    if _from_sqlite:
        try:
            conn = sqlite3.connect(str(silo_dir / "index.db"))
            try:
                cur = conn.execute("SELECT hash FROM commits_index ORDER BY timestamp DESC")
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                rows = None
            finally:
                conn.close()
            if rows:
                commits = []
                for (h,) in rows:
                    c = load_commit(silo_dir, h)
                    if c:
                        commits.append(c)
                return commits
        except Exception:
            pass
    commits_dir = silo_dir / "commits"
    if not commits_dir.exists():
        return []
    commits = []
    for f in commits_dir.glob("*.json"):
        c = Commit.from_json(f.read_text())
        commits.append(c)
    commits.sort(key=lambda c: c.timestamp, reverse=True)
    return commits


def list_commits_meta(silo_dir):
    try:
        conn = sqlite3.connect(str(silo_dir / "index.db"))
        try:
            cur = conn.execute("SELECT hash, message, timestamp, author, branch FROM commits_index ORDER BY timestamp DESC")
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = None
        finally:
            conn.close()
        if rows:
            return [Commit(hash=r[0], message=r[1], timestamp=r[2], author=r[3], branch=r[4], tree={}, parent=None) for r in rows]
    except sqlite3.OperationalError:
        pass
    return list_commits(silo_dir, _from_sqlite=False)


def walk_parents(silo_dir, start_hash):
    hashes = set()
    cur = start_hash
    while cur:
        hashes.add(cur)
        c = load_commit(silo_dir, cur)
        if not c or not c.parent:
            break
        cur = c.parent
    return hashes


def get_head(silo_dir):
    head_file = silo_dir / "HEAD"
    if not head_file.exists():
        return None, None
    content = head_file.read_text().strip()
    if content.startswith("ref:"):
        ref = content.split(" ", 1)[1].strip()
        branch_name = ref.split("/")[-1]
        branch_file = silo_dir / "branches" / branch_name
        if branch_file.exists():
            commit_hash = branch_file.read_text().strip()
            return commit_hash or None, branch_name
        return None, branch_name
    return content, None


def set_head(silo_dir, commit_hash, branch=None):
    if branch:
        set_branch(silo_dir, branch, commit_hash)
        (silo_dir / "HEAD").write_text(f"ref: refs/heads/{branch}")
    else:
        (silo_dir / "HEAD").write_text(commit_hash)


def set_branch(silo_dir, name, commit_hash):
    (silo_dir / "branches" / name).write_text(commit_hash)


def get_branch(silo_dir, name):
    p = silo_dir / "branches" / name
    if p.exists():
        return p.read_text().strip() or None
    return None


def list_branches(silo_dir):
    branches_dir = silo_dir / "branches"
    if not branches_dir.exists():
        return []
    return sorted(b.name for b in branches_dir.iterdir() if b.is_file())


def delete_branch(silo_dir, name):
    p = silo_dir / "branches" / name
    if not p.exists():
        return False
    _, cur = get_head(silo_dir)
    if name == cur:
        return False
    p.unlink()
    return True


def rename_branch(silo_dir, old_name, new_name):
    old_p = silo_dir / "branches" / old_name
    new_p = silo_dir / "branches" / new_name
    if not old_p.exists() or new_p.exists():
        return False
    old_p.rename(new_p)
    _, cur = get_head(silo_dir)
    if old_name == cur:
        set_head(silo_dir, new_p.read_text().strip(), new_name)
    return True


def log_action(silo_dir, action, msg=""):
    log_dir = silo_dir / "logs"
    ensure_dirs(log_dir)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_dir / "history.log", "a") as f:
        f.write(f"[{ts}] {action} {msg}\n")


# --- Tags ---

def _migrate_tag(silo_dir, name):
    old_p = silo_dir / "tags" / name
    new_p = silo_dir / "tags" / f"{name}.json"
    if old_p.exists() and not new_p.exists():
        h = old_p.read_text().strip()
        tag = Tag(name=name, commits=[h] if h else [], timestamp=time.time())
        new_p.write_text(tag.to_json())
        old_p.unlink()
        return tag
    return None


def save_tag(silo_dir, tag):
    ensure_dirs(silo_dir / "tags")
    (silo_dir / "tags" / f"{tag.name}.json").write_text(tag.to_json())


def load_tag(silo_dir, name):
    migrated = _migrate_tag(silo_dir, name)
    if migrated:
        return migrated
    p = silo_dir / "tags" / f"{name}.json"
    if p.exists():
        return Tag.from_json(p.read_text())
    return None


def list_tags(silo_dir):
    tags_dir = silo_dir / "tags"
    if not tags_dir.exists():
        return []
    # Migrate any old-format tags
    for f in list(tags_dir.iterdir()):
        if f.is_file() and f.suffix == "":
            _migrate_tag(silo_dir, f.name)
    return sorted(f.stem for f in tags_dir.iterdir() if f.is_file() and f.suffix == ".json")


def delete_tag(silo_dir, name):
    p = silo_dir / "tags" / f"{name}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def rename_tag(silo_dir, old_name, new_name):
    old_p = silo_dir / "tags" / f"{old_name}.json"
    new_p = silo_dir / "tags" / f"{new_name}.json"
    if not old_p.exists():
        return False
    if new_p.exists():
        return False
    old_p.rename(new_p)
    return True


# --- Notes ---

def _note_hash(text):
    return hashlib.sha256(f"{text}{time.time_ns()}".encode()).hexdigest()


def _migrate_note(silo_dir, f):
    h = f.stem
    text = f.read_text().strip()
    ts = time.time()
    note_hash = hashlib.sha256(f"{text}{ts}{h}".encode()).hexdigest()
    note = Note(hash=note_hash, text=text, commits=[h], timestamp=ts)
    new_p = silo_dir / "notes" / f"{note_hash}.json"
    new_p.write_text(note.to_json())
    f.unlink()
    return note


def save_note(silo_dir, note):
    ensure_dirs(silo_dir / "notes")
    (silo_dir / "notes" / f"{note.hash}.json").write_text(note.to_json())


def load_note(silo_dir, note_hash):
    p = silo_dir / "notes" / f"{note_hash}.json"
    if p.exists():
        return Note.from_json(p.read_text())
    return None


def list_notes(silo_dir):
    notes_dir = silo_dir / "notes"
    if not notes_dir.exists():
        return []
    result = []
    for f in sorted(notes_dir.iterdir()):
        if f.is_file():
            if f.suffix == ".json":
                result.append(Note.from_json(f.read_text()))
            elif f.suffix == ".txt":
                result.append(_migrate_note(silo_dir, f))
    return result


def delete_note(silo_dir, note_hash):
    p = silo_dir / "notes" / f"{note_hash}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def update_note(silo_dir, note_hash, text):
    note = load_note(silo_dir, note_hash)
    if not note:
        return False
    note.text = text
    note.timestamp = time.time()
    save_note(silo_dir, note)
    return True


# --- Helpers for amend ---

def replace_commit_in_tags_notes(silo_dir, old_hash, new_hash):
    for name in list_tags(silo_dir):
        tag = load_tag(silo_dir, name)
        if tag and old_hash in tag.commits:
            tag.commits = [new_hash if c == old_hash else c for c in tag.commits]
            tag.timestamp = time.time()
            save_tag(silo_dir, tag)

    for note in list_notes(silo_dir):
        if old_hash in note.commits:
            note.commits = [new_hash if c == old_hash else c for c in note.commits]
            note.timestamp = time.time()
            save_note(silo_dir, note)


# --- Config ---

def get_global_config_dir():
    return Path(click.get_app_dir("silo"))


def load_config_file(path):
    if path.exists():
        data = read_json(path)
        issues = Config.validate(data)
        if issues:
            for i in issues:
                warn(f"config '{path.name}': {i}")
        return Config(data)
    return Config()


def get_config(silo_dir, include_global=True):
    if include_global:
        global_dir = get_global_config_dir()
        global_cfg = load_config_file(global_dir / "config.json")
        local_cfg = load_config_file(silo_dir / "config.json")
        merged = Config({**global_cfg.data, **local_cfg.data})
        return merged
    return load_config_file(silo_dir / "config.json")


def save_config(silo_dir, cfg, global_=False):
    if global_:
        d = get_global_config_dir()
        ensure_dirs(d)
        write_json(d / "config.json", cfg.data)
    else:
        write_json(silo_dir / "config.json", cfg.data)
