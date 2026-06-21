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


def load_commit(silo_dir, h):
    p = silo_dir / "commits" / f"{h}.json"
    if not p.exists():
        return None
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


def save_note(silo_dir, note):
    notes_dir = silo_dir / "notes"
    ensure_dirs(notes_dir)
    p = notes_dir / f"{note.commit_hash}.txt"
    with open(p, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {note.text}\n")


def load_note(silo_dir, commit_hash):
    p = silo_dir / "notes" / f"{commit_hash}.txt"
    if p.exists():
        return p.read_text().strip()
    return None


def get_config(silo_dir):
    p = silo_dir / "config.json"
    if p.exists():
        return Config(read_json(p))
    return Config()


def save_config(silo_dir, cfg):
    write_json(silo_dir / "config.json", cfg.data)
