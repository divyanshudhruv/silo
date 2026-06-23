import sqlite3
import time
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import Commit, Config, Tag, Note
from .utils import ensure_dirs, read_json, write_json
from .theme import warn


def init_db(silo_dir):
    ensure_dirs(silo_dir / "objects")
    ensure_dirs(silo_dir / "commits")
    ensure_dirs(silo_dir / "branches")
    ensure_dirs(silo_dir / "tags")  
    ensure_dirs(silo_dir / "notes")
    ensure_dirs(silo_dir / "logs")

    conn: sqlite3.Connection = sqlite3.connect(str(silo_dir / "index.db"))
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
        from .models import CONFIG_DEFAULTS
        write_json(silo_dir / "config.json", dict(CONFIG_DEFAULTS))

    if not (silo_dir / "HEAD").exists():
        (silo_dir / "HEAD").write_text("ref: refs/heads/main")

    branch_file: Path = silo_dir / "branches" / "main"
    if not branch_file.exists():
        branch_file.write_text("")

    return conn


def get_db(silo_dir):
    return sqlite3.Connection(str(silo_dir / "index.db"))


def update_index(conn, tree):
    now: float = time.time()
    for path, h in tree.items():
        conn.execute(
            "INSERT OR REPLACE INTO file_index (path, file_hash, mtime) VALUES (?, ?, ?)",
            (path, h, now),
        )
    conn.commit()


def get_index(conn):
    cur: sqlite3.Cursor = conn.execute("SELECT path, file_hash FROM file_index")
    return {row[0]: row[1] for row in cur.fetchall()}


def clear_index(conn):
    conn.execute("DELETE FROM file_index")
    conn.commit()


def save_commit(silo_dir, commit, conn=None):
    p: Path = silo_dir / "commits" / f"{commit.hash}.json"
    p.write_text(commit.to_json())
    close = conn is None
    if close:
        conn: sqlite3.Connection = sqlite3.connect(str(silo_dir / "index.db"))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO commits_index (hash, message, timestamp, author, branch) VALUES (?, ?, ?, ?, ?)",
            (commit.hash, commit.message, commit.timestamp, commit.author, commit.branch or ""),
        )
        conn.commit()
    except sqlite3.OperationalError:
        warn("commit saved to disk but index update failed")
    finally:
        if close:
            conn.close()


def resolve_commit(silo_dir, ref=None):
    if not ref:
        h, _ = get_head(silo_dir)
        if not h:
            return None, None
        return h, load_commit(silo_dir, h)
    r: str | None = resolve_ref(silo_dir, ref)
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
            n: int = int(ref[5:]) if len(ref) > 5 else 1
        except ValueError:
            return None
        h, _ = get_head(silo_dir)
        for _ in range(n):
            c: Commit | None = load_commit(silo_dir, h)
            if not c or not c.parent:
                return None
            h = c.parent
        return h
    c: Commit | None = find_commit(silo_dir, ref)
    if c:
        return c.hash
    return None


def find_commit(silo_dir, h):
    try:
        conn: sqlite3.Connection = sqlite3.connect(str(silo_dir / "index.db"))
        try:
            cur: sqlite3.Cursor = conn.execute(
                "SELECT hash FROM commits_index WHERE hash LIKE ?",
                (h + "%",),
            )
            row: tuple[str] | None = cur.fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        if row:
            return load_commit(silo_dir, row[0])
    except sqlite3.OperationalError:
        pass
    commits_dir: Path = silo_dir / "commits"
    if not commits_dir.exists():
        return None
    for f in commits_dir.glob("*.json"):
        if f.stem.startswith(h):
            return Commit.from_json(f.read_text())
    return None


@lru_cache(maxsize=256)
def load_commit(silo_dir, h: str) -> Commit | None:
    p: Path = silo_dir / "commits" / f"{h}.json"
    if not p.exists():
        return None
    return Commit.from_json(p.read_text())


def list_commits(silo_dir, _from_sqlite: bool = True) -> list[Commit]:
    if _from_sqlite:
        try:
            conn: sqlite3.Connection = sqlite3.connect(str(silo_dir / "index.db"))
            try:
                cur: sqlite3.Cursor = conn.execute("SELECT hash FROM commits_index ORDER BY timestamp DESC")
                rows: list[tuple[str]] | None = cur.fetchall()
            except sqlite3.OperationalError:
                rows = None
            finally:
                conn.close()
            if rows:
                commits: list[Commit] = []
                for (h,) in rows:
                    c: Commit | None = load_commit(silo_dir, h)
                    if c:
                        commits.append(c)
                return commits
        except Exception:
            warn("falling back to filesystem for commit listing")
    commits_dir: Path = silo_dir / "commits"
    if not commits_dir.exists():
        return []
    commits: list[Commit] = []
    for f in commits_dir.glob("*.json"):
        c: Commit = Commit.from_json(f.read_text())
        commits.append(c)
    commits.sort(key=lambda c: c.timestamp, reverse=True)
    return commits


