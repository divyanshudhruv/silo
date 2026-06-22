import time

from ..database import resolve_commit, get_branch, walk_parents
from ..theme import err


def weld_entity(silo_dir, entity, commit_hash, branch, save_fn):
    if branch:
        branch_hash = get_branch(silo_dir, branch)
        if not branch_hash:
            err(f"branch '{branch}' not found")
            return False, None
        commits = list(walk_parents(silo_dir, branch_hash))
        if not commits:
            err(f"no commits on branch '{branch}'")
            return False, None
        entity.commits = commits
        entity.branch = branch
        entity.timestamp = time.time()
        save_fn(silo_dir, entity)
        return True, commits
    else:
        if not commit_hash:
            err("provide a commit hash or --branch")
            return False, None
        _, c = resolve_commit(silo_dir, commit_hash)
        if not c:
            err(f"commit '{commit_hash}' not found")
            return False, None
        entity.branch = ""
        if c.hash not in entity.commits:
            entity.commits.append(c.hash)
        entity.timestamp = time.time()
        save_fn(silo_dir, entity)
        return True, c


def unweld_entity(silo_dir, entity, commit_hash, branch, save_fn):
    if branch:
        if entity.branch != branch:
            err(f"not welded to branch '{branch}'")
            return False, branch
        entity.commits = []
        entity.branch = ""
        entity.timestamp = time.time()
        save_fn(silo_dir, entity)
        return True, branch
    else:
        if not commit_hash:
            err("provide a commit hash or --branch")
            return False, None
        resolved, _ = resolve_commit(silo_dir, commit_hash)
        target = resolved or commit_hash
        if entity.branch:
            entity.commits = []
            entity.branch = ""
            entity.timestamp = time.time()
            save_fn(silo_dir, entity)
            return True, target
        if target not in entity.commits:
            err(f"not attached to {target[:8]}")
            return False, target
        entity.commits = [c for c in entity.commits if c != target]
        entity.timestamp = time.time()
        save_fn(silo_dir, entity)
        return True, target
