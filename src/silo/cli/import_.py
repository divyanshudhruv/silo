
import sqlite3
import json
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from ..engine import snapshot_to_objects
from ..database import (
    init_db, get_db, update_index,
    save_commit, set_head, log_action, get_config, save_config,
)
from ..models import Commit, Config
from ..theme import ok, err, t
from ._common import require_silo, ColorGroup


def _git_tree(git_path: Path, commit_hash: str) -> dict[str, str] | None:
    result: subprocess.CompletedProcess = subprocess.run(
        ["git", "ls-tree", "-r", "-z", commit_hash],
        cwd=str(git_path), capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    tree: dict[str, str] = {}
    for entry in result.stdout.strip("\x00").split("\x00"):
        if not entry.strip():
            continue
        parts: list[str] = entry.split("\t", 1)
        if len(parts) != 2:
            continue
        meta, path = parts
        # meta: "mode type hash"
        blob_hash: str = meta.split()[-1]
        tree[path] = blob_hash
    return tree


def _import_commit(git_path: Path, silo_dir: Path, commit_hash: str) -> tuple[dict[str, str], dict[str, bytes]] | None:
    git_tree: dict[str, str] | None = _git_tree(git_path, commit_hash)
    if git_tree is None:
        return None

    tree: dict[str, str] = {}
    contents: dict[str, bytes] = {}
    paths: list[str] = list(git_tree.keys())
    if not paths:
        return tree, contents

    blob_hashes: list[str] = [git_tree[p] for p in paths]
    proc: subprocess.Popen = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=str(git_path), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    stdin_data: bytes = "\n".join(blob_hashes).encode()
    stdout_data, _ = proc.communicate(stdin_data)

    pos: int = 0
    buf: bytes = stdout_data
    for path, blob_hash in zip(paths, blob_hashes):
        # Read header line: "<hash> <type> <size>\n"
        header_end: int = buf.find(b"\n", pos)
        if header_end == -1:
            break
        header: str = buf[pos:header_end].decode()
        pos = header_end + 1
        hdr_parts: list[str] = header.split(" ")
        if len(hdr_parts) < 3:
            continue
        _, obj_type, size_str = hdr_parts
        if obj_type == "missing":
            continue
        size: int = int(size_str)
        data_b: bytes = buf[pos:pos + size]
        pos += size
        if pos < len(buf) and buf[pos] == ord("\n"):
            pos += 1
        h_: str = hashlib.sha256(data_b).hexdigest()
        tree[path] = h_
        contents[path] = data_b

    snapshot_to_objects(silo_dir, tree, contents)
    return tree, contents


@click.group("import", cls=ColorGroup, help="Import history from Git or GitHub")
def import_cmd() -> None:
    pass


@import_cmd.command("git", help="Import commits from the current git repository")
@click.argument("git_dir", required=False, default=".")
def git_cmd(git_dir: str) -> None:
    git_path: Path = Path(git_dir).resolve()
    if not (git_path / ".git").exists():
        err(f"not a git repository: {git_path}")
        return

    silo_dir: Path = git_path / ".silo"
    if silo_dir.exists():
        if not click.confirm(t(f"silo already exists in {git_path}. reinitialize? existing data will be lost.", "warn")):
            return
        for d in ["objects", "commits", "branches", "tags", "notes", "logs"]:
            p = silo_dir / d
            if p.exists():
                shutil.rmtree(p)
        db: Path = silo_dir / "index.db"
        if db.exists():
            db.unlink()

    conn: sqlite3.Connection | None = init_db(silo_dir)
    if conn is None:
        err("failed to initialize database")
        return
    conn.close()
    log_action(silo_dir, "import", f"from git: {git_path}")
    ok(f"importing {git_path} ...")

    result: subprocess.CompletedProcess = subprocess.run(
        ["git", "log", "--first-parent", "--format=%H%n%ct%n%an <%ae>%n%s%n==SILO==="],
        cwd=str(git_path), capture_output=True, text=True
    )
    if result.returncode != 0:
        err(f"git log failed: {result.stderr}")
        return

    entries: list[str] = result.stdout.strip().split("==SILO===")
    entries = [e.strip() for e in entries if e.strip()]
    entries.reverse()
    total: int = len(entries)
    cfg: Config | None = get_config(silo_dir)
    if cfg is None:
        cfg = Config()

    last_author: str | None = None
    prev_silo_hash: str | None = None

    for i, entry in enumerate(entries):
        lines: list[str] = entry.strip().split("\n")
        if len(lines) < 4:
            continue
        ts: float = float(lines[1])
        author: str = lines[2]
        msg = "\n".join(lines[3:])
        last_author = author

        tree, contents = _import_commit(
            git_path, silo_dir, lines[0])
        if tree is None:
            continue

        commit_data: dict[str, str | float | list[str]] = {
            "tree": tree,
            "parent": prev_silo_hash,
            "author": author,
            "message": msg,
            "co_authors": [],
            "timestamp": ts,
            "branch": "main",
        }
        raw: bytes = json.dumps(commit_data, sort_keys=True).encode()
        ch: str = hashlib.sha256(raw).hexdigest()
        prev_silo_hash = ch
        c_obj: Commit = Commit(hash=ch, **commit_data)
        save_commit(silo_dir, c_obj)
        set_head(silo_dir, ch, "main")
        conn: sqlite3.Connection | None = get_db(silo_dir)
        if conn is None:
            err("failed to get database connection")
            return
        update_index(conn, tree)
        conn.close()
        log_action(silo_dir, "commit", f"[{ch[:8]}] {msg}")

        click.echo(f"  [{t(f'{i+1}/{total}', 'highlight')}] {t(ch[:8], 'hash')} {msg[:50]}")

    if last_author and "@" in last_author:
        m: re.Match[str] | None = re.match(r"(.+)\s+<([^>]+)>", last_author)
        if m:
            cfg.name = m.group(1)
            cfg.email = m.group(2)
            save_config(silo_dir, cfg)
            click.echo(
                f"  config: {t('name', 'file')}={t(cfg.name, 'modified')}, {t('email', 'file')}={t(cfg.email, 'modified')}")

    ok(f"imported {t(str(total), 'hash')} commits from {t(str(git_path), 'file')}")


@import_cmd.command("gh", help="Clone a GitHub repo and import its history")
@click.argument("repo")
def gh_cmd(repo):
    tmp: Path = Path(tempfile.mkdtemp(suffix="_silo_import"))
    url: str = repo
    if "/" in repo and not repo.startswith("http"):
        url = f"https://github.com/{repo}.git"

    ok(f"cloning {url} ...")
    result: subprocess.CompletedProcess = subprocess.run(
        ["git", "clone", "--quiet", url, str(tmp / "repo")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err(f"clone failed: {result.stderr}")
        shutil.rmtree(tmp)
        return

    ok("importing cloned repo ...")
    ctx: click.Context = click.get_current_context()
    ctx.invoke(git_cmd, git_dir=str(tmp / "repo"))

    shutil.rmtree(tmp)
