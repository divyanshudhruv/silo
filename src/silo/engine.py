import os
import zlib
from pathlib import Path

from .utils import walk_files, hash_file, ensure_dirs


def scan_tree(project_dir):
    tree = {}
    for f in walk_files(project_dir):
        rel = str(f.relative_to(project_dir).as_posix())
        tree[rel] = hash_file(f)
    return tree


def store_blob(silo_dir, h, data):
    obj_dir = silo_dir / "objects" / h[:2]
    ensure_dirs(obj_dir)
    p = obj_dir / h[2:]
    if not p.exists():
        compressed = zlib.compress(data)
        p.write_bytes(compressed)


def load_blob(silo_dir, h):
    p = silo_dir / "objects" / h[:2] / h[2:]
    if not p.exists():
        return None
    return zlib.decompress(p.read_bytes())


def snapshot_to_objects(silo_dir, project_dir, tree):
    stored = {}
    for rel_path, h in tree.items():
        f = project_dir / rel_path
        if not f.exists():
            continue
        store_blob(silo_dir, h, f.read_bytes())
        stored[rel_path] = h
    return stored


def load_tree(silo_dir, tree_dict):
    out = {}
    for rel_path, h in tree_dict.items():
        data = load_blob(silo_dir, h)
        if data is not None:
            out[rel_path] = data
    return out


def diff_trees(old, new):
    old = old or {}
    new = new or {}
    old_keys = set(old.keys())
    new_keys = set(new.keys())

    added = {k: new[k] for k in new_keys - old_keys}
    removed = {k: old[k] for k in old_keys - new_keys}
    modified = {}
    for k in old_keys & new_keys:
        if old[k] != new[k]:
            modified[k] = (old[k], new[k])

    return added, modified, removed
