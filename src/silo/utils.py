import os
import json
import hashlib
import fnmatch
from pathlib import Path


def _try_read(path):
    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def load_ignore_patterns(silo_dir):
    p = silo_dir.parent / ".siloignore"
    patterns = []
    if p.exists():
        for line in _try_read(p).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def walk_files(dir_path, ignore_patterns=None):
    p = Path(dir_path)
    for f in p.rglob("*"):
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
        if ignore_patterns:
            rel_str = str(rel.as_posix())
            skip = False
            for pat in ignore_patterns:
                if pat.endswith("/") and rel_str.startswith(pat):
                    skip = True
                    break
                if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(Path(rel_str).name, pat):
                    skip = True
                    break
            if skip:
                continue
        yield f


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
