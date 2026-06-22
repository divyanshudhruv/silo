import json
import hashlib
import fnmatch
from datetime import datetime
from pathlib import Path


_ALWAYS_EXCLUDE = {".silo", ".git", "__pycache__"}


def _try_read(path):
    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def load_ignore_patterns(silo_dir):
    config_path = silo_dir / "config.json"
    usegitignore = False
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text())
            usegitignore = cfg.get("usegitignore", "false") == "true"
        except (json.JSONDecodeError, OSError):
            pass

    ignore_file = ".gitignore" if usegitignore else ".siloignore"
    p = silo_dir.parent / ignore_file
    patterns = []
    if p.exists():
        for line in _try_read(p).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def _dir_match(rel_path, patterns):
    for pat in patterns:
        if pat.endswith("/"):
            base = pat.rstrip("/")
            if rel_path == base or rel_path.startswith(base + "/"):
                return True
    return False


def filter_ignored(paths, ignore_patterns):
    """Return only paths that do NOT match ignore patterns (or _ALWAYS_EXCLUDE dirs)."""
    if not ignore_patterns:
        return list(paths)
    result = []
    for rel in paths:
        skip = False
        for pat in ignore_patterns:
            if pat.endswith("/"):
                base = pat.rstrip("/")
                if rel == base or rel.startswith(base + "/"):
                    skip = True
                    break
            elif fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat):
                skip = True
                break
        if not skip:
            parts = rel.split("/")
            if any(p in _ALWAYS_EXCLUDE for p in parts[:-1]):
                skip = True
        if not skip:
            result.append(rel)
    return result


def walk_files(dir_path, ignore_patterns=None):
    root = Path(dir_path)
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except PermissionError:
            continue
        dirs = []
        for entry in entries:
            if entry.is_dir():
                if entry.name in _ALWAYS_EXCLUDE:
                    continue
                rel_dir = str(entry.relative_to(root).as_posix())
                if ignore_patterns and _dir_match(rel_dir, ignore_patterns):
                    continue
                dirs.append(entry)
            elif entry.is_file():
                rel = str(entry.relative_to(root).as_posix())
                if ignore_patterns:
                    skip = False
                    for pat in ignore_patterns:
                        if pat.endswith("/"):
                            continue
                        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(entry.name, pat):
                            skip = True
                            break
                    if skip:
                        continue
                yield entry
        stack.extend(reversed(dirs))


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
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
