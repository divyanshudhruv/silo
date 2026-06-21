import os
import sqlite3
import json
import time
from pathlib import Path

from .models import Commit, Config
from .utils import ensure_dirs, read_json, write_json


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


def save_commit(silo_dir, commit):
    p = silo_dir / "commits" / f"{commit.hash}.json"
    p.write_text(commit.to_json())
    try:
        conn = sqlite3.connect(str(silo_dir / "index.db"))
        conn.execute(
            "INSERT OR REPLACE INTO commits_index (hash, message, timestamp, author, branch) VALUES (?, ?, ?, ?, ?)",
            (commit.hash, commit.message, commit.timestamp, commit.author, commit.branch or ""),
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass


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
        cur = conn.execute(
            "SELECT hash FROM commits_index WHERE hash LIKE ?",
            (h + "%",),
        )
        row = cur.fetchone()
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


def load_commit(silo_dir, h):
    p = silo_dir / "commits" / f"{h}.json"
    if not p.exists():
        return find_commit(silo_dir, h)
    return Commit.from_json(p.read_text())


def list_commits(silo_dir):
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
        cur = conn.execute("SELECT hash, message, timestamp, author, branch FROM commits_index ORDER BY timestamp DESC")
        rows = cur.fetchall()
        conn.close()
        if rows:
            from .models import Commit
            return [Commit(hash=r[0], message=r[1], timestamp=r[2], author=r[3], branch=r[4], tree={}, parent=None) for r in rows]
    except sqlite3.OperationalError:
        pass
    return list_commits(silo_dir)


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


def save_tag(silo_dir, tag):
    tags_dir = silo_dir / "tags"
    ensure_dirs(tags_dir)
    (tags_dir / tag.name).write_text(tag.commit_hash)


def load_tag(silo_dir, name):
    p = silo_dir / "tags" / name
    if p.exists():
        return p.read_text().strip()
    return None


def list_tags(silo_dir):
    tags_dir = silo_dir / "tags"
    if not tags_dir.exists():
        return []
    return sorted(t.name for t in tags_dir.iterdir() if t.is_file())


def delete_tag(silo_dir, name):
    p = silo_dir / "tags" / name
    if p.exists():
        p.unlink()
        return True
    return False


def rename_tag(silo_dir, old_name, new_name):
    old_p = silo_dir / "tags" / old_name
    new_p = silo_dir / "tags" / new_name
    if not old_p.exists():
        return False
    if new_p.exists():
        return False
    old_p.rename(new_p)
    return True


def save_note(silo_dir, note):
    notes_dir = silo_dir / "notes"
    ensure_dirs(notes_dir)
    p = notes_dir / f"{note.commit_hash}.txt"
    with open(p, "w") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {note.text}\n")


def load_note(silo_dir, commit_hash):
    p = silo_dir / "notes" / f"{commit_hash}.txt"
    if p.exists():
        return p.read_text().strip()
    return None


def delete_note(silo_dir, commit_hash):
    p = silo_dir / "notes" / f"{commit_hash}.txt"
    if p.exists():
        p.unlink()
        return True
    return False


def update_note(silo_dir, commit_hash, text):
    notes_dir = silo_dir / "notes"
    ensure_dirs(notes_dir)
    p = notes_dir / f"{commit_hash}.txt"
    p.write_text(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    return True


def get_config(silo_dir):
    p = silo_dir / "config.json"
    if p.exists():
        return Config(read_json(p))
    return Config()


def save_config(silo_dir, cfg):
    write_json(silo_dir / "config.json", cfg.data)