def list_commits_meta(silo_dir: Path) -> list[Commit]:
    try:
        conn: sqlite3.Connection = sqlite3.connect(str(silo_dir / "index.db"))
        try:
            cur: sqlite3.Cursor = conn.execute("SELECT hash, message, timestamp, author, branch FROM commits_index ORDER BY timestamp DESC")
            rows: list[tuple[str, str, float, str, str]] | None = cur.fetchall()
        except sqlite3.OperationalError:
            rows: list[tuple[str, str, float, str, str]] | None = None
        finally:
            conn.close()
        if rows:
            return [Commit(hash=h[0], message=h[1], timestamp=h[2], author=h[3], branch=h[4], tree={}, parent=None) for h in rows]
    except sqlite3.OperationalError:
        pass
    return list_commits(silo_dir, _from_sqlite=False)


def walk_parents(silo_dir: Path, start_hash: str) -> set[str]:
    hashes: set[str] = set()
    cur: str | None = start_hash
    while cur:
        hashes.add(cur)
        c: Commit | None = load_commit(silo_dir, cur)
        if not c or not c.parent:
            break
        cur = c.parent
    return hashes


def get_head(silo_dir: Path) -> tuple[str | None, str | None]:
    head_file = silo_dir / "HEAD"
    if not head_file.exists():
        return None, None
    content: str = head_file.read_text().strip()
    if content.startswith("ref:"):
        ref: str = content.split(" ", 1)[1].strip()
        branch_name: str = ref.split("/")[-1]
        branch_file: Path = silo_dir / "branches" / branch_name
        if branch_file.exists():
            commit_hash: str | None = branch_file.read_text().strip()
            return commit_hash or None, branch_name
        return None, branch_name
    return content, None


def set_head(silo_dir: Path, commit_hash: str | None, branch: str | None = None):
    if branch:
        set_branch(silo_dir, branch, commit_hash)
        (silo_dir / "HEAD").write_text(f"ref: refs/heads/{branch}")
    else:
        (silo_dir / "HEAD").write_text(commit_hash)


def set_branch(silo_dir: Path, name: str, commit_hash: str):
    (silo_dir / "branches" / name).write_text(commit_hash)


def get_branch(silo_dir: Path, name: str) -> str | None:
    p: Path = silo_dir / "branches" / name
    if p.exists():
        return p.read_text().strip() or None
    return None


def list_branches(silo_dir: Path) -> list[str]:
    branches_dir: Path = silo_dir / "branches"
    if not branches_dir.exists():
        return []
    return sorted(b.name for b in branches_dir.iterdir() if b.is_file())


def delete_branch(silo_dir: Path, name: str) -> bool:
    p: Path = silo_dir / "branches" / name
    if not p.exists():
        return False
    _, cur = get_head(silo_dir)
    if name == cur:
        return False
    p.unlink()
    return True


def rename_branch(silo_dir: Path, old_name: str, new_name: str) -> bool:
    old_p: Path = silo_dir / "branches" / old_name
    new_p: Path = silo_dir / "branches" / new_name
    if not old_p.exists() or new_p.exists():
        return False
    old_p.rename(new_p)
    _, cur = get_head(silo_dir)
    if old_name == cur:
        set_head(silo_dir, new_p.read_text().strip(), new_name)
    return True


def log_action(silo_dir: Path, action: str, msg: str = "") -> None:
    log_dir: Path = silo_dir / "logs"
    ensure_dirs(log_dir)
    ts: str = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_dir / "history.log", "a") as f: # type: ignore[arg-type]
        f.write(f"[{ts}] {action} {msg}\n")


# --- Tags ---

def _migrate_tag(silo_dir: Path, name: str) -> Tag | None:
    old_p: Path = silo_dir / "tags" / name
    new_p: Path = silo_dir / "tags" / f"{name}.json"
    if old_p.exists() and not new_p.exists():
        h: str | None = old_p.read_text().strip()
        tag: Tag = Tag(name=name, commits=[h] if h else [], timestamp=time.time()) # type: ignore
        new_p.write_text(tag.to_json())
        old_p.unlink()
        return tag
    return None


def save_tag(silo_dir: Path, tag: Tag) -> None:
    ensure_dirs(silo_dir / "tags")
    (silo_dir / "tags" / f"{tag.name}.json").write_text(tag.to_json())


def load_tag(silo_dir: Path, name: str) -> Tag | None:
    migrated: Tag | None = _migrate_tag(silo_dir, name)
    if migrated:
        return migrated
    p: Path = silo_dir / "tags" / f"{name}.json"
    if p.exists():
        return Tag.from_json(p.read_text())
    return None


