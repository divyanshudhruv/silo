import json
import hashlib
import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Any, Generator


_ALWAYS_EXCLUDE: set[str] = {".silo", ".git", "__pycache__"}


def _try_read(path: Path) -> str:
    raw: bytes = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def load_ignore_patterns(silo_dir: Path) -> list[str]:
    config_path: Path = silo_dir / "config.json"
    use_gitignore: bool = False
    if config_path.exists():
        try:
            cfg: dict[str, Any] = json.loads(config_path.read_text())
            use_gitignore = cfg.get("use_gitignore", False)
        except (json.JSONDecodeError, OSError):
            pass

    ignore_file: str = ".gitignore" if use_gitignore else ".siloignore"
    p: Path = silo_dir.parent / ignore_file
    patterns: list[str] = []
    lines: list[str] = []
    if p.exists():
        lines = _try_read(p).splitlines()
    for line in lines:
        line: str = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _dir_match(rel_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if pat.endswith("/"):
            base: str = pat.rstrip("/")
            if fnmatch.fnmatch(rel_path, base) or fnmatch.fnmatch(Path(rel_path).name, base):
                return True
    return False


def filter_ignored(paths: list[str], ignore_patterns: list[str] | None = None) -> list[str]:
    if not ignore_patterns:
        return list(paths)
    result: list[str] = []
    for rel in paths:
        skip: bool = False
        for pat in ignore_patterns:
            if pat.endswith("/"):
                base: str = pat.rstrip("/")
                if fnmatch.fnmatch(rel, base) or fnmatch.fnmatch(Path(rel).name, base):
                    skip: bool = True
                    break
            elif fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat):
                skip: bool = True
                break
        if not skip:
            parts: list[str] = rel.split("/")
            if any(p in _ALWAYS_EXCLUDE for p in parts[:-1]):
                skip: bool = True
        if not skip:
            result.append(rel)
    return result


def walk_files(dir_path: str, ignore_patterns: list[str] | None = None) -> Generator[Path, None, None]:
    root: Path = Path(dir_path)
    stack: list[Path] = [root]
    while stack:
        d: Path = stack.pop()
        try:
            entries: list[Path] = list(d.iterdir())
        except PermissionError:
            continue
        dirs: list[Path] = []
        for entry in entries:
            if entry.is_dir():
                if entry.name in _ALWAYS_EXCLUDE:
                    continue
                rel_dir: str = str(entry.relative_to(root).as_posix())
                if ignore_patterns and _dir_match(rel_dir, ignore_patterns):
                    continue
                dirs.append(entry)
            elif entry.is_file():
                rel: str = str(entry.relative_to(root).as_posix())
                if ignore_patterns:
                    skip: bool = False
                    for pat in ignore_patterns:
                        if pat.endswith("/"):
                            continue
                        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(entry.name, pat):
                            skip: bool = True
                            break
                    if skip:
                        continue
                yield entry
        stack.extend(reversed(dirs))


def ensure_dirs(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    with open(path, "r") as f: # type: ignore[arg-type]
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def find_silo_dir(start: str = ".") -> Path | None:
    p: Path = Path(start).resolve()
    for parent in [p] + list(p.parents):
        d: Path = parent / ".silo"
        if d.is_dir():
            return d
    return None


def readable_time(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
