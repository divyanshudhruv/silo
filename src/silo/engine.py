import zlib
import hashlib

from pathlib import Path

from .utils import walk_files, ensure_dirs


def scan_tree(project_dir: Path, ignore_patterns: list[str] | None = None) -> dict[str, str]:
    tree, _ = scan_tree_with_content(project_dir, ignore_patterns)
    return tree


def scan_tree_with_content(project_dir: Path, ignore_patterns: list[str] | None = None) -> tuple[dict[str, str], dict[str, bytes]]:
    tree: dict[str, str] = {}
    contents: dict[str, bytes] = {}
    for f in walk_files(project_dir, ignore_patterns):
        rel: str = str(f.relative_to(project_dir).as_posix())
        data: bytes = f.read_bytes()
        h: str = hashlib.sha256(data).hexdigest()
        tree[rel] = h
        contents[rel] = data
    return tree, contents


def store_blob(silo_dir: Path, h: str, data: bytes) -> None:
    obj_dir: Path = silo_dir / "objects" / h[:2]
    ensure_dirs(obj_dir)
    p: Path = obj_dir / h[2:]
    if not p.exists():
        compressed: bytes = zlib.compress(data)
        p.write_bytes(compressed)


def load_blob(silo_dir: Path, h: str) -> bytes | None:
    p: Path = silo_dir / "objects" / h[:2] / h[2:]
    if not p.exists():
        return None
    return zlib.decompress(p.read_bytes())


def snapshot_to_objects(silo_dir: Path, tree: dict[str, str], content_map: dict[str, bytes] | None = None) -> dict[str, str]:
    stored: dict[str, str] = {}
    for rel_path, h in tree.items():
        if content_map and rel_path in content_map:
            data: bytes | None = content_map[rel_path]
        else:
            p: Path = silo_dir.parent / rel_path
            if not p.exists():
                continue
            data: bytes = p.read_bytes()
        store_blob(silo_dir, h, data)
        stored[rel_path] = h
    return stored


def diff_trees(old: dict[str, str], new: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, tuple[str, str]], dict[str, str]]:
    old: dict[str, str] = old or {}
    new: dict[str, str] = new or {}
    old_keys: set[str] = set(old.keys())
    new_keys: set[str] = set(new.keys())

    added: dict[str, str] = {k: new[k] for k in new_keys - old_keys}
    removed: dict[str, str] = {k: old[k] for k in old_keys - new_keys}
    modified: dict[str, tuple[str, str]] = {}
    for k in old_keys & new_keys:
        if old[k] != new[k]:
            modified[k] = (old[k], new[k])

    return added, modified, removed