def list_tags(silo_dir: Path) -> list[str]:
    tags_dir: Path = silo_dir / "tags"
    if not tags_dir.exists():
        return []
    # Migrate any old-format tags
    for f in list(tags_dir.iterdir()):
        if f.is_file() and f.suffix == "":
            _migrate_tag(silo_dir, f.name)
    return sorted(f.stem for f in tags_dir.iterdir() if f.is_file() and f.suffix == ".json")


def delete_tag(silo_dir: Path, name: str) -> bool:
    p: Path = silo_dir / "tags" / f"{name}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def rename_tag(silo_dir: Path, old_name: str, new_name: str) -> bool:
    old_p: Path = silo_dir / "tags" / f"{old_name}.json"
    new_p: Path = silo_dir / "tags" / f"{new_name}.json"
    if not old_p.exists():
        return False
    if new_p.exists():
        return False
    old_p.rename(new_p)
    return True


# --- Notes ---

def _migrate_note(silo_dir: Path, f: Path) -> Note:
    h: str = f.stem
    text: str = f.read_text().strip()
    ts: float = time.time()
    note_hash: str = hashlib.sha256(f"{text}{ts}{h}".encode()).hexdigest()
    note: Note = Note(hash=note_hash, text=text, commits=[h], timestamp=ts)
    new_p: Path = silo_dir / "notes" / f"{note_hash}.json"
    new_p.write_text(note.to_json())
    f.unlink()
    return note


def save_note(silo_dir: Path, note: Note):
    ensure_dirs(silo_dir / "notes")
    (silo_dir / "notes" / f"{note.hash}.json").write_text(note.to_json())


def load_note(silo_dir: Path, note_hash: str) -> Note | None:
    p: Path = silo_dir / "notes" / f"{note_hash}.json"
    if p.exists():
        return Note.from_json(p.read_text())
    notes_dir: Path = silo_dir / "notes"
    if notes_dir.exists():
        for f in notes_dir.iterdir():
            if f.suffix == ".json" and f.stem.startswith(note_hash):
                return Note.from_json(f.read_text())
    return None


def list_notes(silo_dir: Path) -> list[Note]:
    notes_dir: Path = silo_dir / "notes"
    if not notes_dir.exists():
        return []
    result: list[Note] = []
    for f in sorted(notes_dir.iterdir()):
        if f.is_file():
            if f.suffix == ".json":
                result.append(Note.from_json(f.read_text()))
            elif f.suffix == ".txt":
                result.append(_migrate_note(silo_dir, f)) # type: ignore
    return result


def delete_note(silo_dir: Path, note_hash: str) -> bool:
    note: Note | None = load_note(silo_dir, note_hash)
    if not note:
        return False
    p: Path = silo_dir / "notes" / f"{note.hash}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def update_note(silo_dir: Path, note_hash: str, text: str) -> bool:
    note: Note | None = load_note(silo_dir, note_hash)
    if not note:
        return False
    note.text = text
    note.timestamp = time.time()
    save_note(silo_dir, note)
    return True


# --- Helpers for amend ---

def resolve_tag_commits(silo_dir: Path, tag: Tag) -> set[str]:
    if tag.branch:
        h: str | None = get_branch(silo_dir, tag.branch)
        if h:
            return walk_parents(silo_dir, h)
        return set()
    return set(tag.commits)


def resolve_note_commits(silo_dir: Path, note: Note) -> set[str]:
    if note.branch:
        h: str | None = get_branch(silo_dir, note.branch)
        if h:
            return walk_parents(silo_dir, h)
        return set()
    return set(note.commits)


def replace_commit_in_tags_notes(silo_dir: Path, old_hash: str, new_hash: str):
    for name in list_tags(silo_dir):
        tag: Tag | None = load_tag(silo_dir, name)
        if tag and old_hash in resolve_tag_commits(silo_dir, tag):
            tag.commits = [new_hash if c == old_hash else c for c in tag.commits]
            tag.timestamp = time.time()
            save_tag(silo_dir, tag)

    for note in list_notes(silo_dir):
        if old_hash in resolve_note_commits(silo_dir, note):
            note: Note = Note(hash=note.hash, text=note.text, commits=[new_hash if c == old_hash else c for c in note.commits], timestamp=time.time()) # type: ignore
            save_note(silo_dir, note)


# --- Config ---

def get_config(silo_dir: Path) -> Config:
    p: Path = silo_dir / "config.json"
    if p.exists():
        data: dict[str, Any] = read_json(p)
        issues: list[str] | None = Config.validate(data)
        if issues:
            for i in issues:
                warn(f"config '{p.name}': {i}")
        return Config(data)
    return Config()


def save_config(silo_dir: Path, cfg: Config) -> None:
    write_json(silo_dir / "config.json", cfg.data) # type: ignore[arg-type]
