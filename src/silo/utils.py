import os
import json
import hashlib
from pathlib import Path


def walk_files(dir_path):
    p = Path(dir_path)
    files = []
    for f in sorted(p.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(p)
        parts = rel.parts
        if parts and parts[0].startswith(".silo"):
            continue
        if parts and parts[0] == ".git":
            continue
        if parts and parts[0].startswith("__pycache__"):
            continue
        if f.suffix == ".pyc":
            continue
        files.append(f)
    return files


def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dirs(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def read_json(path):
    with open(path, "r") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def find_silo_dir(start="."):
    p = Path(start).resolve()
    for parent in [p] + list(p.parents):
        d = parent / ".silo"
        if d.is_dir():
            return d
    return None


def readable_time(t):
    from datetime import datetime
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
