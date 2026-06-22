import zlib
import hashlib

from .utils import walk_files, ensure_dirs


def scan_tree(project_dir, ignore_patterns=None):
    tree, _ = scan_tree_with_content(project_dir, ignore_patterns)
    return tree


def scan_tree_with_content(project_dir, ignore_patterns=None):
    tree = {}
    contents = {}
    for f in walk_files(project_dir, ignore_patterns):
        rel = str(f.relative_to(project_dir).as_posix())
        data = f.read_bytes()
        h = hashlib.sha256(data).hexdigest()
        tree[rel] = h
        contents[rel] = data
    return tree, contents


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


def snapshot_to_objects(silo_dir, tree, content_map=None):
    stored = {}
    for rel_path, h in tree.items():
        if content_map and rel_path in content_map:
            data = content_map[rel_path]
        else:
            p = silo_dir.parent / rel_path
            if not p.exists():
                continue
            data = p.read_bytes()
        store_blob(silo_dir, h, data)
        stored[rel_path] = h
    return stored


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
